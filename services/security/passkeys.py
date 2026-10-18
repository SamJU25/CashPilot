"""
WebAuthn passkey registration and assertion verification for Tier 3 HITL execution.

Each authentication challenge is bound to one intent ID and consumed on first use, so a
signed assertion cannot be replayed against another intent or retried after a failure.
Registration is trust-on-first-use per tenant: there is no user-auth layer yet, so a second
passkey for an already-enrolled tenant is refused instead of letting any caller add a key.
User verification (biometric or device PIN) is required on both ceremonies.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

logger = logging.getLogger(__name__)

PASSKEY_STORAGE_DIR = os.path.abspath(
    os.environ.get("COPILOT_LEDGER_DIR")
    or os.path.join(os.path.dirname(__file__), "../../.data")
)

CHALLENGE_TTL_SECONDS = 300


class PasskeyError(Exception):
    """Raised when a passkey ceremony fails verification."""


class PasskeyAlreadyRegisteredError(PasskeyError):
    """Raised when a tenant that already has a passkey requests another registration."""


class PasskeyNotRegisteredError(PasskeyError):
    """Raised when a tenant without a passkey requests a Tier 3 challenge."""


class PasskeyOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1)


class PasskeyRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1)
    credential: dict[str, Any] = Field(description="PublicKeyCredential JSON from navigator.credentials.create()")


@dataclass
class _StoredCredential:
    credential_id: bytes
    public_key: bytes
    sign_count: int


class PasskeyRegistry:
    """Thread-safe persistent passkey store and challenge issuer."""

    def __init__(
        self,
        rp_id: str,
        rp_name: str,
        origins: list[str],
        storage_dir: Optional[str] = None,
    ) -> None:
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._origins = origins
        self._storage_dir = storage_dir
        self._file_path = os.path.join(self._storage_dir, "passkeys.json") if self._storage_dir else None
        self._credentials: dict[str, _StoredCredential] = {}
        self._challenges: dict[tuple[str, str], tuple[bytes, float]] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for tenant_id, cred_data in data.items():
                    self._credentials[tenant_id] = _StoredCredential(
                        credential_id=bytes.fromhex(cred_data["credential_id"]),
                        public_key=bytes.fromhex(cred_data["public_key"]),
                        sign_count=int(cred_data["sign_count"]),
                    )
        except Exception as exc:
            logger.warning("Could not load persisted passkeys from %s: %s", self._file_path, exc)

    def _persist(self) -> None:
        if not self._file_path:
            return
        os.makedirs(self._storage_dir, exist_ok=True)
        tmp_path = f"{self._file_path}.tmp"
        try:
            data = {
                tenant_id: {
                    "credential_id": cred.credential_id.hex(),
                    "public_key": cred.public_key.hex(),
                    "sign_count": cred.sign_count,
                }
                for tenant_id, cred in self._credentials.items()
            }
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._file_path)
        except OSError as exc:
            logger.warning("Failed to persist passkeys to %s: %s", self._file_path, exc)

    def has_passkey(self, tenant_id: str) -> bool:
        with self._lock:
            return tenant_id in self._credentials

    def registration_options(self, tenant_id: str) -> str:
        with self._lock:
            if tenant_id in self._credentials:
                raise PasskeyAlreadyRegisteredError(f"Tenant {tenant_id} already has a registered passkey")
            options = generate_registration_options(
                rp_id=self._rp_id,
                rp_name=self._rp_name,
                user_name=tenant_id,
                user_id=tenant_id.encode(),
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.PREFERRED,
                    user_verification=UserVerificationRequirement.REQUIRED,
                ),
            )
            self._issue(("register", tenant_id), options.challenge)
        return options_to_json(options)

    def register(self, tenant_id: str, credential: dict[str, Any]) -> None:
        with self._lock:
            if tenant_id in self._credentials:
                raise PasskeyAlreadyRegisteredError(f"Tenant {tenant_id} already has a registered passkey")
            challenge = self._consume(("register", tenant_id))
            try:
                verified = verify_registration_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self._rp_id,
                    expected_origin=self._origins,
                    require_user_verification=True,
                )
            except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
                raise PasskeyError(f"Passkey registration failed: {exc}") from exc
            self._credentials[tenant_id] = _StoredCredential(
                verified.credential_id, verified.credential_public_key, verified.sign_count
            )
            self._persist()

    def authentication_options(self, tenant_id: str, intent_id: str) -> str:
        with self._lock:
            stored = self._credentials.get(tenant_id)
            if stored is None:
                raise PasskeyNotRegisteredError(f"No passkey registered for tenant {tenant_id}")
            options = generate_authentication_options(
                rp_id=self._rp_id,
                allow_credentials=[PublicKeyCredentialDescriptor(id=stored.credential_id)],
                user_verification=UserVerificationRequirement.REQUIRED,
            )
            self._issue(("authenticate", intent_id), options.challenge)
        return options_to_json(options)

    def verify_assertion(self, tenant_id: str, intent_id: str, credential: dict[str, Any]) -> str:
        """Returns the verified credential ID (base64url) as the audit proof for the intent."""
        with self._lock:
            stored = self._credentials.get(tenant_id)
            if stored is None:
                raise PasskeyNotRegisteredError(f"No passkey registered for tenant {tenant_id}")
            challenge = self._consume(("authenticate", intent_id))
            try:
                verified = verify_authentication_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self._rp_id,
                    expected_origin=self._origins,
                    credential_public_key=stored.public_key,
                    credential_current_sign_count=stored.sign_count,
                    require_user_verification=True,
                )
            except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
                raise PasskeyError(f"Passkey assertion failed: {exc}") from exc
            stored.sign_count = verified.new_sign_count
            self._persist()
            return bytes_to_base64url(stored.credential_id)

    def clear(self) -> None:
        with self._lock:
            self._credentials.clear()
            self._challenges.clear()
            if os.path.exists(self._file_path):
                try:
                    os.remove(self._file_path)
                except OSError:
                    pass

    def _issue(self, key: tuple[str, str], challenge: bytes) -> None:
        self._challenges[key] = (challenge, time.monotonic() + CHALLENGE_TTL_SECONDS)

    def _consume(self, key: tuple[str, str]) -> bytes:
        entry = self._challenges.pop(key, None)
        if entry is None or time.monotonic() > entry[1]:
            raise PasskeyError("No active passkey challenge; request new options")
        return entry[0]


passkey_registry = PasskeyRegistry(
    rp_id=os.getenv("WEBAUTHN_RP_ID", "localhost"),
    rp_name=os.getenv("WEBAUTHN_RP_NAME", "SME Finance Copilot"),
    origins=[o.strip() for o in os.getenv("WEBAUTHN_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    storage_dir=PASSKEY_STORAGE_DIR,
)
