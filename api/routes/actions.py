"""
FastAPI router for Three-Tier Security Gate and Staged Action Intents.
Drafted actions are staged here and end in the owner's decision: prepare (they send the request
themselves) or dismiss. CashPilot has no bank or lender connection, so nothing is ever executed.

Every route is scoped to a verified tenant identity. The client-asserted X-Tenant-ID header is
never trusted here: callers must present a signed tenant token (X-Tenant-Token or Bearer).
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from services.security.staging_ledger import (
    staging_ledger,
    StagingRequest,
    StagedActionIntent,
    IntentNotFoundError,
    IntentStateError,
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


@router.get("", response_model=list[StagedActionIntent])
async def list_action_intents(
    tenant: str = Depends(require_tenant),
) -> list[StagedActionIntent]:
    """Lists the authenticated tenant's drafted actions and the owner's decisions on them."""
    return staging_ledger.list_intents(tenant_id=tenant)


@router.get("/{intent_id}", response_model=StagedActionIntent)
async def get_action_intent(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Retrieves a specific staged action intent owned by the authenticated tenant."""
    return _load_owned_intent(intent_id, tenant)


@router.post("/{intent_id}/prepare", response_model=StagedActionIntent)
async def prepare_action_intent(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Records that the owner took the prepared request to send it themselves. Nothing is sent."""
    _load_owned_intent(intent_id, tenant)
    try:
        return staging_ledger.prepare_intent(intent_id)
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{intent_id}/reject", response_model=StagedActionIntent)
async def reject_action_intent(
    intent_id: str,
    tenant: str = Depends(require_tenant),
) -> StagedActionIntent:
    """Records that the owner dismissed the drafted action."""
    _load_owned_intent(intent_id, tenant)
    try:
        return staging_ledger.reject_intent(intent_id)
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
