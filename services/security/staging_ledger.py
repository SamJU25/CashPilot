"""
In-memory staging ledger for Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
Enforces the Three-Tier Security Gate to prevent unauthorized automated money movements.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from services.security.crypto import open_text, seal_text
from services.security.file_utils import ensure_private_dir, restrict_file
from services.security.passkeys import PasskeyError, PasskeyRegistry, passkey_registry
from services.security.three_tier_gate import StagedActionIntent, requires_biometric_execution

logger = logging.getLogger(__name__)

LEDGER_DIR = os.path.abspath(
    os.environ.get("COPILOT_LEDGER_DIR")
    or os.path.join(os.path.dirname(__file__), "../../.data")
)
# Pending proposals are a queue for a human, not an archive: stale ones are dropped.
STAGED_INTENT_TTL_HOURS = max(1, int(os.environ.get("STAGED_INTENT_TTL_HOURS", "72")))
# Repeating the same instruction (double-click, retry) reuses the pending proposal.
STAGED_INTENT_DEDUPE_SECONDS = max(0, int(os.environ.get("STAGED_INTENT_DEDUPE_SECONDS", "300")))


class ActionStatus(str, Enum):
    STAGED_PENDING_HITL = "STAGED_PENDING_HITL"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class StagingLedgerError(Exception):
    """Base exception for staging ledger errors."""


class IntentNotFoundError(StagingLedgerError):
    """Raised when an intent ID does not exist in the ledger."""


class IntentStateError(StagingLedgerError):
    """Raised when an action is performed on an intent in an invalid state."""


class BiometricVerificationError(StagingLedgerError):
    """Raised when a Tier 3 action lacks a verified WebAuthn passkey assertion."""


class StagingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Optional so the API layer can supply the verified tenant identity from a signed token.
    # When present it must match that identity; the route rejects mismatches.
    tenant_id: Optional[str] = Field(default=None, description="Must match the authenticated tenant")
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, TRANSFER, or PLEDGE_INVOICE")
    amount_cents: int = Field(gt=0, description="Exact integer amount in minor currency units (cents)")
    target_identifier: str = Field(min_length=1, description="Account, invoice ID, or facility ID")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    webauthn_assertion: Optional[dict[str, Any]] = Field(
        default=None,
        description="PublicKeyCredential JSON from navigator.credentials.get() over this intent's challenge",
    )


class StagingLedger:
    """Thread-safe persistent staging ledger for autonomous agent financial actions."""

    def __init__(
        self,
        passkeys: Optional[PasskeyRegistry] = None,
        storage_dir: Optional[str] = None,
    ) -> None:
        self._passkeys = passkeys or passkey_registry
        self._storage_dir = storage_dir
        self._file_path = os.path.join(self._storage_dir, "staged_intents.json") if self._storage_dir else None
        self._intents: dict[str, StagedActionIntent] = {}
        self._lock = threading.Lock()
        self._load_persisted()
        with self._lock:
            if self._purge_expired_locked():
                self._persist()

    def _load_persisted(self) -> None:
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.loads(open_text(f.read()))
                for item in data.values():
                    intent = StagedActionIntent.model_validate_json(json.dumps(item))
                    self._intents[intent.id] = intent
        except Exception as exc:
            logger.warning("Could not load persisted intents from %s: %s", self._file_path, exc)

    def _persist(self) -> None:
        if not self._file_path:
            return
        ensure_private_dir(self._storage_dir)
        tmp_path = f"{self._file_path}.tmp"
        try:
            data = {k: v.model_dump(mode="json") for k, v in self._intents.items()}
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(seal_text(json.dumps(data, indent=2)))
            os.replace(tmp_path, self._file_path)
            restrict_file(self._file_path)
        except OSError as exc:
            logger.warning("Failed to persist intents to %s: %s", self._file_path, exc)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        """Persisted/constructed timestamps may be naive; compare them as UTC."""
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _purge_expired_locked(self) -> int:
        """Drops pending intents older than the TTL. Caller must hold _lock."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STAGED_INTENT_TTL_HOURS)
        expired = [
            intent_id
            for intent_id, intent in self._intents.items()
            if intent.status == ActionStatus.STAGED_PENDING_HITL.value
            and self._aware(intent.staged_at) < cutoff
        ]
        for intent_id in expired:
            self._intents.pop(intent_id, None)
        return len(expired)

    def _find_recent_duplicate_locked(self, request: StagingRequest, tenant_id: str, now: datetime) -> Optional[StagedActionIntent]:
        """Returns an equivalent pending proposal created inside the dedupe window, if any."""
        if STAGED_INTENT_DEDUPE_SECONDS <= 0:
            return None
        cutoff = now - timedelta(seconds=STAGED_INTENT_DEDUPE_SECONDS)
        for intent in self._intents.values():
            if (
                intent.status == ActionStatus.STAGED_PENDING_HITL.value
                and intent.tenant_id == tenant_id
                and intent.action_type == request.action_type
                and intent.amount_cents == request.amount_cents
                and intent.target_identifier == request.target_identifier
                and self._aware(intent.staged_at) >= cutoff
            ):
                return intent
        return None

    def stage_intent(self, request: StagingRequest) -> StagedActionIntent:
        """Stages an action proposal in Tier 2. No money moves.

        Expired pending proposals are purged, and an identical pending proposal inside the
        dedupe window is returned instead of minting another ID for the same instruction.
        """
        tenant_id = (request.tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("A verified tenant identity is required to stage an action")
        now = datetime.now(timezone.utc)
        with self._lock:
            purged = self._purge_expired_locked()
            duplicate = self._find_recent_duplicate_locked(request, tenant_id, now)
            if duplicate is not None:
                if purged:
                    self._persist()
                return duplicate

            intent = StagedActionIntent(
                id=f"intent-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                action_type=request.action_type,
                amount_cents=request.amount_cents,
                target_identifier=request.target_identifier,
                status=ActionStatus.STAGED_PENDING_HITL.value,
                staged_at=now,
                biometric_signature=None,
            )
            self._intents[intent.id] = intent
            self._persist()
            return intent

    def get_intent(self, intent_id: str) -> StagedActionIntent:
        """Retrieves a staged intent by ID."""
        with self._lock:
            intent = self._intents.get(intent_id)
        if intent is None:
            raise IntentNotFoundError(f"Action intent {intent_id} not found")
        return intent

    def list_intents(self, tenant_id: Optional[str] = None) -> list[StagedActionIntent]:
        """Lists staged action intents, optionally filtered by tenant."""
        with self._lock:
            all_intents = list(self._intents.values())
        if tenant_id:
            return [i for i in all_intents if i.tenant_id == tenant_id]
        return all_intents

    def execute_intent(
        self, intent_id: str, webauthn_assertion: Optional[dict[str, Any]] = None
    ) -> StagedActionIntent:
        """
        Executes a staged intent.
        Tier 3 actions require a passkey assertion signed over this intent's challenge.
        """
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot execute intent in status {intent.status}")

            # Tier 2 proposals are queue-only by construction: nothing may move capital without
            # a Tier 3 biometric authorization. This blocks execution of any action type that the
            # security-gate policy does not require a passkey for.
            if not requires_biometric_execution(intent.action_type):
                raise IntentStateError(
                    f"Action '{intent.action_type}' is a Tier 2 proposal and cannot be executed"
                )

            if not webauthn_assertion:
                raise BiometricVerificationError(
                    f"Tier 3 action '{intent.action_type}' requires biometric passkey verification."
                )
            try:
                proof = self._passkeys.verify_assertion(intent.tenant_id, intent_id, webauthn_assertion)
            except PasskeyError as exc:
                raise BiometricVerificationError(
                    f"Tier 3 action '{intent.action_type}' biometric passkey verification failed: {exc}"
                ) from exc

            executed_intent = intent.model_copy(
                update={
                    "status": ActionStatus.EXECUTED.value,
                    "biometric_signature": proof,
                }
            )
            self._intents[intent_id] = executed_intent
            self._persist()
            return executed_intent

    def reject_intent(self, intent_id: str, reason: str = "Rejected by user") -> StagedActionIntent:
        """Rejects a staged intent."""
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot reject intent in status {intent.status}")

            rejected_intent = intent.model_copy(
                update={"status": ActionStatus.REJECTED.value}
            )
            self._intents[intent_id] = rejected_intent
            self._persist()
            return rejected_intent

    def clear(self) -> None:
        """Clears all intents (used for testing)."""
        with self._lock:
            self._intents.clear()
            if self._file_path and os.path.exists(self._file_path):
                try:
                    os.remove(self._file_path)
                except OSError:
                    pass


# Shared singleton instance
staging_ledger = StagingLedger(storage_dir=LEDGER_DIR)
