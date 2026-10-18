"""
Cryptographic Tenant Token Service.
Issues and verifies HMAC-SHA256 signed tenant identity tokens to eliminate
unverified client-asserted tenant spoofing while preserving backward compatibility.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TenantTokenError(Exception):
    """Base exception for tenant authentication token errors."""


class TenantTokenExpiredError(TenantTokenError):
    """Raised when a tenant token has expired."""


class TenantTokenInvalidError(TenantTokenError):
    """Raised when a tenant token has an invalid signature or structure."""


class TenantAuthenticationRequiredError(TenantTokenError):
    """Raised when a protected operation receives no signed tenant credential."""


class TenantIssuanceDeniedError(TenantTokenError):
    """Raised when a token request does not present the tenant's enrollment key."""


class TenantIssuanceUnavailableError(TenantTokenError):
    """Raised when the server has no enrollment key configured, so issuance is closed."""


_EPHEMERAL_SECRET: Optional[bytes] = None


def _signing_secret(secret: Optional[str] = None) -> bytes:
    """
    Resolves the HMAC signing secret.

    TENANT_TOKEN_SECRET is required in any shared or deployed environment. When it is absent
    (local single-process runs), a random per-process secret is generated so tokens can never be
    forged with a value published in the repository. Tokens then stop verifying after a restart,
    which is the safe failure direction.
    """
    if secret:
        return secret.encode("utf-8")

    configured = os.getenv("TENANT_TOKEN_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")

    global _EPHEMERAL_SECRET
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = secrets.token_bytes(32)
        logger.warning(
            "TENANT_TOKEN_SECRET is not set; using a random per-process signing secret. "
            "Set TENANT_TOKEN_SECRET for tokens that survive restarts."
        )
    return _EPHEMERAL_SECRET


_SINGLE_KEY_UNBOUND_WARNED = False


def authorize_token_issuance(tenant_id: str, enrollment_key: Optional[str]) -> None:
    """
    Authorizes issuing a tenant token.

    TENANT_ENROLLMENT_KEYS (JSON map of tenant_id -> key) takes precedence for multi-tenant
    deployments; TENANT_ENROLLMENT_KEY is the single-operator fallback. With neither set,
    issuance is closed rather than open, so an unauthenticated caller can never mint a token
    for an arbitrary tenant.
    """
    clean_tenant = (tenant_id or "").strip()
    if not clean_tenant:
        raise TenantIssuanceDeniedError("tenant_id is required")

    provided = (enrollment_key or "").strip()
    per_tenant_raw = os.getenv("TENANT_ENROLLMENT_KEYS", "").strip()
    single_key = os.getenv("TENANT_ENROLLMENT_KEY", "").strip()

    if per_tenant_raw:
        try:
            per_tenant = json.loads(per_tenant_raw)
        except ValueError as exc:
            raise TenantIssuanceUnavailableError("TENANT_ENROLLMENT_KEYS is not valid JSON") from exc
        if not isinstance(per_tenant, dict):
            raise TenantIssuanceUnavailableError("TENANT_ENROLLMENT_KEYS must be a JSON object")
        expected = per_tenant.get(clean_tenant)
        if not expected:
            raise TenantIssuanceDeniedError(f"Tenant {clean_tenant} is not enrolled")
        if not provided or not hmac.compare_digest(provided, str(expected)):
            raise TenantIssuanceDeniedError("Invalid enrollment key")
        return

    if single_key:
        if not provided or not hmac.compare_digest(provided, single_key):
            raise TenantIssuanceDeniedError("Invalid enrollment key")

        # A shared operator key is a master credential. It is fail-closed unless bound to one
        # tenant; TENANT_ENROLLMENT_ALLOW_ANY_TENANT is an explicit local-development escape hatch.
        bound_tenant = os.getenv("TENANT_ENROLLMENT_TENANT_ID", "").strip()
        allow_any = os.getenv("TENANT_ENROLLMENT_ALLOW_ANY_TENANT", "").strip().lower() in {"1", "true", "yes"}
        if bound_tenant:
            if not hmac.compare_digest(clean_tenant, bound_tenant):
                raise TenantIssuanceDeniedError(
                    f"Tenant {clean_tenant} is not enrolled: the single enrollment key is bound to {bound_tenant}"
                )
        elif not allow_any:
            raise TenantIssuanceUnavailableError(
                "Single-key enrollment is not bound to a tenant. Set TENANT_ENROLLMENT_TENANT_ID "
                "(one tenant), TENANT_ENROLLMENT_KEYS (many tenants), or "
                "TENANT_ENROLLMENT_ALLOW_ANY_TENANT=1 for local-only use."
            )
        else:
            global _SINGLE_KEY_UNBOUND_WARNED
            if not _SINGLE_KEY_UNBOUND_WARNED:
                _SINGLE_KEY_UNBOUND_WARNED = True
                logger.warning(
                    "TENANT_ENROLLMENT_ALLOW_ANY_TENANT is active: the single enrollment key can mint "
                    "any tenant identity. Use a tenant binding or the per-tenant map in production."
                )
        return

    raise TenantIssuanceUnavailableError(
        "Token issuance is disabled: set TENANT_ENROLLMENT_KEY or TENANT_ENROLLMENT_KEYS"
    )


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def issue_tenant_token(
    tenant_id: str,
    ttl_seconds: int = 86400 * 30,  # 30 days
    secret: Optional[str] = None,
) -> str:
    """Issues an HMAC-SHA256 signed token embedding the authenticated tenant_id."""
    clean_tenant = tenant_id.strip()
    if not clean_tenant:
        raise ValueError("tenant_id cannot be empty")

    signing_secret = _signing_secret(secret)
    now = int(time.time())
    payload = {
        "tenant_id": clean_tenant,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_payload = _b64url_encode(payload_bytes)

    signature = hmac.new(signing_secret, b64_payload.encode("utf-8"), hashlib.sha256).digest()
    b64_signature = _b64url_encode(signature)

    return f"{b64_payload}.{b64_signature}"


def verify_tenant_token(token: str, secret: Optional[str] = None) -> str:
    """
    Verifies the HMAC-SHA256 signature and expiration of a tenant token.
    Returns the verified tenant_id string.
    """
    if not token or "." not in token:
        raise TenantTokenInvalidError("Malformed tenant token format")

    parts = token.strip().split(".")
    if len(parts) != 2:
        raise TenantTokenInvalidError("Malformed tenant token format")

    b64_payload, b64_signature = parts
    signing_secret = _signing_secret(secret)

    expected_sig = hmac.new(signing_secret, b64_payload.encode("utf-8"), hashlib.sha256).digest()
    b64_expected_sig = _b64url_encode(expected_sig)

    if not hmac.compare_digest(b64_signature, b64_expected_sig):
        raise TenantTokenInvalidError("Invalid tenant token signature")

    try:
        payload_bytes = _b64url_decode(b64_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TenantTokenInvalidError(f"Corrupted token payload: {exc}") from exc

    if "tenant_id" not in payload or "exp" not in payload:
        raise TenantTokenInvalidError("Incomplete token payload")

    if time.time() > payload["exp"]:
        raise TenantTokenExpiredError("Tenant token has expired")

    return str(payload["tenant_id"])


def resolve_tenant_identity(
    x_tenant_token: Optional[str] = None,
    authorization: Optional[str] = None,
    x_tenant_id: Optional[str] = None,
) -> str:
    """
    Resolves tenant identity authoritatively:
    1. If X-Tenant-Token is provided: verifies signature; raises on forgery.
    2. Else if Authorization: Bearer <token> is provided: verifies signature; raises on forgery.
    3. Else fallback to client-asserted X-Tenant-ID (or 'SME-DEFAULT').
    """
    if x_tenant_token and x_tenant_token.strip():
        return verify_tenant_token(x_tenant_token.strip())

    if authorization and authorization.strip():
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            bearer_token = auth[7:].strip()
            if bearer_token:
                return verify_tenant_token(bearer_token)

    if x_tenant_id and x_tenant_id.strip():
        return x_tenant_id.strip()

    return "SME-DEFAULT"


def resolve_verified_tenant(
    x_tenant_token: Optional[str] = None,
    authorization: Optional[str] = None,
) -> Optional[str]:
    """Returns the verified tenant when a valid signed token is present, else None.

    Used for capabilities that are optional for anonymous callers (read-only chat) but
    must be authenticated when they mutate state (proposal staging).
    """
    try:
        return require_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
        )
    except TenantTokenError:
        return None


def require_tenant_identity(
    x_tenant_token: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    """
    Resolves a *verified* tenant identity for protected operations.

    Unlike resolve_tenant_identity, this never falls back to the client-asserted X-Tenant-ID
    header or a shared default tenant. Callers must present a signed tenant token.
    """
    if x_tenant_token and x_tenant_token.strip():
        return verify_tenant_token(x_tenant_token.strip())

    if authorization and authorization.strip():
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            bearer_token = auth[7:].strip()
            if bearer_token:
                return verify_tenant_token(bearer_token)

    raise TenantAuthenticationRequiredError(
        "A signed tenant token is required (X-Tenant-Token or Authorization: Bearer)."
    )
