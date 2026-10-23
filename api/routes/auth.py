"""
Authentication and Tenant Token Router.
Issues and validates HMAC-SHA256 signed tenant identity tokens.
"""

from __future__ import annotations

from typing import Optional
import os
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from services.security.tenant_token import (
    TenantIssuanceDeniedError,
    TenantIssuanceUnavailableError,
    TenantTokenError,
    authorize_token_issuance,
    issue_tenant_token,
    require_tenant_identity,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Tenant Authentication"])


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1, description="Tenant identifier to issue token for")
    ttl_seconds: Optional[int] = Field(default=86400 * 30, ge=60, description="Token TTL in seconds")


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    access_token: str
    token_type: str = "Bearer"
    tenant_id: str
    expires_in: int


class VerifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    valid: bool
    tenant_id: str


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue Signed Tenant Token",
    description=(
        "Generates an HMAC-SHA256 signed identity token. Requires the tenant's enrollment key "
        "(X-Enrollment-Key) so identities cannot be self-asserted."
    ),
)
async def create_tenant_token(
    request: TokenRequest,
    x_enrollment_key: Optional[str] = Header(default=None, alias="X-Enrollment-Key"),
) -> TokenResponse:
    try:
        authorize_token_issuance(request.tenant_id, x_enrollment_key)
    except TenantIssuanceDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except TenantIssuanceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    ttl = request.ttl_seconds or (86400 * 30)
    token = issue_tenant_token(tenant_id=request.tenant_id, ttl_seconds=ttl)
    return TokenResponse(
        access_token=token,
        token_type="Bearer",
        tenant_id=request.tenant_id,
        expires_in=ttl,
    )


@router.get(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Tenant Token",
    description="Verifies the cryptographic signature and expiration of a tenant token.",
)
async def verify_token(
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> VerifyResponse:
    try:
        resolved = require_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
        )
        return VerifyResponse(valid=True, tenant_id=resolved)
    except TenantTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid tenant authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/local-session",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue Desktop / Localhost Session Token",
    description="Allows local desktop application loopback sessions to obtain an authenticated tenant token.",
)
async def local_session_token(request: Request) -> TokenResponse:
    client_host = request.client.host if request.client else ""
    is_loopback = client_host in ("127.0.0.1", "::1", "localhost") or not client_host
    open_session = os.getenv("CASHPILOT_OPEN_SESSION", "").strip() in ("1", "true", "yes")

    if not is_loopback and not open_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local session token issuance only permitted from loopback interface."
        )

    tenant_id = os.getenv("TENANT_ENROLLMENT_TENANT_ID", "SME-LOCAL-DEV").strip()
    ttl = 86400 * 30
    token = issue_tenant_token(tenant_id=tenant_id, ttl_seconds=ttl)
    return TokenResponse(
        access_token=token,
        token_type="Bearer",
        tenant_id=tenant_id,
        expires_in=ttl,
    )
