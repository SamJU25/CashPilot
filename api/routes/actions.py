"""
FastAPI router for Three-Tier Security Gate and Staged Action Intents.
Manages Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.

Every route is scoped to a verified tenant identity. The client-asserted X-Tenant-ID header is
never trusted here: callers must present a signed tenant token (X-Tenant-Token or Bearer).
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status

from services.security.passkeys import (
    passkey_registry,
    PasskeyError,
    PasskeyAlreadyRegisteredError,
    PasskeyNotRegisteredError,
    PasskeyOptionsRequest,
    PasskeyRegistrationRequest,
)
from services.security.staging_ledger import (
    staging_ledger,
    StagingRequest,
    ExecutionRequest,
    StagedActionIntent,
    ActionStatus,
    IntentNotFoundError,
    IntentStateError,
    BiometricVerificationError,
)
from api.dependencies import require_tenant

router = APIRouter(prefix="/api/v1/actions", tags=["Security Gate & Action Intents"])


def _assert_same_tenant(claimed: Optional[str], authenticated: str) -> None:
    """Rejects bodies/query parameters that try to act on behalf of another tenant."""
    if claimed and claimed.strip() and claimed.strip() != authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant identity mismatch: the signed token does not authorize this tenant.",
        )


def _load_owned_intent(intent_id: str, tenant: str) -> StagedActionIntent:
    """Loads an intent only if it belongs to the authenticated tenant (404 otherwise)."""
    try:
        intent = staging_ledger.get_intent(intent_id)
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if intent.tenant_id != tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action intent {intent_id} not found",
        )
    return intent


@router.post("/stage", response_model=StagedActionIntent, status_code=status.HTTP_201_CREATED)
async def stage_action_intent(
    request: StagingRequest,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Stages an action proposal in Tier 2 for the authenticated tenant. No funds move."""
    _assert_same_tenant(request.tenant_id, tenant)
    scoped = request.model_copy(update={"tenant_id": tenant})
    return staging_ledger.stage_intent(scoped)


@router.post("/passkeys/register/options")
async def passkey_registration_options(
    request: PasskeyOptionsRequest,
    tenant: str = Depends(require_tenant),
) -> Response:
    """Issues WebAuthn creation options for the authenticated tenant's Tier 3 passkey."""
    _assert_same_tenant(request.tenant_id, tenant)
    try:
        options = passkey_registry.registration_options(tenant)
    except PasskeyAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return Response(content=options, media_type="application/json")


@router.post("/passkeys/register", status_code=status.HTTP_201_CREATED)
async def register_passkey(
    request: PasskeyRegistrationRequest,
    tenant: str = Depends(require_tenant),
) -> dict[str, bool]:
    """Verifies the attestation from navigator.credentials.create() and stores the public key."""
    _assert_same_tenant(request.tenant_id, tenant)
    try:
        passkey_registry.register(tenant, request.credential)
    except PasskeyAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except PasskeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"registered": True}


@router.get("", response_model=list[StagedActionIntent])
async def list_action_intents(
    tenant: str = Depends(require_tenant),
) -> list[StagedActionIntent]:
    """Lists the authenticated tenant's staged proposals and execution records."""
    return staging_ledger.list_intents(tenant_id=tenant)


@router.get("/{intent_id}", response_model=StagedActionIntent)
async def get_action_intent(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Retrieves a specific staged action intent owned by the authenticated tenant."""
    return _load_owned_intent(intent_id, tenant)


@router.post("/{intent_id}/passkey-options")
async def intent_passkey_options(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> Response:
    """
    Issues a single-use WebAuthn challenge bound to this intent.
    428 means the tenant has no passkey yet and must register one first.
    """
    intent = _load_owned_intent(intent_id, tenant)
    if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot sign intent in status {intent.status}",
        )
    try:
        options = passkey_registry.authentication_options(intent.tenant_id, intent_id)
    except PasskeyNotRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail=str(exc))
    return Response(content=options, media_type="application/json")


@router.post("/{intent_id}/execute", response_model=StagedActionIntent)
async def execute_action_intent(
    intent_id: str,
    request: Optional[ExecutionRequest] = None,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """
    Executes a staged proposal owned by the authenticated tenant.
    Tier 3 irreversible actions require a WebAuthn assertion over the intent's challenge.
    """
    _load_owned_intent(intent_id, tenant)
    assertion = request.webauthn_assertion if request else None
    try:
        return staging_ledger.execute_intent(intent_id, webauthn_assertion=assertion)
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except BiometricVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/{intent_id}/reject", response_model=StagedActionIntent)
async def reject_action_intent(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Rejects a staged proposal owned by the authenticated tenant."""
    _load_owned_intent(intent_id, tenant)
    try:
        return staging_ledger.reject_intent(intent_id)
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
