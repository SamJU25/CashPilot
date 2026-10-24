"""Browser sign-in for Gmail and Outlook alert mailboxes: the URL, the single-use state, the callback."""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

import services.mail.oauth as oauth
import services.mail.store as store_mod
from services.mail.store import MailStore
from tests.auth_helpers import tenant_headers

SERVER = {"host": "imap.gmail.com", "port": 993, "username": "biz@gmail.com", "name": "Gmail"}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "desktop-secret")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", "ms-cid")
    secrets = {}
    monkeypatch.setattr(store_mod.keyring, "set_password", lambda s, n, p: secrets.__setitem__((s, n), p))
    monkeypatch.setattr(store_mod.keyring, "get_password", lambda s, n: secrets.get((s, n)))
    monkeypatch.setattr(store_mod.keyring, "delete_password", lambda s, n: secrets.pop((s, n)))
    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    oauth._pending.clear()
    return secrets


def q(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_google_url_uses_pkce_offline_access_and_loopback(env):
    url = oauth.start("t1", "google", "biz@gmail.com", SERVER, 8000)
    p = q(url)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert (p["scope"], p["access_type"], p["code_challenge_method"], p["login_hint"]) == ("https://mail.google.com/", "offline", "S256", "biz@gmail.com")
    assert p["redirect_uri"] == "http://127.0.0.1:8000/api/v1/mail/oauth/callback"
    pending = oauth.take(p["state"])
    expected = base64.urlsafe_b64encode(hashlib.sha256(pending.verifier.encode()).digest()).rstrip(b"=").decode()
    assert p["code_challenge"] == expected and "desktop-secret" not in url


def test_microsoft_url(env):
    p = q(oauth.start("t1", "microsoft", "biz@outlook.com", {**SERVER, "host": "outlook.office365.com"}, 8000))
    assert p["scope"] == "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
    assert p["redirect_uri"] == "http://localhost:8000/api/v1/mail/oauth/callback"


def test_not_configured(env, monkeypatch):
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID")
    monkeypatch.setenv("USE_THUNDERBIRD_OAUTH", "0")
    with pytest.raises(oauth.OAuthError) as e:
        oauth.start("t1", "microsoft", "a@outlook.com", SERVER, 8000)
    assert e.value.code == "not_configured"


def test_state_works_once_and_expires(env, monkeypatch):
    state = q(oauth.start("t1", "google", "biz@gmail.com", SERVER, 8000))["state"]
    oauth.take(state)
    with pytest.raises(oauth.OAuthError):
        oauth.take(state)
    state = q(oauth.start("t1", "google", "biz@gmail.com", SERVER, 8000))["state"]
    oauth._pending[state].created -= oauth.PENDING_TTL_S + 1
    with pytest.raises(oauth.OAuthError):
        oauth.take(state)


def test_exchange_sends_verifier_and_needs_a_refresh_token(env):
    state = q(oauth.start("t1", "google", "biz@gmail.com", SERVER, 8000))["state"]
    pending = oauth.take(state)
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent.update(parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": "A", "refresh_token": "R"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert oauth.exchange(pending, "the-code", client) == ("A", "R")
    assert sent["code_verifier"] == [pending.verifier] and sent["client_secret"] == ["desktop-secret"]

    no_refresh = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"access_token": "A"})))
    with pytest.raises(oauth.OAuthError):
        oauth.exchange(pending, "c", no_refresh)


def test_revoked_refresh_is_reported(env):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "invalid_grant"})))
    with pytest.raises(oauth.OAuthError) as e:
        oauth.refresh("google", "R", client)
    assert e.value.code == "revoked"


def test_callback_connects_and_rejects_replays(env, monkeypatch):
    from api.main import app
    import api.routes.mail as routes

    client = TestClient(app)
    h = tenant_headers(client, "oauth-tenant")
    monkeypatch.setattr(routes, "discover", lambda a: None)
    r = client.post("/api/v1/mail/oauth/start", headers=h, json={"address": "biz@gmail.com", "host": "imap.gmail.com", "username": "biz@gmail.com"})
    state = q(r.json()["url"])["state"]

    class Box:
        def logout(self):
            pass

    monkeypatch.setattr(routes.oauth, "exchange", lambda pending, code: ("ACCESS", "REFRESH"))
    opened = []
    monkeypatch.setattr(routes, "open_mailbox", lambda *a: opened.append(a) or Box())
    monkeypatch.setattr(routes, "sync", lambda store: {"read": 0, "added": 0})

    ok = client.get("/api/v1/mail/oauth/callback", params={"state": state, "code": "c"})
    assert ok.status_code == 200 and "Connected" in ok.text
    assert opened == [("imap.gmail.com", 993, "biz@gmail.com", "ACCESS", True)]
    conn = MailStore("oauth-tenant").data["connection"]
    assert conn["oauth"] == "google" and "REFRESH" not in str(conn) and MailStore("oauth-tenant").secret() == "REFRESH"

    replay = client.get("/api/v1/mail/oauth/callback", params={"state": state, "code": "c"})
    assert replay.status_code == 400
    forged = client.get("/api/v1/mail/oauth/callback", params={"state": "made-up", "code": "c"})
    assert forged.status_code == 400
    assert client.post("/api/v1/mail/oauth/start", json={"address": "a@gmail.com", "host": "imap.gmail.com", "username": "a"}).status_code == 401


def test_return_link_only_for_local_app_pages(env):
    from api.main import app

    client = TestClient(app)
    h = tenant_headers(client, "oauth-tenant-2")
    body = {"address": "biz@gmail.com", "host": "imap.gmail.com", "username": "biz@gmail.com"}
    for back, kept in (("http://localhost:3000/bank-emails", True), ("https://evil.example/phish", False), ("http://localhost:3000/x?y=<script>", False)):
        state = q(client.post("/api/v1/mail/oauth/start", headers=h, json={**body, "return_to": back}).json()["url"])["state"]
        page = client.get("/api/v1/mail/oauth/callback", params={"state": state, "error": "access_denied"}).text
        assert ("Back to CashPilot" in page) is kept and "evil.example" not in page


def test_thunderbird_oauth_credentials_used_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setenv("USE_THUNDERBIRD_OAUTH", "1")
    url = oauth.start("t1", "google", "biz@gmail.com", SERVER, 8000)
    p = q(url)
    assert p["client_id"] == oauth.THUNDERBIRD_CREDENTIALS["google"]["client_id"]
    assert p["redirect_uri"] == "http://127.0.0.1:8000/"

    ms_url = oauth.start("t1", "microsoft", "biz@outlook.com", {**SERVER, "host": "outlook.office365.com"}, 8000)
    ms_p = q(ms_url)
    assert ms_p["client_id"] == oauth.THUNDERBIRD_CREDENTIALS["microsoft"]["client_id"]
    assert ms_p["redirect_uri"] == "http://localhost:8000/"


def test_root_callback_delegates_to_mail_oauth(env, monkeypatch):
    from api.main import app
    client = TestClient(app)
    import api.routes.mail as routes

    class Box:
        def logout(self):
            pass

    monkeypatch.setattr(routes.oauth, "exchange", lambda pending, code: ("ACCESS", "REFRESH"))
    monkeypatch.setattr(routes, "open_mailbox", lambda *a: Box())
    monkeypatch.setattr(routes, "sync", lambda store: {"read": 0, "added": 0})

    pending_state = "tb-state"
    routes.oauth._pending[pending_state] = routes.oauth.Pending(
        tenant="tb-tenant",
        provider="google",
        address="biz@gmail.com",
        server=SERVER,
        verifier="v",
        redirect="http://127.0.0.1:8000/",
    )
    res = client.get("/", params={"state": pending_state, "code": "the-code"})
    assert res.status_code == 200
    assert "Connected" in res.text
