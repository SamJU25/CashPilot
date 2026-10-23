"""Bank alert emails: connect a read-only alerts mailbox, sync it, and decide what its alerts mean.

Tier 1 (read-only) only: nothing here can send mail, move money or change the mailbox.
"""

from __future__ import annotations

import html
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import require_tenant
from services.mail.banks import BANKS
from services.mail.discover import discover, secret_kind, stamps_auth_results
from services.mail import oauth
from services.mail.store import MailStore, tenant_lock
from services.mail.sync import MailError, open_mailbox, sync

router = APIRouter(prefix="/api/v1/mail", tags=["Bank alert emails"])

_DOMAIN = r"^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,6}$"


_ADDRESS = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(pattern=_ADDRESS, max_length=254)


class ConnectRequest(BaseModel):
    """Settings come from discovery or from the owner's manual entry; TLS on connect is the only mode."""

    model_config = ConfigDict(extra="forbid")
    address: str = Field(pattern=_ADDRESS, max_length=254)
    secret: str = Field(min_length=4, max_length=256)
    host: str = Field(pattern=_DOMAIN, max_length=253)
    port: int = Field(default=993, ge=993, le=993)  # IMAPS only; see sync.open_mailbox
    username: str = Field(min_length=1, max_length=254)
    name: str = Field(default="", max_length=60)


class AccountDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "use", "ignore"]
    target: Optional[str] = Field(default=None, max_length=120)


class AlertDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "dismiss", "trust"]


class BankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str = Field(pattern=_DOMAIN)
    name: str = Field(min_length=1, max_length=60)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


def _fail(exc: MailError) -> HTTPException:
    return HTTPException(status_code=400 if exc.code != "unreachable" else 502, detail={"code": exc.code, "message": str(exc)})


@router.get("/banks")
def banks(tenant: str = Depends(require_tenant)) -> dict:
    return {"banks": [{"domain": d, "name": b.name, "currency": b.currency} for d, b in BANKS.items()]}


@router.post("/discover")
async def find_settings(payload: DiscoverRequest, tenant: str = Depends(require_tenant)) -> dict:
    """The IMAP settings for an address, found as Thunderbird finds them; null when none were found."""
    found = await run_in_threadpool(discover, payload.address.strip())
    if not found:
        return {"settings": None}
    provider = oauth.provider_for(found.host)
    return {
        "settings": {
            **found.as_dict(),
            "verifies_sender": stamps_auth_results(found.host),
            "secret_kind": secret_kind(found.host),
            # Browser sign-in, when this computer has the provider's app registration.
            "oauth": provider if provider and oauth.configured(provider) else None,
        }
    }


class OAuthStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(pattern=_ADDRESS, max_length=254)
    host: str = Field(pattern=_DOMAIN, max_length=253)
    username: str = Field(min_length=1, max_length=254)
    name: str = Field(default="", max_length=60)
    # The app page to send the owner back to; only a local CashPilot address is kept (no open redirect).
    return_to: str = Field(default="", max_length=300)


_LOCAL_APP = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d{1,5})?/[\w\-/]*$")


@router.post("/oauth/start")
def oauth_start(payload: OAuthStart, request: Request, tenant: str = Depends(require_tenant)) -> dict:
    """The provider's sign-in page for the app to open in the browser."""
    provider = oauth.provider_for(payload.host.lower())
    if not provider:
        raise HTTPException(status_code=400, detail={"code": "no_oauth", "message": "This mail server has no browser sign-in."})
    server = {"host": payload.host.lower(), "port": 993, "username": payload.username, "name": payload.name or oauth.PROVIDERS[provider].label}
    try:
        back = payload.return_to if _LOCAL_APP.match(payload.return_to) else ""
        url = oauth.start(tenant, provider, payload.address, server, request.url.port or 80, back)
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    return {"url": url}


def _page(ok: bool, title: str, body: str, back: str = "") -> HTMLResponse:
    """The tab the provider sends the owner back to; it only says what happened and to return to the app."""
    color = "#0e9f6e" if ok else "#c2410c"
    return HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CashPilot</title><style>body{{font:15px/1.5 system-ui,sans-serif;background:#0b0f14;color:#e6edf3;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{max-width:28rem;padding:2rem;border:1px solid #243041;border-radius:12px;background:#111821}}h1{{font-size:1.15rem;margin:0 0 .5rem;color:{color}}}p{{margin:0;color:#9fb0c3}}a{{display:inline-block;margin-top:1.25rem;color:#5ccfe6}}</style></head>
<body><main><h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>{f'<a href="{html.escape(back)}">Back to CashPilot</a>' if back else ''}</main>{"<script>setTimeout(()=>window.close(),1500)</script>" if ok else ""}</body></html>""",
        status_code=200 if ok else 400,
    )


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(state: str = "", code: str = "", error: str = "") -> HTMLResponse:
    """Where Google or Microsoft send the browser after sign-in. Not tenant-authenticated: the
    single-use state from oauth_start is what ties this answer to the tenant that asked."""
    try:
        pending = oauth.take(state)
    except oauth.OAuthError as exc:
        return _page(False, "Sign-in did not finish", str(exc))
    if error or not code:
        return _page(False, "Sign-in was cancelled", "Nothing was connected. You can try again from CashPilot.", pending.return_to)
    try:
        access, refresh = await run_in_threadpool(oauth.exchange, pending, code)
        s = pending.server
        box = await run_in_threadpool(open_mailbox, s["host"], s["port"], s["username"], access, True)
        await run_in_threadpool(box.logout)
    except oauth.OAuthError as exc:
        return _page(False, "Sign-in did not finish", str(exc), pending.return_to)
    except MailError as exc:
        return _page(False, "Signed in, but the mailbox did not open", str(exc), pending.return_to)
    with tenant_lock(pending.tenant):
        store = MailStore(pending.tenant)
        store.connect(pending.address, pending.server, refresh, oauth=pending.provider)
        store.save()
    try:
        await run_sync(pending.tenant)
    except Exception:
        pass  # connected; the first read's error shows in the app
    return _page(True, "Connected", f"CashPilot can now read bank alerts in {pending.address}.", pending.return_to)


@router.get("/state")
def state(tenant: str = Depends(require_tenant)) -> dict:
    return MailStore(tenant).view()


@router.post("/connect")
async def connect(payload: ConnectRequest, tenant: str = Depends(require_tenant)) -> dict:
    host = payload.host.lower()
    try:
        # Test before saving: a wrong password is never stored.
        box = await run_in_threadpool(open_mailbox, host, payload.port, payload.username, payload.secret)
        await run_in_threadpool(box.logout)
    except MailError as exc:
        raise _fail(exc)
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.connect(payload.address, {"host": host, "port": payload.port, "username": payload.username, "name": payload.name or host}, payload.secret)
        store.save()
    try:
        return await run_sync(tenant)
    except HTTPException:
        # Connected; the first read failed and the error is on the connection for the app to show.
        return MailStore(tenant).view()


@router.delete("/connect")
def disconnect(tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.disconnect()
        store.save()
        return store.view()


@router.post("/sync")
async def run_sync(tenant: str = Depends(require_tenant)) -> dict:
    def work() -> dict:
        with tenant_lock(tenant):
            store = MailStore(tenant)
            try:
                result = sync(store)
            except MailError as exc:
                if store.data["connection"]:
                    store.data["connection"]["last_error"] = exc.code
                    store.save()
                raise
            store.save()
            return {**store.view(), "result": result}

    try:
        return await run_in_threadpool(work)
    except MailError as exc:
        raise _fail(exc)


@router.put("/accounts/{key}")
def decide_account(key: str, payload: AccountDecision, tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        if key not in store.data["accounts"]:
            raise HTTPException(status_code=404, detail={"code": "unknown_account", "message": "No such account."})
        store.decide_account(key, payload.status, payload.target)
        store.save()
        return store.view()


@router.put("/alerts/{alert_id}")
def decide_alert(alert_id: str, payload: AlertDecision, tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        if not any(a["id"] == alert_id for a in store.data["alerts"]):
            raise HTTPException(status_code=404, detail={"code": "unknown_alert", "message": "No such alert."})
        store.resolve_alert(alert_id, payload.action)
        store.save()
        return store.view()


@router.post("/banks")
def add_bank(payload: BankRequest, tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.data["banks"][payload.domain.lower()] = {"name": payload.name.strip(), "currency": payload.currency}
        # Re-read from the start so mail from this bank that arrived earlier is picked up.
        store.data["cursor"] = {}
        store.save()
        return store.view()


@router.delete("/banks/{domain}")
def remove_bank(domain: str, tenant: str = Depends(require_tenant)) -> dict:
    if not re.match(_DOMAIN, domain.lower()):
        raise HTTPException(status_code=400, detail={"code": "bad_domain", "message": "Not a domain."})
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.data["banks"].pop(domain.lower(), None)
        store.save()
        return store.view()
