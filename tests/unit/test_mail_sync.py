"""Mailbox sync and the account view, against a fake IMAP server and an in-memory credential store."""

from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

import services.mail.store as store_mod
from services.mail.store import MailStore
from services.mail.sync import sync
from tests.auth_helpers import tenant_headers

AUTH = "mx.google.com; dkim=pass header.d=icbc.com.cn"


def alert(n: int, body: str, sender: str = "notice@icbc.com.cn", day: int = 20) -> bytes:
    m = EmailMessage()
    m["Authentication-Results"] = AUTH
    m["From"] = sender
    m["Subject"] = "账户变动"
    m["Date"] = f"{day} Oct 2026 10:00:00 +0800"
    m["Message-ID"] = f"<m{n}@icbc>"
    m.set_content(body)
    return m.as_bytes()


class FakeBox:
    """Answers only the read-only commands sync may use; anything else fails the test."""

    def __init__(self, mails: dict[int, bytes], validity: str = "7"):
        self.mails, self.validity, self.commands = mails, validity, []

    def response(self, code):
        return code, [self.validity.encode()]

    def uid(self, command, *args):
        self.commands.append(command)
        assert command in ("SEARCH", "FETCH")
        if command == "SEARCH":
            domain = args[-1].strip('"')
            hits = [u for u, raw in self.mails.items() if f"@{domain}".encode() in raw or f".{domain}".encode() in raw]
            return "OK", [" ".join(map(str, hits)).encode()]
        assert args[1] == "(BODY.PEEK[])"  # never a fetch that marks mail as read
        return "OK", [(b"1 (BODY[] {n}", self.mails[int(args[0])]), b")"]

    def logout(self):
        pass


@pytest.fixture
def vault(monkeypatch, tmp_path):
    secrets = {}
    monkeypatch.setattr(store_mod.keyring, "set_password", lambda s, n, p: secrets.__setitem__((s, n), p))
    monkeypatch.setattr(store_mod.keyring, "get_password", lambda s, n: secrets.get((s, n)))
    monkeypatch.setattr(store_mod.keyring, "delete_password", lambda s, n: secrets.pop((s, n)))
    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    return secrets


def connected(vault) -> MailStore:
    s = MailStore("t1")
    s.connect("biz.alerts@gmail.com", {"host": "imap.gmail.com", "port": 993, "username": "biz.alerts@gmail.com", "name": "Gmail"}, "app-pass-1234")
    return s


def test_password_lives_in_the_credential_store_not_the_file(vault):
    s = connected(vault)
    s.save()
    assert "app-pass-1234" not in s.path.read_text(encoding="utf-8")
    assert "app-pass-1234" not in vault.values()  # the keychain holds the key, not the password
    assert MailStore("t1").secret() == "app-pass-1234"
    assert "secret" not in (s.view()["connection"] or {})
    s.disconnect()
    assert vault == {}


def test_refresh_token_too_long_for_windows_credentials_still_works(vault):
    s = MailStore("t1")
    token = "M." + "x" * 3000  # Windows Credential Manager caps a blob near 1,280 characters
    s.connect("biz@outlook.com", {"host": "outlook.office365.com", "port": 993, "username": "biz@outlook.com", "name": "Outlook"}, token, oauth="microsoft")
    assert all(len(v) < 100 for v in vault.values())
    assert s.secret() == token


def test_oauth_sync_refreshes_signs_in_with_xoauth2_and_keeps_rotated_token(vault, monkeypatch):
    import services.mail.sync as sync_mod

    s = MailStore("t1")
    s.connect("biz@outlook.com", {"host": "outlook.office365.com", "port": 993, "username": "biz@outlook.com", "name": "Outlook"}, "refresh-1", oauth="microsoft")
    monkeypatch.setattr(sync_mod.oauth, "refresh", lambda provider, rt: ("access-1", "refresh-2"))
    calls = []
    sync(s, opener=lambda *a: calls.append(a) or FakeBox({}))
    assert calls == [("outlook.office365.com", 993, "biz@outlook.com", "access-1", True)]
    assert s.secret() == "refresh-2"


def test_sync_reads_new_alerts_once_and_keeps_a_cursor(vault):
    s = connected(vault)
    box = FakeBox({1: alert(1, "尾号1234 转入人民币1,000.00元，余额人民币5,000.00元"), 2: alert(2, "hello", sender="friend@example.com")})
    assert sync(s, opener=lambda *a: box)["added"] == 1
    box.mails[3] = alert(3, "尾号1234 支出人民币200.00元，余额人民币4,800.00元", day=21)
    assert sync(s, opener=lambda *a: box)["added"] == 1
    assert sync(s, opener=lambda *a: box)["added"] == 0
    assert s.data["cursor"]["last_uid"] == 3


def test_new_account_waits_for_the_owner_then_counts(vault):
    s = connected(vault)
    sync(s, opener=lambda *a: FakeBox({1: alert(1, "尾号1234 转入人民币1,000.00元，余额人民币5,000.00元")}))
    v = s.view()
    assert [a["status"] for a in v["alerts"]] == ["waiting"]
    assert v["accounts"][0]["status"] == "pending"
    s.decide_account(v["accounts"][0]["key"], "use", "acct-main")
    assert s.view()["alerts"][0]["status"] == "ready"
    s.decide_account(v["accounts"][0]["key"], "ignore", None)
    assert s.view()["alerts"][0]["status"] == "ignored"


def test_missing_alert_is_flagged_by_balance_arithmetic(vault):
    s = connected(vault)
    sync(
        s,
        opener=lambda *a: FakeBox(
            {
                1: alert(1, "尾号1234 转入人民币1,000.00元，余额人民币5,000.00元", day=20),
                # A 300.00 payment between these two never arrived.
                2: alert(2, "尾号1234 支出人民币200.00元，余额人民币4,500.00元", day=21),
            }
        ),
    )
    s.decide_account(s.view()["accounts"][0]["key"], "use", "a")
    newest = s.view()["alerts"][0]
    assert newest["gap"] == "-300.00"


def test_transfer_between_own_accounts_is_paired(vault):
    s = connected(vault)
    sync(
        s,
        opener=lambda *a: FakeBox(
            {
                1: alert(1, "尾号1234 转出人民币2,000.00元"),
                2: alert(2, "尾号5678 转入人民币2,000.00元"),
            }
        ),
    )
    for acc in s.view()["accounts"]:
        s.decide_account(acc["key"], "use", acc["tail"])
    rows = s.view()["alerts"]
    assert {r["transfer_with"] for r in rows} == {r["id"] for r in rows}


def test_changed_uidvalidity_restarts_without_duplicates(vault):
    s = connected(vault)
    mails = {1: alert(1, "尾号1234 转入人民币1.00元")}
    sync(s, opener=lambda *a: FakeBox(mails, validity="7"))
    assert sync(s, opener=lambda *a: FakeBox(mails, validity="8"))["added"] == 0


def test_api_requires_a_tenant_and_rejects_bad_input(vault):
    from api.main import app

    client = TestClient(app)
    assert client.get("/api/v1/mail/state").status_code == 401
    h = tenant_headers(client, "mail-tenant")
    assert client.get("/api/v1/mail/state", headers=h).json()["connection"] is None
    bad = client.post("/api/v1/mail/connect", headers=h, json={"address": "nope", "secret": "x", "host": "imap.gmail.com", "username": "nope"})
    assert bad.status_code == 422
    assert client.post("/api/v1/mail/banks", headers=h, json={"domain": "../etc", "name": "x", "currency": "CNY"}).status_code == 422
    # A server address must be a host name, not a URL or path.
    bad_host = {"address": "a@b.com", "secret": "xxxxx", "host": "http://evil/", "username": "a"}
    assert client.post("/api/v1/mail/connect", headers=h, json=bad_host).status_code == 422


def test_trusting_an_unchecked_sender_counts_its_alerts(vault):
    s = MailStore("t1")
    s.connect("biz@qq.com", {"host": "imap.qq.com", "port": 993, "username": "biz@qq.com", "name": "QQ"}, "auth-code")  # QQ Mail does not stamp sender checks
    sync(s, opener=lambda *a: FakeBox({1: alert(1, "尾号1234 转入人民币10.00元"), 2: alert(2, "尾号1234 转入人民币20.00元")}))
    s.decide_account(s.view()["accounts"][0]["key"], "use", "a")
    rows = s.view()["alerts"]
    assert {r["status"] for r in rows} == {"review"}
    s.resolve_alert(rows[0]["id"], "trust")
    assert {r["status"] for r in s.view()["alerts"]} == {"ready"}


def test_multi_mailbox_connections_and_edit_alert(vault):
    s = MailStore("t_multi")
    s.connect("owner@biz.com", {"host": "imap.biz.com", "port": 993, "username": "owner@biz.com", "name": "Biz 1"}, "secret1")
    s.connect("finance@biz.com", {"host": "imap.biz.com", "port": 993, "username": "finance@biz.com", "name": "Biz 2"}, "secret2")
    
    view = s.view()
    assert len(view["connections"]) == 2
    assert {c["address"] for c in view["connections"]} == {"owner@biz.com", "finance@biz.com"}

    # Sync with fake boxes
    sync(s, opener=lambda *a: FakeBox({1: alert(1, "尾号1111 转入人民币100.00元", day=21)}))
    rows = s.view()["alerts"]
    assert len(rows) == 1
    alert_id = rows[0]["id"]

    # Edit alert counterparty and note
    assert s.edit_alert(alert_id, counterparty="Acme Corp Refined", note="Verified invoice payment") is True
    updated = s.view()["alerts"][0]
    assert updated["counterparty"] == "Acme Corp Refined"
    assert updated["note"] == "Verified invoice payment"

    # Disconnect one address
    s.disconnect("finance@biz.com")
    remaining = s.view()["connections"]
    assert len(remaining) == 1
    assert remaining[0]["address"] == "owner@biz.com"


def test_disconnect_when_connection_is_none_does_not_raise_attribute_error(vault):
    s = MailStore("t_none")
    s.data["connection"] = None
    s.data["connections"] = []
    # Must not raise AttributeError
    s.disconnect("any@biz.com")
    assert s.view()["connection"] is None


def test_abort_event_stops_sync_immediately(vault):
    import threading

    s = connected(vault)
    abort = threading.Event()
    abort.set()  # Pre-aborted
    res = sync(s, opener=lambda *a: FakeBox({1: alert(1, "尾号1234 转入人民币1,000.00元")}), abort_event=abort)
    # Since it was aborted before folder search, no alerts added
    assert res["added"] == 0


def test_multi_mailbox_sync_continues_when_one_fails(vault):
    from services.mail.sync import MailError

    s = MailStore("t_resilient")
    s.connect("failing@biz.com", {"host": "imap.fail.com", "port": 993, "username": "failing@biz.com", "name": "Fail"}, "pass1")
    s.connect("working@biz.com", {"host": "imap.work.com", "port": 993, "username": "working@biz.com", "name": "Work"}, "pass2")

    def opener(host, *args, **kwargs):
        if "fail" in host:
            raise MailError("auth_failed", "Refused")
        return FakeBox({1: alert(1, "尾号9999 转入人民币500.00元")})

    res = sync(s, opener=opener)
    assert res["added"] == 1
    view = s.view()
    failing_conn = next(c for c in view["connections"] if c["address"] == "failing@biz.com")
    working_conn = next(c for c in view["connections"] if c["address"] == "working@biz.com")
    assert failing_conn["last_error"] == "auth_failed"
    assert working_conn["last_error"] is None


def test_api_disconnect_while_sync_in_flight(vault, monkeypatch):
    import time
    from threading import Thread
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    h = tenant_headers(client, "t_race")

    s = MailStore("t_race")
    s.connect("race@biz.com", {"host": "imap.biz.com", "port": 993, "username": "race@biz.com", "name": "Race"}, "pass")
    s.save()

    import services.mail.sync as sync_mod
    original_scan = sync_mod._scan_folder

    def slow_scan(*args, **kwargs):
        time.sleep(0.3)
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "_scan_folder", slow_scan)
    monkeypatch.setattr(sync_mod, "open_mailbox", lambda *a, **kw: FakeBox({1: alert(1, "尾号1234 转入人民币1,000.00元")}))

    sync_result = []

    def run_sync_thread():
        r = client.post("/api/v1/mail/sync", headers=h)
        sync_result.append(r)

    t = Thread(target=run_sync_thread)
    t.start()
    time.sleep(0.05)

    # User clicks disconnect while sync is in flight
    del_res = client.delete("/api/v1/mail/connect", headers=h)
    assert del_res.status_code == 200
    assert del_res.json()["connection"] is None
    assert del_res.json()["connections"] == []

    t.join()
    assert len(sync_result) == 1
    # Post-sync state must NOT resurrect the connection
    final_state = client.get("/api/v1/mail/state", headers=h).json()
    assert final_state["connection"] is None
    assert final_state["connections"] == []

