"""
Authentication and Tenant Token Router.
Issues and validates HMAC-SHA256 signed tenant identity tokens.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.security.tenant_token import (
    TenantIssuanceDeniedError,
    TenantIssuanceUnavailableError,
    TenantTokenError,
    authorize_token_issuance,
    issue_tenant_token,
    resolve_tenant_identity,
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
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> VerifyResponse:
    try:
        resolved = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
        return VerifyResponse(valid=True, tenant_id=resolved)
    except TenantTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid tenant authentication token: {exc}",
        )
