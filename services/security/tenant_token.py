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
import os
import time
from typing import Optional


class TenantTokenError(Exception):
    """Base exception for tenant authentication token errors."""


class TenantTokenExpiredError(TenantTokenError):
    """Raised when a tenant token has expired."""


class TenantTokenInvalidError(TenantTokenError):
    """Raised when a tenant token has an invalid signature or structure."""


DEFAULT_SECRET = os.getenv("TENANT_TOKEN_SECRET", "sme-copilot-dev-secret-key-32bytes!")


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

    signing_secret = (secret or DEFAULT_SECRET).encode("utf-8")
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
    signing_secret = (secret or DEFAULT_SECRET).encode("utf-8")

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
