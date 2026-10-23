"""Browser sign-in for Gmail and Outlook alert mailboxes, as Thunderbird does it.

The owner signs in on Google's or Microsoft's own page; CashPilot never sees the password. The provider
redirects back to this computer's backend with a one-time code, which is exchanged (with PKCE) for a
refresh token. Only that token is kept, in the OS credential store, and turned into short-lived access
tokens for IMAP (SASL XOAUTH2).

The app registrations are the owner's (see docs/bank-emails-oauth.md); their ids come from the
environment, so nothing here works until they are set.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import NamedTuple, Optional
from urllib.parse import urlencode

import httpx

PENDING_TTL_S = 600


class OAuthProvider(NamedTuple):
    label: str
    hosts: tuple[str, ...]
    authorize_url: str
    token_url: str
    scope: str
    client_id_env: str
    client_secret_env: Optional[str]  # Google desktop clients send one (it is not secret); Microsoft public clients do not
    loopback: str  # Google wants 127.0.0.1; Microsoft's portal registers localhost


def _ms_tenant() -> str:
    return os.getenv("MICROSOFT_OAUTH_TENANT", "common").strip() or "common"


PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        "Google",
        ("imap.gmail.com",),
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://mail.google.com/",  # the only Google scope that allows IMAP
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "127.0.0.1",
    ),
    "microsoft": OAuthProvider(
        "Microsoft",
        ("outlook.office365.com", "imap-mail.outlook.com"),
        "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
        "MICROSOFT_OAUTH_CLIENT_ID",
        None,
        "localhost",
    ),
}

CALLBACK_PATH = "/api/v1/mail/oauth/callback"


class OAuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def provider_for(host: str) -> Optional[str]:
    return next((k for k, p in PROVIDERS.items() if host in p.hosts), None)


def configured(name: str) -> bool:
    return bool(os.getenv(PROVIDERS[name].client_id_env, "").strip())


def _url(template: str) -> str:
    return template.format(tenant=_ms_tenant())


def redirect_uri(name: str, port: int) -> str:
    return f"http://{PROVIDERS[name].loopback}:{port}{CALLBACK_PATH}"


@dataclass
class Pending:
    tenant: str
    provider: str
    address: str
    server: dict
    verifier: str
    redirect: str
    return_to: str = ""
    created: float = field(default_factory=time.monotonic)


_pending: dict[str, Pending] = {}
_lock = threading.Lock()


def start(tenant: str, provider: str, address: str, server: dict, port: int, return_to: str = "") -> str:
    """Returns the provider's sign-in URL; the state in it ties the answer back to this tenant."""
    if not configured(provider):
        raise OAuthError("not_configured", f"{PROVIDERS[provider].label} sign-in is not set up on this computer.")
    p = PROVIDERS[provider]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    redirect = redirect_uri(provider, port)
    with _lock:
        now = time.monotonic()
        for k in [k for k, v in _pending.items() if now - v.created > PENDING_TTL_S]:
            del _pending[k]
        _pending[state] = Pending(tenant, provider, address, server, verifier, redirect, return_to)
    params = {
        "client_id": os.environ[p.client_id_env].strip(),
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": p.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "login_hint": address,
    }
    if provider == "google":
        params.update(access_type="offline", prompt="consent")
    else:
        params.update(prompt="select_account")
    return f"{_url(p.authorize_url)}?{urlencode(params)}"


def take(state: str) -> Pending:
    """The sign-in this answer belongs to; each state works once and expires after ten minutes."""
    with _lock:
        pending = _pending.pop(state, None)
    if not pending or time.monotonic() - pending.created > PENDING_TTL_S:
        raise OAuthError("expired", "This sign-in link has expired. Start again from CashPilot.")
    return pending


def _token(provider: str, data: dict, client: Optional[httpx.Client] = None) -> dict:
    p = PROVIDERS[provider]
    data = {"client_id": os.environ[p.client_id_env].strip(), **data}
    if p.client_secret_env and os.getenv(p.client_secret_env):
        data["client_secret"] = os.environ[p.client_secret_env].strip()
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        r = client.post(_url(p.token_url), data=data, headers={"Accept": "application/json"})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise OAuthError("token_unreachable", f"Could not reach {p.label} to finish signing in.") from exc
    finally:
        if own:
            client.close()
    if r.status_code != 200 or "access_token" not in body:
        # invalid_grant: the owner revoked access, or the token expired from disuse.
        code = "revoked" if body.get("error") == "invalid_grant" else "token_failed"
        raise OAuthError(code, f"{p.label} did not accept the sign-in ({body.get('error', r.status_code)}).")
    return body


def exchange(pending: Pending, code: str, client: Optional[httpx.Client] = None) -> tuple[str, str]:
    """(access_token, refresh_token) for the code the provider sent back."""
    body = _token(pending.provider, {"grant_type": "authorization_code", "code": code, "redirect_uri": pending.redirect, "code_verifier": pending.verifier}, client)
    if not body.get("refresh_token"):
        raise OAuthError("no_refresh", "The sign-in did not allow offline access, so CashPilot could not stay connected.")
    return body["access_token"], body["refresh_token"]


def refresh(provider: str, refresh_token: str, client: Optional[httpx.Client] = None) -> tuple[str, str]:
    """A fresh access token, and the refresh token to keep (Microsoft rotates it; Google keeps it)."""
    body = _token(provider, {"grant_type": "refresh_token", "refresh_token": refresh_token}, client)
    return body["access_token"], body.get("refresh_token") or refresh_token


def xoauth2(username: str, access_token: str) -> bytes:
    """The SASL XOAUTH2 string; imaplib base64-encodes it."""
    return f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode()
