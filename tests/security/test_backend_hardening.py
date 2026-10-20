"""Regression tests for the remaining backend hardening pass.

Covers chat-driven staging, model management, decision-admin access, private file modes,
and bounded in-memory stores.
"""

import os
import stat
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.agent.local_transformers import LocalTransformersEngine
from services.security.staging_ledger import StagingLedger, StagingRequest, staging_ledger
from tests.auth_helpers import tenant_headers

client = TestClient(app)

DEFICIT_CSV = (
    Path(__file__).resolve().parents[2] / "data" / "samples" / "deficit_statement.csv"
).read_text(encoding="utf-8")

STAGING_CHAT = {
    "message": "Please stage an application to draw line of $25,000 for working capital",
    "staged_action_type": "DRAW_CREDIT_LINE",
    "staged_amount_cents": 2500000,
    "staged_target": "FACILITY-X",
}


@pytest.fixture(autouse=True)
def clean_ledger():
    staging_ledger.clear()
    yield
    staging_ledger.clear()


def test_anonymous_chat_cannot_stage_a_proposal():
    payload = dict(STAGING_CHAT, tenant_id="VICTIM-TENANT")
    response = client.post("/api/v1/agent/chat", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["staged_action"] is None
    assert "authenticated tenant" in body["reply"].lower()
    assert staging_ledger.list_intents() == []


def test_authenticated_chat_stages_for_the_token_tenant():
    headers = tenant_headers(client, "SME-CHAT-01")
    payload = dict(STAGING_CHAT, tenant_id="SOMEONE-ELSE")
    response = client.post("/api/v1/agent/chat", json=payload, headers=headers)

    assert response.status_code == 200
    staged = response.json()["staged_action"]
    assert staged is not None
    assert staged["action_type"] == "DRAW_CREDIT_LINE"

    tenants = [intent.tenant_id for intent in staging_ledger.list_intents()]
    assert tenants == ["SME-CHAT-01"]


def test_anonymous_bridge_plan_stages_nothing():
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Prepare a bridge financing plan for the shortfall.",
            "csv_content": DEFICIT_CSV,
            "tenant_id": "VICTIM-BRIDGE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["staged_action"] is None
    assert staging_ledger.list_intents() == []


def test_authenticated_bridge_plan_stages_for_the_token_tenant():
    headers = tenant_headers(client, "SME-BRIDGE-01")
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Prepare a bridge financing plan for the shortfall.",
            "csv_content": DEFICIT_CSV,
            "tenant_id": "SOMEONE-ELSE",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["staged_action"] is not None
    tenants = {intent.tenant_id for intent in staging_ledger.list_intents()}
    assert tenants == {"SME-BRIDGE-01"}


def test_model_management_requires_a_tenant_token():
    for path in ("/api/v1/agent/download-model", "/api/v1/agent/delete-model"):
        response = client.post(path, json={"model_name": "base-instruct"})
        assert response.status_code == 401, (path, response.text)


def test_provider_probes_require_a_tenant_token():
    for path in ("/api/v1/agent/test-connection", "/api/v1/agent/fetch-models"):
        response = client.post(path, json={"provider": "offline"})
        assert response.status_code == 401, (path, response.text)


def test_decision_admin_is_closed_without_a_configured_key(monkeypatch):
    monkeypatch.delenv("DECISION_ADMIN_KEY", raising=False)
    assert client.post("/api/v1/decision/reload").status_code == 503


def test_decision_reload_rejects_a_wrong_or_missing_key(monkeypatch):
    monkeypatch.setenv("DECISION_ADMIN_KEY", "operator-key")
    assert client.post("/api/v1/decision/reload").status_code == 403
    assert (
        client.post("/api/v1/decision/reload", headers={"X-Admin-Key": "wrong"}).status_code == 403
    )


def test_decision_reload_accepts_the_operator_key(monkeypatch):
    monkeypatch.setenv("DECISION_ADMIN_KEY", "operator-key")
    response = client.post(
        "/api/v1/decision/reload", headers={"X-Admin-Key": "operator-key"}
    )
    assert response.status_code == 200


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are not enforced on Windows")
def test_ledger_files_are_owner_only(tmp_path):
    ledger = StagingLedger(storage_dir=str(tmp_path / "ledger"))
    ledger.stage_intent(
        StagingRequest(
            tenant_id="TENANT-MODE",
            action_type="TRANSFER",
            amount_cents=100,
            target_identifier="ACC-1",
        )
    )

    ledger_dir = tmp_path / "ledger"
    ledger_file = ledger_dir / "staged_intents.json"
    assert stat.S_IMODE(os.stat(ledger_file).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(ledger_dir).st_mode) == 0o700


def test_private_helpers_always_request_owner_only_modes(tmp_path, monkeypatch):
    import services.security.file_utils as file_utils

    calls = []
    monkeypatch.setattr(file_utils.os, "chmod", lambda path, mode: calls.append((str(path), mode)))

    file_utils.ensure_private_dir(str(tmp_path / "private"))
    target = tmp_path / "private" / "secrets.json"
    target.write_text("{}", encoding="utf-8")
    file_utils.restrict_file(str(target))

    assert (str(tmp_path / "private"), 0o700) in calls
    assert (str(target), 0o600) in calls


def test_session_store_evicts_beyond_the_cap(tmp_path, monkeypatch):
    import services.agent.session_store as store_module

    monkeypatch.setattr(store_module, "SESSION_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(store_module, "MAX_IN_MEMORY_SESSIONS", 3)

    store = store_module.SessionStore()
    for index in range(6):
        store.get_or_create(f"sess_{index}", tenant_id="TENANT-CAP")

    assert len(store._sessions) <= 3
    persisted = [name for name in os.listdir(tmp_path) if name.endswith(".json")]
    assert len(persisted) <= 3


def test_delete_model_adapter_guard_still_holds(monkeypatch):
    # rmtree is stubbed: delete_model works on the real models/ folder, and an unstubbed run of this
    # test once deleted the developer's downloaded base weights.
    import shutil

    removed = []
    monkeypatch.setattr(shutil, "rmtree", lambda path, *a, **k: removed.append(os.path.abspath(path)))
    engine = LocalTransformersEngine.get_instance()
    result = engine.delete_model("sme-finance-lora")
    # Whatever it targets, it must never be a fine-tuned adapter directory.
    for path in removed + [str(result.get("deleted_path") or "")]:
        assert "sme-finance-lora" not in path
        assert not os.path.exists(os.path.join(path, "adapter_config.json"))
