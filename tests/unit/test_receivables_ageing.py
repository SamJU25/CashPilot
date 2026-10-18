"""Unit and integration tests for Accounts Receivable (AR) Ageing and Collections Risk Engine."""

from datetime import date
from decimal import Decimal
import pytest
from starlette.testclient import TestClient

from api.main import app
from services.agent.schema import AgentChatRequest, ChatHistoryItem
from services.agent.session_store import session_store
from services.agent.subagents.liquidity_subagent import LiquiditySubagent
from services.agent.tools import tool_analyze_receivables_ageing
from services.calculations.receivables_ageing import (
    calculate_receivables_ageing,
    ReceivablesAgeingResult,
)
from services.ingestion.invoice_parser import InvoiceRecord, parse_invoice_csv


SAMPLE_AR_CSV = """invoice_id,customer_name,issue_date,due_date,amount,status
INV-101,Acme Corp,2026-08-01,2026-08-31,10000.00,UNPAID
INV-102,Globex,2026-09-01,2026-09-15,6000.00,UNPAID
INV-103,Initech,2026-09-10,2026-10-10,14000.00,UNPAID
INV-104,Wayne Ent,2026-06-01,2026-07-01,20000.00,UNPAID
INV-105,Stark Ind,2026-09-20,2026-10-20,50000.00,UNPAID
"""


def test_receivables_ageing_empty():
    result = calculate_receivables_ageing([])
    assert result.total_ar == Decimal("0.00")
    assert result.total_overdue == Decimal("0.00")
    assert result.overdue_ratio_pct == Decimal("0.00")
    assert result.risk_tier == "HEALTHY"
    assert len(result.top_debtors) == 0


def test_receivables_ageing_calculation():
    # As of snapshot: 2026-10-15
    # INV-101 (Acme, due 2026-08-31): overdue by 45 days -> 31-60 bucket, $10,000
    # INV-102 (Globex, due 2026-09-15): overdue by 30 days -> 1-30 bucket, $6,000
    # INV-103 (Initech, due 2026-10-10): overdue by 5 days -> 1-30 bucket, $14,000
    # INV-104 (Wayne, due 2026-07-01): overdue by 106 days -> OVER_90 bucket, $20,000
    # INV-105 (Stark, due 2026-10-20): due in 5 days -> CURRENT bucket, $50,000
    # Total AR: 10k + 6k + 14k + 20k + 50k = $100,000
    # Current: $50,000 (50.00%)
    # Overdue: $50,000 (50.00%)
    # Overdue details:
    # 1-30: 6k + 14k = $20,000 (20.00%)
    # 31-60: $10,000 (10.00%)
    # 61-90: $0.00 (0.00%)
    # OVER_90: $20,000 (20.00%)
    ingest = parse_invoice_csv(SAMPLE_AR_CSV)
    result = calculate_receivables_ageing(ingest.accepted_invoices, as_of_date="2026-10-15")

    assert result.total_ar == Decimal("100000.00")
    assert result.current_amount == Decimal("50000.00")
    assert result.total_overdue == Decimal("50000.00")
    assert result.overdue_ratio_pct == Decimal("50.00")

    # Buckets
    buckets = result.buckets
    assert buckets["CURRENT"].amount == Decimal("50000.00")
    assert buckets["CURRENT"].percentage == Decimal("50.00")
    assert buckets["1_30"].amount == Decimal("20000.00")
    assert buckets["1_30"].percentage == Decimal("20.00")
    assert buckets["31_60"].amount == Decimal("10000.00")
    assert buckets["31_60"].percentage == Decimal("10.00")
    assert buckets["61_90"].amount == Decimal("0.00")
    assert buckets["OVER_90"].amount == Decimal("20000.00")
    assert buckets["OVER_90"].percentage == Decimal("20.00")

    # WADO = (30*6k + 5*14k + 45*10k + 106*20k) / 50k
    # 180k + 70k + 450k + 2120k = 2,820,000 / 50,000 = 56.40 days
    assert result.weighted_average_days_overdue == Decimal("56.40")

    # Top Debtors: Wayne ($20k overdue) should lead overdue ranking
    assert result.top_debtors[0].customer_name == "Wayne Ent"
    assert result.top_debtors[0].overdue_amount == Decimal("20000.00")
    assert result.top_debtors[0].max_days_overdue == 106

    # Concentration: Stark has $50k of $100k total AR = 50%
    assert result.top_1_concentration_pct == Decimal("50.00")

    # Risk Tier: Over 90% is 20%, overdue ratio is 50% -> WARNING tier (or CRITICAL if >50%)
    assert result.risk_tier in ("WARNING", "CRITICAL")
    assert len(result.recommended_actions) >= 1


def test_tool_analyze_receivables_ageing():
    # 1. Via CSV text
    res = tool_analyze_receivables_ageing(SAMPLE_AR_CSV, as_of_date="2026-10-15")
    assert res["total_ar"] == "100000.00"
    assert res["total_overdue"] == "50000.00"
    assert res["overdue_ratio_pct"] == "50.00"
    assert "Wayne Ent" in [d["customer_name"] for d in res["top_debtors"]]

    # 2. Via dict records
    dict_records = [
        {"customer": "Alpha Corp", "amount": "12000.00", "due_date": "2026-10-01"},
        {"customer": "Beta Ltd", "amount": "8000.00", "due_date": "2026-10-25"},
    ]
    res_dict = tool_analyze_receivables_ageing(dict_records, as_of_date="2026-10-15")
    assert res_dict["total_ar"] == "20000.00"
    assert res_dict["total_overdue"] == "12000.00"

    # 3. Missing invoices returns error
    res_err = tool_analyze_receivables_ageing(None)
    assert res_err["error"] == "MISSING_INVOICE_DATA"


def test_liquidity_subagent_receivables_ageing_with_invoices():
    # Test dispatching with inline invoice text
    msg = "Please run receivables ageing for: INV-1 Acme 10000 due 2026-08-31, INV-2 Beta 5000 due 2026-10-20 snapshot 2026-10-15"
    req = AgentChatRequest(message=msg, session_id="test-session-ar")
    resp = LiquiditySubagent.handle_sub_intent(
        sub_intent="RECEIVABLES_AGEING",
        request=req,
        effective_csv=None,
        enrich_fn=lambda text, **kwargs: text,
    )
    assert resp is not None
    assert "Accounts Receivable (AR) Ageing & Collections Audit" in resp.reply
    assert "Acme" in resp.reply
    assert "$10,000.00" in resp.reply


def test_liquidity_subagent_receivables_ageing_missing_guidance():
    # Without invoice data, returns missing param guidance
    req = AgentChatRequest(message="Who owes us money and how late are they?", session_id="test-session-none")
    resp = LiquiditySubagent.handle_sub_intent(
        sub_intent="RECEIVABLES_AGEING",
        request=req,
        effective_csv=None,
        enrich_fn=lambda text, **kwargs: text,
    )
    assert resp is not None
    assert "To analyze accounts receivable aging and identify who owes you and how late" in resp.reply


def test_api_analyze_invoices_endpoint():
    client = TestClient(app)
    files = {"file": ("invoices.csv", SAMPLE_AR_CSV.encode("utf-8"), "text/csv")}
    response = client.post("/api/v1/analyze/invoices", files=files, data={"as_of_date": "2026-10-15"})
    assert response.status_code == 200
    data = response.json()
    assert data["accepted_count"] == 5
    assert data["total_ar"] == "100000.00"
    assert data["total_overdue"] == "50000.00"
    assert "CURRENT" in data["buckets"]
    assert "1_30" in data["buckets"]
    assert len(data["top_debtors"]) >= 1
    assert data["top_debtors"][0]["customer_name"] == "Wayne Ent"


def test_api_analyze_invoices_invalid_upload():
    client = TestClient(app)
    # Empty file
    files = {"file": ("empty.csv", b"", "text/csv")}
    response = client.post("/api/v1/analyze/invoices", files=files)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_receivables_ageing_future_due_dates_not_overdue():
    from datetime import timedelta
    today = date.today()
    invoices = [
        {"customer": "Future Client A", "amount": "5000.00", "due_date": today + timedelta(days=7)},
        {"customer": "Future Client B", "amount": "10000.00", "due_date": today + timedelta(days=30)},
        {"customer": "Overdue Client C", "amount": "2000.00", "due_date": today - timedelta(days=10)},
    ]
    # When as_of_date is omitted, must snapshot to date.today() rather than max(due_date)
    res = calculate_receivables_ageing(invoices)
    assert res.as_of_date == today
    assert res.total_ar == Decimal("17000.00")
    assert res.total_overdue == Decimal("2000.00")
    assert res.current_amount == Decimal("15000.00")
    assert res.buckets["CURRENT"].amount == Decimal("15000.00")
    assert res.buckets["1_30"].amount == Decimal("2000.00")

