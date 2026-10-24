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


class EditAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    counterparty: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=200)


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


_LOCAL_APP = re.compile(r"^(https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d{1,5})?|tauri://localhost)(/[\w\-/]*)?$")


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


def _page(ok: bool, title: str, body: str, back: str = "", address: str = "") -> HTMLResponse:
    """The landing page shown in the browser when OAuth completes.
    Styled with CashPilot design tokens, animated status visual, account badge, and guidance."""
    theme_bg = "#080c14"
    card_bg = "#0f172a"
    border_color = "rgba(255, 255, 255, 0.08)"
    accent_color = "#10b981" if ok else "#f43f5e"
    accent_soft = "rgba(16, 185, 129, 0.12)" if ok else "rgba(244, 63, 94, 0.12)"
    status_label = "ACTIVE CONNECTION" if ok else "SIGN-IN HALTED"

    safe_title = html.escape(title)
    safe_body = html.escape(body)
    safe_back = html.escape(back)
    safe_address = html.escape(address)

    is_desktop = "tauri.localhost" in back or back.startswith("tauri://")

    if ok:
        icon_svg = """
        <div class="icon-circle success">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
        """
    else:
        icon_svg = """
        <div class="icon-circle error">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
        </div>
        """

    address_badge = ""
    if safe_address:
        address_badge = f"""
        <div class="account-pill">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="20" height="16" x="2" y="4" rx="2"></rect>
            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"></path>
          </svg>
          <span>{safe_address}</span>
        </div>
        """

    if ok:
        if is_desktop:
            guidance_html = f"""
            <div class="guidance-box">
              <div class="guidance-header">
                <span class="live-dot"></span>
                <span class="guidance-title">Ready in Desktop App</span>
              </div>
              <p class="guidance-text">CashPilot is active and syncing in your desktop application. Click below to close this tab and resume in CashPilot.</p>
            </div>
            <div class="actions">
              <button onclick="closeOrSwitch()" class="btn-primary" id="action-btn">
                Close This Window
              </button>
              {f'<a href="{safe_back}" class="btn-secondary">Back to CashPilot</a>' if safe_back else ''}
              <p id="switch-hint" style="display:none;font-size:0.75rem;color:#94a3b8;margin-top:0.4rem;">
                Tab still open? Switch back to the CashPilot desktop window on your taskbar (or press Alt+Tab).
              </p>
            </div>
            """
        elif back:
            guidance_html = f"""
            <div class="guidance-box">
              <div class="guidance-header">
                <span class="live-dot"></span>
                <span class="guidance-title" id="countdown-label">Redirecting in 3 seconds...</span>
              </div>
              <div class="progress-track"><div class="progress-fill"></div></div>
            </div>
            <div class="actions">
              <a href="{safe_back}" class="btn-primary" id="action-btn">Back to CashPilot</a>
              <button onclick="window.close()" class="btn-secondary">Close Tab</button>
            </div>
            """
        else:
            guidance_html = """
            <div class="guidance-box">
              <p class="guidance-text">CashPilot has linked your mailbox. You can return to the CashPilot application.</p>
            </div>
            <div class="actions">
              <button onclick="window.close()" class="btn-primary">Close Window</button>
            </div>
            """
    else:
        guidance_html = f"""
        <div class="actions">
          {f'<a href="{safe_back}" class="btn-primary">Back to CashPilot</a>' if safe_back else ''}
          <button onclick="window.close()" class="btn-secondary">Close Window</button>
        </div>
        """

    script_html = ""
    if ok:
        if is_desktop:
            script_html = """
            <script>
              function closeOrSwitch() {
                window.close();
                setTimeout(() => {
                  const btn = document.getElementById('action-btn');
                  if (btn) btn.innerText = "Switch to CashPilot Window";
                }, 400);
              }
              setTimeout(() => { window.close(); }, 2500);
            </script>
            """
        elif back:
            script_html = f"""
            <script>
              let count = 3;
              const lbl = document.getElementById('countdown-label');
              const interval = setInterval(() => {{
                count--;
                if (lbl && count > 0) lbl.innerText = "Redirecting in " + count + " second" + (count === 1 ? "" : "s") + "...";
                if (count <= 0) {{
                  clearInterval(interval);
                  window.location.href = "{safe_back}";
                }}
              }}, 1000);
            </script>
            """

    full_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CashPilot — Mailbox Connection</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: {theme_bg};
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      background-image: radial-gradient(circle at 50% 20%, {accent_soft}, transparent 55%);
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 1.75rem;
      text-decoration: none;
    }}
    .brand-logo {{
      width: 28px;
      height: 28px;
      background: linear-gradient(135deg, #06b6d4, #10b981);
      border-radius: 8px;
      display: grid;
      place-items: center;
      box-shadow: 0 0 16px rgba(16, 185, 129, 0.35);
    }}
    .brand-title {{
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #f8fafc;
    }}
    .brand-sub {{
      font-size: 0.75rem;
      color: #64748b;
      margin-left: 0.25rem;
      font-weight: 500;
    }}
    .card {{
      width: 100%;
      max-width: 440px;
      background: {card_bg};
      border: 1px solid {border_color};
      border-radius: 20px;
      padding: 2.25rem 2rem;
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05);
      text-align: center;
      animation: enter 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    @keyframes enter {{
      from {{ opacity: 0; transform: translateY(12px) scale(0.98); }}
      to {{ opacity: 1; transform: translateY(0) scale(1); }}
    }}
    .icon-circle {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      margin: 0 auto 1.25rem;
    }}
    .icon-circle.success {{
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      box-shadow: 0 0 24px rgba(16, 185, 129, 0.2);
    }}
    .icon-circle.error {{
      background: rgba(244, 63, 94, 0.12);
      border: 1px solid rgba(244, 63, 94, 0.3);
      box-shadow: 0 0 24px rgba(244, 63, 94, 0.2);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: {accent_soft};
      color: {accent_color};
      border: 1px solid rgba(255, 255, 255, 0.06);
      margin-bottom: 0.75rem;
    }}
    h1 {{
      font-size: 1.35rem;
      font-weight: 600;
      letter-spacing: -0.015em;
      color: #f1f5f9;
      margin-bottom: 0.5rem;
    }}
    p.desc {{
      font-size: 0.9rem;
      line-height: 1.55;
      color: #94a3b8;
      margin-bottom: 1.25rem;
    }}
    .account-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.85rem;
      border-radius: 9999px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.82rem;
      color: #cbd5e1;
      margin-bottom: 1.5rem;
    }}
    .guidance-box {{
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 12px;
      padding: 1rem 1.15rem;
      margin-bottom: 1.5rem;
      text-align: left;
    }}
    .guidance-header {{
      display: flex;
      align-items: center;
      gap: 0.45rem;
      margin-bottom: 0.35rem;
    }}
    .live-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.4; transform: scale(0.9); }}
    }}
    .guidance-title {{
      font-size: 0.78rem;
      font-weight: 600;
      color: #e2e8f0;
    }}
    .guidance-text {{
      font-size: 0.8rem;
      line-height: 1.5;
      color: #94a3b8;
    }}
    .progress-track {{
      width: 100%;
      height: 3px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 9999px;
      margin-top: 0.75rem;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, #06b6d4, #10b981);
      width: 100%;
      animation: progress 3s linear forwards;
    }}
    @keyframes progress {{
      from {{ width: 0%; }}
      to {{ width: 100%; }}
    }}
    .actions {{
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    .btn-primary {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      width: 100%;
      padding: 0.75rem 1rem;
      border-radius: 10px;
      font-size: 0.88rem;
      font-weight: 500;
      background: #f8fafc;
      color: #0b0f14;
      text-decoration: none;
      border: none;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .btn-primary:hover {{
      background: #ffffff;
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(255, 255, 255, 0.15);
    }}
    .btn-secondary {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      padding: 0.65rem 1rem;
      border-radius: 10px;
      font-size: 0.84rem;
      font-weight: 500;
      background: transparent;
      color: #94a3b8;
      text-decoration: none;
      border: 1px solid rgba(255, 255, 255, 0.08);
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .btn-secondary:hover {{
      background: rgba(255, 255, 255, 0.04);
      color: #e2e8f0;
      border-color: rgba(255, 255, 255, 0.15);
    }}
  </style>
</head>
<body>
  <div class="brand">
    <div class="brand-logo">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
        <polyline points="2 17 12 22 22 17"></polyline>
        <polyline points="2 12 12 17 22 12"></polyline>
      </svg>
    </div>
    <span class="brand-title">CashPilot</span>
    <span class="brand-sub">Autonomous AI Financial Participant</span>
  </div>

  <main class="card">
    {icon_svg}
    <div class="badge">{status_label}</div>
    <h1>{safe_title}</h1>
    <p class="desc">{safe_body}</p>
    {address_badge}
    {guidance_html}
  </main>
  {script_html}
</body>
</html>"""

    return HTMLResponse(full_html, status_code=200 if ok else 400)


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(state: str = "", code: str = "", error: str = "") -> HTMLResponse:
    """Where Google or Microsoft send the browser after sign-in. Not tenant-authenticated: the
    single-use state from oauth_start is what ties this answer to the tenant that asked."""
    try:
        pending = oauth.take(state)
    except oauth.OAuthError as exc:
        return _page(False, "Sign-in did not finish", str(exc))
    if error or not code:
        return _page(False, "Sign-in was cancelled", "Nothing was connected. You can try again from CashPilot.", pending.return_to, pending.address)
    try:
        access, refresh = await run_in_threadpool(oauth.exchange, pending, code)
        s = pending.server
        box = await run_in_threadpool(open_mailbox, s["host"], s["port"], s["username"], access, True)
        await run_in_threadpool(box.logout)
    except oauth.OAuthError as exc:
        return _page(False, "Sign-in did not finish", str(exc), pending.return_to, pending.address)
    except MailError as exc:
        return _page(False, "Signed in, but the mailbox did not open", str(exc), pending.return_to, pending.address)
    with tenant_lock(pending.tenant):
        store = MailStore(pending.tenant)
        store.connect(pending.address, pending.server, refresh, oauth=pending.provider)
        store.save()
    try:
        await run_sync(pending.tenant)
    except Exception:
        pass  # connected; the first read's error shows in the app
    return _page(True, "Connected", f"CashPilot can now read bank alerts in {pending.address}.", pending.return_to, pending.address)


@router.get("/state")
def state(tenant: str = Depends(require_tenant)) -> dict:
    return MailStore(tenant).view()


@router.post("/connect")
async def connect(payload: ConnectRequest, tenant: str = Depends(require_tenant)) -> dict:
    host = payload.host.lower()
    clean_secret = payload.secret.strip()
    if "gmail" in host or "google" in host:
        clean_secret = clean_secret.replace(" ", "")
    try:
        # Test before saving: a wrong password is never stored.
        box = await run_in_threadpool(open_mailbox, host, payload.port, payload.username, clean_secret)
        await run_in_threadpool(box.logout)
    except MailError as exc:
        raise _fail(exc)
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.connect(payload.address, {"host": host, "port": payload.port, "username": payload.username, "name": payload.name or host}, clean_secret)
        store.save()
    try:
        return await run_sync(tenant)
    except HTTPException:
        # Connected; the first read failed and the error is on the connection for the app to show.
        return MailStore(tenant).view()


@router.delete("/connect")
def disconnect(address: Optional[str] = None, tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        store.disconnect(address)
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


@router.patch("/alerts/{alert_id}")
def edit_alert(alert_id: str, payload: EditAlertRequest, tenant: str = Depends(require_tenant)) -> dict:
    with tenant_lock(tenant):
        store = MailStore(tenant)
        if not any(a["id"] == alert_id for a in store.data["alerts"]):
            raise HTTPException(status_code=404, detail={"code": "unknown_alert", "message": "No such alert."})
        store.edit_alert(alert_id, payload.counterparty, payload.note)
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
