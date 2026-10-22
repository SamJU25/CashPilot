"""Plaid Open Banking API Routes.
Manages Link token lifecycle, public token exchange, multi-account sync, and webhook events.
Strictly Tier 1 (Read-Only Observation).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.routes.analyze import CashAnalysisResponse
from services.plaid.client import PlaidError, plaid_client
from services.plaid.storage import plaid_storage
from services.plaid.sync import sync_plaid_accounts_for_tenant
from services.agent.session_store import session_store
from services.security.tenant_token import TenantTokenError, resolve_tenant_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plaid", tags=["Plaid Open Banking"])


class LinkTokenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_name: Optional[str] = "CashPilot"


class ExchangeTokenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    public_token: str
    institution_name: Optional[str] = "Connected Bank"
    institution_id: Optional[str] = None
    accounts: Optional[list[dict[str, Any]]] = None


class ExchangeTokenResponse(BaseModel):
    success: bool
    item_id: str
    institution_name: str
    analysis: CashAnalysisResponse
    accounts: list[dict[str, Any]]


class PlaidConfigPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_id: str
    secret: str
    env: Optional[str] = "sandbox"


class PlaidWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    webhook_type: Optional[str] = None
    webhook_code: Optional[str] = None
    item_id: Optional[str] = None
    error: Optional[Any] = None


@router.get("/status")
async def get_plaid_status() -> dict[str, Any]:
    """Returns Plaid live connection configuration status."""
    return {
        "configured": plaid_client.is_live,
        "env": plaid_client.env,
        "client_id_prefix": plaid_client.client_id[:4] + "..." if plaid_client.client_id else None,
    }


@router.post("/config", response_model=None)
async def save_plaid_config(
    req: PlaidConfigPayload,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict[str, Any] | JSONResponse:
    """Configures Plaid credentials for connecting real bank accounts."""
    try:
        resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    plaid_client.configure(client_id=req.client_id, secret=req.secret, env=req.env or "sandbox")
    return {
        "success": True,
        "configured": plaid_client.is_live,
        "env": plaid_client.env,
    }


@router.post("/link-token", response_model=None)
async def create_link_token(
    req: LinkTokenRequest,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict[str, Any] | JSONResponse:
    """Creates a Plaid Link token for embedded frontend authentication."""
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    user_id = effective_tenant or x_session_id or "sme-user-default"
    try:
        data = await plaid_client.create_link_token(
            client_user_id=user_id,
            client_name=req.client_name or "CashPilot",
        )
        return data
    except PlaidError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.message}},
        )


@router.post("/exchange-token", response_model=None)
async def exchange_public_token(
    req: ExchangeTokenRequest,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> ExchangeTokenResponse | JSONResponse:
    """Exchanges a public_token from Plaid Link modal, stores the encrypted item,
    and returns initial synced CashAnalysisResponse.
    """
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    try:
        exchange_res = await plaid_client.exchange_public_token(req.public_token)
        item_id = exchange_res["item_id"]
        access_token = exchange_res["access_token"]

        # Fetch accounts if not passed
        accounts = req.accounts
        if not accounts:
            accounts = await plaid_client.get_accounts(access_token)

        plaid_storage.save_item(
            tenant_id=effective_tenant,
            item_id=item_id,
            access_token=access_token,
            institution_name=req.institution_name or "Connected Bank",
            institution_id=req.institution_id or "ins_default",
            accounts=accounts,
        )

        analysis, all_accounts = await sync_plaid_accounts_for_tenant(tenant_id=effective_tenant)

        # Update session store if session ID is provided
        if x_session_id:
            try:
                session_store.update_statement(
                    session_id=x_session_id,
                    csv_content=f"# Plaid live sync item {item_id}\n",
                    tenant_id=effective_tenant,
                )
            except Exception:
                pass

        return ExchangeTokenResponse(
            success=True,
            item_id=item_id,
            institution_name=req.institution_name or "Connected Bank",
            analysis=analysis,
            accounts=all_accounts,
        )
    except PlaidError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.message}},
        )
    except Exception as exc:
        logger.exception("Plaid token exchange error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "EXCHANGE_FAILED", "message": str(exc)}},
        )


@router.get("/accounts", response_model=None)
async def list_connected_accounts(
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict[str, Any] | JSONResponse:
    """Lists all connected bank institutions and accounts for the tenant."""
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    items = plaid_storage.get_items(effective_tenant)
    sanitized_items = []
    for it in items:
        sanitized_items.append({
            "item_id": it.get("item_id"),
            "institution_name": it.get("institution_name"),
            "institution_id": it.get("institution_id"),
            "connected_at": it.get("connected_at"),
            "last_synced_at": it.get("last_synced_at"),
            "status": it.get("status"),
            "accounts": [
                {
                    "account_id": a.get("account_id"),
                    "name": a.get("name"),
                    "official_name": a.get("official_name"),
                    "type": a.get("type"),
                    "subtype": a.get("subtype"),
                    "balance": a.get("balances", {}).get("current"),
                    "currency": a.get("balances", {}).get("iso_currency_code", "USD"),
                }
                for a in it.get("accounts", [])
            ],
        })

    return {
        "items": sanitized_items,
        "connected_institutions": len(sanitized_items),
        "total_accounts": sum(len(it.get("accounts", [])) for it in sanitized_items),
        "sandbox_simulated": not plaid_client.is_live,
    }


@router.post("/sync", response_model=None)
async def trigger_accounts_sync(
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> CashAnalysisResponse | JSONResponse:
    """Refreshes balances and transactions across all connected accounts."""
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    try:
        analysis, _ = await sync_plaid_accounts_for_tenant(tenant_id=effective_tenant)
        return analysis
    except PlaidError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.message}},
        )


@router.delete("/items/{item_id}", response_model=None)
async def disconnect_institution(
    item_id: str,
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> dict[str, Any] | JSONResponse:
    """Disconnects a bank institution and removes its access token."""
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    removed = plaid_storage.remove_item(tenant_id=effective_tenant, item_id=item_id)
    if not removed:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "ITEM_NOT_FOUND", "message": f"Bank connection {item_id} not found."}},
        )

    return {"success": True, "item_id": item_id, "message": "Bank connection disconnected."}


@router.post("/webhook")
async def handle_plaid_webhook(payload: PlaidWebhookPayload) -> dict[str, Any]:
    """Handles Plaid real-time webhook events (e.g. SYNC_UPDATES_AVAILABLE)."""
    logger.info("Received Plaid webhook: %s / %s for item %s", payload.webhook_type, payload.webhook_code, payload.item_id)
    return {"received": True, "status": "ACK"}
