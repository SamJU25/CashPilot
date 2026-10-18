"""
Regression tests for the Three-Tier Security Gate's authentication boundary.

Before these tests, every action route was anonymous: callers could stage intents for any
tenant, list another tenant's intents, wipe the whole ledger, enroll a passkey for a victim
tenant, and execute Tier 2 proposals. These tests pin the closed behaviour.
"""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.security.staging_ledger import staging_ledger
from tests.auth_helpers import tenant_headers

client = TestClient(app)

ALPHA = "TENANT-ALPHA"
BETA = "TENANT-BETA"


@pytest.fixture(autouse=True)
def clean_ledger():
    staging_ledger.clear()
    yield
    staging_ledger.clear()


def _stage(tenant: str, action_type: str = "TRANSFER") -> dict:
    headers = tenant_headers(client, tenant)
    response = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": tenant,
            "action_type": action_type,
            "amount_cents": 100000,
            "target_identifier": "ACC-001",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return {"headers": headers, "intent": response.json()}


def test_stage_requires_signed_tenant_token():
    response = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": ALPHA,
            "action_type": "TRANSFER",
            "amount_cents": 100000,
            "target_identifier": "ACC-001",
        },
    )
    assert response.status_code == 401
    assert "tenant token" in response.json()["detail"].lower()


def test_list_and_get_require_token():
    staged = _stage(ALPHA)
    intent_id = staged["intent"]["id"]

    assert client.get("/api/v1/actions").status_code == 401
    assert client.get(f"/api/v1/actions/{intent_id}").status_code == 401
    assert client.post(f"/api/v1/actions/{intent_id}/execute", json={}).status_code == 401
    assert client.post(f"/api/v1/actions/{intent_id}/reject").status_code == 401


def test_delete_ledger_route_is_gone():
    for method in ("delete",):
        assert getattr(client, method)("/api/v1/actions").status_code in (404, 405)
    assert len(staging_ledger.list_intents()) == 0


def test_stage_rejects_tenant_spoofing():
    alpha_headers = tenant_headers(client, ALPHA)
    response = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": BETA,
            "action_type": "TRANSFER",
            "amount_cents": 100000,
            "target_identifier": "ACC-002",
        },
        headers=alpha_headers,
    )
    assert response.status_code == 403
    assert staging_ledger.list_intents() == []


def test_stage_uses_token_identity_when_body_omits_tenant():
    alpha_headers = tenant_headers(client, ALPHA)
    response = client.post(
        "/api/v1/actions/stage",
        json={"action_type": "TRANSFER", "amount_cents": 100000, "target_identifier": "ACC-003"},
        headers=alpha_headers,
    )
    assert response.status_code == 201
    assert response.json()["tenant_id"] == ALPHA


def test_cross_tenant_reads_are_isolated():
    staged = _stage(ALPHA)
    intent_id = staged["intent"]["id"]
    beta_headers = tenant_headers(client, BETA)

    listing = client.get("/api/v1/actions", headers=beta_headers)
    assert listing.status_code == 200
    assert listing.json() == []

    # A tenant_id query override no longer widens visibility.
    overridden = client.get(f"/api/v1/actions?tenant_id={ALPHA}", headers=beta_headers)
    assert overridden.status_code == 200
    assert overridden.json() == []

    assert client.get(f"/api/v1/actions/{intent_id}", headers=beta_headers).status_code == 404
    assert (
        client.post(f"/api/v1/actions/{intent_id}/passkey-options", headers=beta_headers).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/actions/{intent_id}/execute", json={}, headers=beta_headers).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/actions/{intent_id}/reject", headers=beta_headers).status_code == 404
    )


def test_passkey_endpoints_require_token_and_reject_spoofing():
    assert client.post("/api/v1/actions/passkeys/register/options", json={"tenant_id": BETA}).status_code == 401
    assert (
        client.post(
            "/api/v1/actions/passkeys/register",
            json={"tenant_id": BETA, "credential": {}},
        ).status_code
        == 401
    )

    alpha_headers = tenant_headers(client, ALPHA)
    spoof = client.post(
        "/api/v1/actions/passkeys/register/options",
        json={"tenant_id": BETA},
        headers=alpha_headers,
    )
    assert spoof.status_code == 403


def test_tier_2_proposals_cannot_be_executed():
    staged = _stage(ALPHA, action_type="PREPARE_APPLICATION")
    intent_id = staged["intent"]["id"]

    response = client.post(
        f"/api/v1/actions/{intent_id}/execute",
        json={},
        headers=staged["headers"],
    )
    assert response.status_code == 409
    assert "tier 2" in response.json()["detail"].lower()

    still_staged = client.get(f"/api/v1/actions/{intent_id}", headers=staged["headers"])
    assert still_staged.json()["status"] == "STAGED_PENDING_HITL"


def test_factoring_is_tier_3_and_still_requires_passkey():
    staged = _stage(ALPHA, action_type="FACTOR_INVOICE")
    response = client.post(
        f"/api/v1/actions/{staged['intent']['id']}/execute",
        json={},
        headers=staged["headers"],
    )
    assert response.status_code == 403
    assert "biometric" in response.json()["detail"].lower()


def test_token_issuance_requires_enrollment_key(monkeypatch):
    monkeypatch.setenv("TENANT_ENROLLMENT_KEY", "correct-key")
    monkeypatch.delenv("TENANT_ENROLLMENT_KEYS", raising=False)

    missing = client.post("/api/v1/auth/token", json={"tenant_id": ALPHA})
    assert missing.status_code == 403

    wrong = client.post(
        "/api/v1/auth/token",
        json={"tenant_id": ALPHA},
        headers={"X-Enrollment-Key": "wrong"},
    )
    assert wrong.status_code == 403

    good = client.post(
        "/api/v1/auth/token",
        json={"tenant_id": ALPHA},
        headers={"X-Enrollment-Key": "correct-key"},
    )
    assert good.status_code == 200


def test_token_issuance_is_closed_when_no_key_configured(monkeypatch):
    monkeypatch.delenv("TENANT_ENROLLMENT_KEY", raising=False)
    monkeypatch.delenv("TENANT_ENROLLMENT_KEYS", raising=False)

    response = client.post("/api/v1/auth/token", json={"tenant_id": ALPHA})
    assert response.status_code == 503


def test_token_signed_with_former_repository_default_is_rejected():
    legacy_secret = b"sme-copilot-dev-secret-key-32bytes!"
    payload = json.dumps(
        {"tenant_id": ALPHA, "iat": 0, "exp": 9999999999}, separators=(",", ":"), sort_keys=True
    ).encode()
    b64_payload = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(legacy_secret, b64_payload.encode(), hashlib.sha256).digest()
    b64_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    forged = f"{b64_payload}.{b64_signature}"

    response = client.get("/api/v1/actions", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
