"""
End-to-End user flow test validating the complete SME Copilot journey:
1. Ingestion of synthetic bank CSV via /api/v1/analyze.
2. Verification of row-level error provenance (row 6 invalid amount).
3. Deterministic cash metrics (balance, net period change, daily burn, runway).
4. Digital Underwriting Dossier generation via /api/v1/underwrite with True APR matching.
5. Tier 2 intent staging into immutable ledger via /api/v1/actions/stage.
6. The owner's decision via /api/v1/actions/{intent_id}/prepare; nothing is ever executed.
"""

from io import BytesIO
from fastapi.testclient import TestClient
from api.main import app
from services.security.staging_ledger import staging_ledger
from tests.auth_helpers import tenant_headers

client = TestClient(app)

SYNTHETIC_BANK_CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx_001,2026-01-01,1000.00,USD,Initial Client Invoice,10000.00\n"
    "tx_002,2026-01-05,-1500.00,USD,Supplier Raw Materials,8500.00\n"
    "tx_003,2026-01-10,-2000.00,USD,Warehouse Rent Expense,6500.00\n"
    "tx_004,2026-01-15,1000.00,USD,Customer Invoice Settlement,7500.00\n"
    "tx_005,2026-01-20,INVALID_NUM,USD,Corrupted POS Entry,7500.00\n"
).encode("utf-8")


def test_complete_sme_copilot_user_journey():
    staging_ledger.clear()
    tenant = "SME-COFFEE-001"
    headers = tenant_headers(client, tenant)

    # Step 1: Upload CSV and trigger Cash Analysis with 30-day alert threshold
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files={"file": ("synthetic_statement.csv", BytesIO(SYNTHETIC_BANK_CSV), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()

    # Step 2: Verify Ingestion Provenance & Row Rejection
    assert data["accepted_count"] == 4
    assert len(data["rejected_rows"]) == 1
    rejected = data["rejected_rows"][0]
    assert rejected["row_number"] == 6
    assert rejected["reason_code"] == "INVALID_AMOUNT"

    # Step 3: Verify Deterministic Decimal Calculations (Exact Strings)
    assert data["currency"] == "USD"
    assert data["current_balance"] == "7500.00"
    assert data["net_period_change"] == "-1500.00"
    assert data["period_days"] == 15
    assert data["average_daily_burn"] == "100.00"
    assert data["runway_days"] == 75
    assert data["cash_status"] == "WATCH"

    # Step 4: Digital Underwriting & Pre-Qualified Credit Matching
    uw_response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": 0},
        files={"file": ("synthetic_statement.csv", BytesIO(SYNTHETIC_BANK_CSV), "text/csv")},
    )
    assert uw_response.status_code == 200
    uw_data = uw_response.json()
    dossier = uw_data["dossier"]
    assert dossier["currency"] == "USD"
    assert dossier["nsf_count"] == 0
    assert len(uw_data["matched_options"]) >= 1

    top_facility = uw_data["matched_options"][0]
    assert top_facility["is_predatory"] is False
    assert float(top_facility["apr_percent"]) <= 36.00

    # Step 5: Tier 2 Proposal Staging (Immutable Ledger Queue)
    stage_response = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": tenant,
            "action_type": "DRAW_CREDIT_LINE",
            "amount_cents": 2500000,
            "target_identifier": top_facility["provider"],
        },
        headers=headers,
    )
    assert stage_response.status_code == 201
    stage_data = stage_response.json()
    intent_id = stage_data["id"]
    assert stage_data["status"] == "STAGED_PENDING_HITL"
    assert stage_data["amount_cents"] == 2500000

    # Step 6: No execution path exists; the owner prepares the request and sends it themselves.
    assert client.post(f"/api/v1/actions/{intent_id}/execute", json={}, headers=headers).status_code in (404, 405)
    prepared = client.post(f"/api/v1/actions/{intent_id}/prepare", headers=headers)
    assert prepared.status_code == 200
    assert prepared.json()["status"] == "PREPARED"


def test_complete_conversational_agent_user_journey():
    """Validates the complete SME user journey orchestrated through the Autonomous AI Copilot:

    1. Conversational onboarding & capability inquiry via /api/v1/agent/chat.
    2. Contextual cash flow diagnosis with exact runway metrics.
    3. WeBank digital underwriting & pre-qualified financing option matching.
    4. Autonomous Tier 2 proposal staging; the reply says nothing has been sent.
    5. The owner's decision: prepare the request (no execution route exists).
    """
    staging_ledger.clear()
    tenant = "SME-COFFEE-001"
    headers = tenant_headers(client, tenant)
    csv_str = SYNTHETIC_BANK_CSV.decode("utf-8")

    # Step 1: Onboarding dialogue inquiry
    chat_init = client.post(
        "/api/v1/agent/chat",
        json={"message": "Hello Copilot, how can you assist our coffee roastery with cash management?"},
    )
    assert chat_init.status_code == 200
    init_data = chat_init.json()
    assert init_data["intent_detected"] == "GENERAL_ASSISTANCE"
    assert ("CashPilot" in init_data["reply"] or "Autonomous SME Finance Copilot" in init_data["reply"])

    # Step 2: Ingest bank transactions and query cash diagnostic metrics
    chat_diag = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Here is our latest bank statement. What is our daily burn rate and cash runway?",
            "csv_content": csv_str,
            "alert_threshold_days": 30,
        },
    )
    assert chat_diag.status_code == 200
    diag_data = chat_diag.json()
    assert diag_data["intent_detected"] == "CASH_DIAGNOSTIC"
    assert diag_data["metrics"]["current_balance"] == "7500.00"
    assert diag_data["metrics"]["average_daily_burn"] == "100.00"
    assert diag_data["metrics"]["runway_days"] == 75
    assert diag_data["metrics"]["cash_status"] == "WATCH"
    assert "75 days" in diag_data["reply"]

    # Step 3: Query pre-qualified financing facilities
    chat_credit = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Based on this statement, what working capital loans or credit lines can we qualify for?",
            "csv_content": csv_str,
            "nsf_count": 0,
        },
    )
    assert chat_credit.status_code == 200
    credit_data = chat_credit.json()
    assert credit_data["intent_detected"] == "CREDIT_UNDERWRITING"
    assert credit_data["metrics"]["risk_tier"] == "NEAR_PRIME"
    assert len(credit_data["matched_options"]) >= 1
    top_facility = credit_data["matched_options"][0]
    assert top_facility["is_predatory"] is False
    assert float(top_facility["apr_percent"]) <= 36.00

    # Step 4: Ask agent to stage a Tier 2 action proposal
    chat_stage = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Please stage an application to draw line of $25,000 for working capital",
            "tenant_id": tenant,
            "staged_action_type": "DRAW_CREDIT_LINE",
            "staged_amount_cents": 2500000,
            "staged_target": top_facility["provider"],
        },
        headers=headers,
    )
    assert chat_stage.status_code == 200
    stage_data = chat_stage.json()
    assert stage_data["intent_detected"] == "ACTION_STAGING"
    assert stage_data["staged_action"] is not None

    staged_intent_id = stage_data["staged_action"]["intent_id"]
    assert stage_data["staged_action"]["status"] == "STAGED_PENDING_HITL"
    assert stage_data["staged_action"]["amount_cents"] == 2500000
    assert "nothing has been sent" in stage_data["reply"].lower()

    # Step 5: The agent-staged proposal ends in the owner's decision, never an execution.
    assert client.post(f"/api/v1/actions/{staged_intent_id}/execute", json={}, headers=headers).status_code in (404, 405)
    prepared = client.post(f"/api/v1/actions/{staged_intent_id}/prepare", headers=headers)
    assert prepared.status_code == 200
    assert prepared.json()["id"] == staged_intent_id
    assert prepared.json()["status"] == "PREPARED"

