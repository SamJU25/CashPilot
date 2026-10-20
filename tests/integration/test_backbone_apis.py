"""
Integration tests for new Backbone APIs:
- Tier 2/3 Action Staging and the owner's decision (/api/v1/actions)
- Digital Transactional Underwriting and Financing Matching (/api/v1/underwrite)
"""

from fastapi.testclient import TestClient
from api.main import app
from services.security.staging_ledger import staging_ledger
from tests.auth_helpers import tenant_headers

client = TestClient(app)

CSV_PAYLOAD = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx-1,2026-10-01,-1000.00,USD,Office rent,15000.00\n"
    "tx-2,2026-10-02,5000.00,USD,Customer deposit,20000.00\n"
)


def test_actions_staging_and_tier_3_execution_flow():
    staging_ledger.clear()
    headers = tenant_headers(client, "SME-CORP-101")

    # 1. Stage an intent (Tier 2) as the authenticated tenant
    stage_resp = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "SME-CORP-101",
            "action_type": "TRANSFER",
            "amount_cents": 500000,
            "target_identifier": "ACC-PAYROLL-01",
        },
        headers=headers,
    )
    assert stage_resp.status_code == 201
    intent = stage_resp.json()
    intent_id = intent["id"]
    assert intent["status"] == "STAGED_PENDING_HITL"
    assert intent["amount_cents"] == 500000

    # 2. List intents (scoped by the signed token, not a query parameter)
    list_resp = client.get("/api/v1/actions", headers=headers)
    assert list_resp.status_code == 200
    intents = list_resp.json()
    assert len(intents) == 1
    assert intents[0]["id"] == intent_id

    # 3. There is no execution route, signed or not
    assert client.post(f"/api/v1/actions/{intent_id}/execute", json={}, headers=headers).status_code in (404, 405)

    # 4. The owner prepares the request to send it themselves
    prepared = client.post(f"/api/v1/actions/{intent_id}/prepare", headers=headers)
    assert prepared.status_code == 200
    assert prepared.json()["status"] == "PREPARED"


def test_actions_reject_flow():
    staging_ledger.clear()
    headers = tenant_headers(client, "SME-CORP-101")
    stage_resp = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "SME-CORP-101",
            "action_type": "FACTOR_INVOICE",
            "amount_cents": 200000,
            "target_identifier": "INV-8899",
        },
        headers=headers,
    )
    intent_id = stage_resp.json()["id"]

    reject_resp = client.post(f"/api/v1/actions/{intent_id}/reject", headers=headers)
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"


def test_underwrite_api_returns_dossier_and_matched_options():
    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": "0"},
        files={"file": ("transactions.csv", CSV_PAYLOAD.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify dossier
    dossier = data["dossier"]
    assert dossier["currency"] == "USD"
    assert dossier["risk_tier"] == "PRIME"
    assert dossier["daily_average_balance"] == "17500.00"
    assert dossier["transaction_count"] == 2
    assert dossier["nsf_count"] == 0
    assert dossier["max_qualified_limit"] == "52500.00"
    assert dossier["volatility_tier"] in ("LOW", "MODERATE", "HIGH")
    assert dossier["revenue_volatility_cv"] is not None

    # Verify matched options
    options = data["matched_options"]
    assert len(options) >= 2
    for opt in options:
        assert float(opt["max_amount"]) > 0
        assert float(opt["apr_percent"]) > 0
        assert opt["requires_tier_3_hitl"] is True


def test_underwrite_api_rejects_malformed_csv():
    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": "0"},
        files={"file": ("bad.csv", b"invalid,header\n", "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_HEADER"


def test_actions_tenant_token_isolation():
    staging_ledger.clear()
    alpha = tenant_headers(client, "TENANT-ALPHA")
    beta = tenant_headers(client, "TENANT-BETA")

    # Stage intent for tenant Alpha
    stage_resp = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "TENANT-ALPHA",
            "action_type": "TRANSFER",
            "amount_cents": 100000,
            "target_identifier": "ACC-ALPHA-01",
        },
        headers=alpha,
    )
    assert stage_resp.status_code == 201
    intent_id = stage_resp.json()["id"]

    # Alpha sees it
    list_alpha = client.get("/api/v1/actions", headers=alpha)
    assert list_alpha.status_code == 200
    assert len(list_alpha.json()) == 1

    # Beta sees an empty list
    list_beta = client.get("/api/v1/actions", headers=beta)
    assert list_beta.status_code == 200
    assert len(list_beta.json()) == 0

    # Beta cannot retrieve Alpha's intent -> HTTP 404
    get_beta = client.get(f"/api/v1/actions/{intent_id}", headers=beta)
    assert get_beta.status_code == 404

    # Beta cannot prepare Alpha's intent -> HTTP 404
    prep_beta = client.post(f"/api/v1/actions/{intent_id}/prepare", headers=beta)
    assert prep_beta.status_code == 404


def test_underwrite_api_caches_statement_in_session():
    from services.agent.session_store import session_store

    session_id = "sess_underwrite_cache_test"
    tenant_id = "TENANT-UNDERWRITE-01"

    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": "0"},
        files={"file": ("statement.csv", CSV_PAYLOAD.encode("utf-8"), "text/csv")},
        headers={"X-Session-ID": session_id, "X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 200

    rec = session_store.get_for_tenant(session_id, tenant_id)
    assert rec is not None
    assert rec.csv_content is not None
    assert "Office rent" in rec.csv_content

