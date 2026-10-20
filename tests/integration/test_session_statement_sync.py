"""The chat answers from the same figures the app shows, including entries recorded after an upload."""

import re

from fastapi.testclient import TestClient

from api.main import app
from services.ingestion.session_statement import split_meta

client = TestClient(app)


def _chat(session, message):
    return client.post("/api/v1/agent/chat", json={"message": message}, headers={"X-Session-ID": session}).json()["reply"]


def _upload_two_accounts(session):
    files = [
        ("files", (name, open(f"data/samples/{name}", "rb").read(), "text/csv"))
        for name in ("chase_operating_october.csv", "svb_payroll_october.csv")
    ]
    return client.post("/api/v1/analyze", files=files, headers={"X-Session-ID": session}).json()


def test_chat_balance_is_the_consolidated_total_after_a_multi_account_upload():
    body = _upload_two_accounts("sess_sync_total")
    assert body["current_balance"] == "36830.00"
    assert "$36,830.00" in _chat("sess_sync_total", "What is my current cash balance?")


def test_underwrite_does_not_replace_the_uploaded_statement():
    _upload_two_accounts("sess_sync_underwrite")
    client.post(
        "/api/v1/underwrite",
        files={"file": ("chase_operating_october.csv", open("data/samples/chase_operating_october.csv", "rb").read(), "text/csv")},
        headers={"X-Session-ID": "sess_sync_underwrite"},
    )
    assert "$36,830.00" in _chat("sess_sync_underwrite", "What is my current cash balance?")


def test_quick_cash_entry_reaches_the_chat():
    session = "sess_sync_adjust"
    body = _upload_two_accounts(session)
    client.post(
        "/api/v1/analyze/adjust",
        json={
            "current_balance": body["current_balance"],
            "adjustment_type": "OUTFLOW",
            "amount": "1000.00",
            "description": "Supplier payment",
            "account_id": "Account_1",
            "accounts": [{"account_id": "Account_1", "balance": "35780.00"}, {"account_id": "Account_2", "balance": "1050.00"}],
        },
        headers={"X-Session-ID": session},
    )
    assert "$35,830.00" in _chat(session, "What is my current cash balance?")


def test_typed_balance_and_spend_drive_the_chat_runway():
    session = "sess_sync_manual"
    client.post(
        "/api/v1/analyze/summary",
        json={"current_balance": "42000.00", "daily_burn": "500.00", "as_of_date": "2026-10-20"},
        headers={"X-Session-ID": session},
    )
    assert re.search(r"\b84 days\b", _chat(session, "How long will my cash last?"))

    client.post(
        "/api/v1/analyze/adjust",
        json={
            "current_balance": "42000.00",
            "adjustment_type": "INFLOW",
            "amount": "8000.00",
            "daily_burn": "500.00",
            "account_id": "Main account",
            "accounts": [{"account_id": "Main account", "balance": "42000.00"}],
            "effective_date": "2026-10-21",
        },
        headers={"X-Session-ID": session},
    )
    reply = _chat(session, "How long will my cash last?")
    assert "$50,000.00" in reply and re.search(r"\b100 days\b", reply)


def test_another_tenants_session_is_not_written():
    from services.agent.session_store import session_store

    session_store.get_or_create("sess_sync_owned", tenant_id="TENANT-OWNER")
    session_store.update_statement("sess_sync_owned", "transaction_id,posted_on,amount,currency,description,closing_balance\n", tenant_id="TENANT-OWNER")
    client.post(
        "/api/v1/analyze/summary",
        json={"current_balance": "1.00"},
        headers={"X-Session-ID": "sess_sync_owned", "X-Tenant-ID": "TENANT-OTHER"},
    )
    meta, body = split_meta(session_store.get("sess_sync_owned").csv_content)
    assert "Balance entered by owner" not in body
