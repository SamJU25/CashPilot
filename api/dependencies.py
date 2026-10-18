"""Shared FastAPI dependencies for authorization boundaries."""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, status

from services.security.tenant_token import TenantTokenError, require_tenant_identity


def require_tenant(
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """Resolves a *verified* tenant from a signed token or fails with 401."""
    try:
        return require_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
        )
    except TenantTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """
    Guards process-wide administrative operations.

    There is no role system yet, so a global decision-table reload is protected by an
    operator key instead of a tenant token. When DECISION_ADMIN_KEY is unset the operation
    is closed rather than open.
    """
    expected = os.getenv("DECISION_ADMIN_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrative operations are disabled: set DECISION_ADMIN_KEY on the server.",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key.")
