from datetime import date
from decimal import Decimal
import pytest

from services.calculations.outflow_breakdown import (
    calculate_outflow_breakdown,
    categorize_transaction_description,
)
from services.ingestion.csv_parser import DemoTransaction


def make_tx(tx_id: str, day: int, amount: str, desc: str) -> DemoTransaction:
    return DemoTransaction(
        row_number=1,
        transaction_id=tx_id,
        posted_on=date(2026, 4, day),
        amount=Decimal(amount),
        currency="USD",
        description=desc,
        closing_balance=Decimal("50000.00"),
    )


def test_categorize_descriptions():
    assert categorize_transaction_description("Gusto Payroll Transfer") == "Payroll & Wages"
    assert categorize_transaction_description("Main Street Property Lease") == "Facilities & Rent"
    assert categorize_transaction_description("SBA Loan Monthly Payment") == "Debt Service & Loans"
    assert categorize_transaction_description("Wholesale Packaging Material") == "Suppliers & Inventory"
    assert categorize_transaction_description("AWS Cloud Hosting Billing") == "Software & Utilities"
    assert categorize_transaction_description("IRS Quarterly Tax Deposit") == "Taxes & Government"
    assert categorize_transaction_description("Legal Counsel Retainer Fee") == "Professional Services"
    assert categorize_transaction_description("Random Coffee Shop") == "Operations & Other"

    # Anti-misfiling regression checks: ensure substrings don't match without word boundaries
    assert categorize_transaction_description("Equipment Lease Payment") == "Debt Service & Loans"
    assert categorize_transaction_description("Parent Company Transfer") == "Operations & Other"
    assert categorize_transaction_description("Current Account Sweep") == "Operations & Other"
    assert categorize_transaction_description("Private Cloud Hosting") == "Software & Utilities"
    assert categorize_transaction_description("Software License Activation") == "Software & Utilities"
    assert categorize_transaction_description("QuickBooks Online Subscription") == "Software & Utilities"
    assert categorize_transaction_description("FedEx Freight Delivery") == "Suppliers & Inventory"

    # Plural loans and leases checks
    assert categorize_transaction_description("Commercial Loans") == "Debt Service & Loans"
    assert categorize_transaction_description("Term Loans") == "Debt Service & Loans"
    assert categorize_transaction_description("Office Leases") == "Facilities & Rent"
    assert categorize_transaction_description("Lease Payment") == "Facilities & Rent"
    assert categorize_transaction_description("Equipment Leases") == "Debt Service & Loans"
    assert categorize_transaction_description("Vehicle Leases") == "Debt Service & Loans"



def test_outflow_breakdown_multi_category():
    rows = [
        make_tx("tx_01", 1, "10000.00", "Client Invoice Payment"),  # Inflow (ignored)
        make_tx("tx_02", 1, "-5000.00", "Monthly Office Rent"),
        make_tx("tx_03", 5, "-12000.00", "ADP Bi-weekly Payroll"),
        make_tx("tx_04", 10, "-3000.00", "National Steel Supplies"),
        make_tx("tx_05", 15, "-1000.00", "AWS Cloud Services"),
        make_tx("tx_06", 20, "-12000.00", "ADP Bi-weekly Payroll"),
        make_tx("tx_07", 25, "-2000.00", "Equipment Loan Payment"),
    ]
    # Total outflows = 5000 + 12000 + 3000 + 1000 + 12000 + 2000 = 35,000.00
    res = calculate_outflow_breakdown(rows, period_days=30)
    assert res.gross_outflows == Decimal("35000.00")
    assert res.average_daily_outflow == Decimal("1166.67")
    assert res.top_category == "Payroll & Wages"
    assert res.top_category_amount == Decimal("24000.00")
    # 24,000 / 35,000 = 68.6%
    assert res.top_category_percentage == Decimal("68.6")

    cat_map = {c.category: c for c in res.categories}
    assert cat_map["Payroll & Wages"].transaction_count == 2
    assert cat_map["Payroll & Wages"].average_transaction == Decimal("12000.00")
    assert cat_map["Facilities & Rent"].total_amount == Decimal("5000.00")
    assert cat_map["Suppliers & Inventory"].total_amount == Decimal("3000.00")
    assert cat_map["Debt Service & Loans"].total_amount == Decimal("2000.00")
    assert cat_map["Software & Utilities"].total_amount == Decimal("1000.00")


def test_outflow_breakdown_zero_outflows():
    rows = [
        make_tx("tx_01", 1, "5000.00", "Client Deposit"),
    ]
    res = calculate_outflow_breakdown(rows, period_days=30)
    assert res.gross_outflows == Decimal("0.00")
    assert res.top_category == "None"
    assert res.categories == []


SAMPLE_CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx_01,2026-04-01,15000.00,USD,Client Invoice Payment,65000.00\n"
    "tx_02,2026-04-01,-4500.00,USD,Office Rent,60500.00\n"
    "tx_03,2026-04-15,-10000.00,USD,ADP Payroll Run,50500.00\n"
    "tx_04,2026-04-20,-2500.00,USD,Supplier Parts Inc,48000.00\n"
)


def test_tool_analyze_outflow_breakdown():
    from services.agent.tools import tool_analyze_outflow_breakdown

    res = tool_analyze_outflow_breakdown(SAMPLE_CSV)
    assert res["gross_outflows"] == "17000.00"
    assert res["top_category"] == "Payroll & Wages"
    assert res["top_category_amount"] == "10000.00"
    assert len(res["categories"]) == 3


def test_liquidity_subagent_outflow_breakdown():
    from services.agent.schema import AgentChatRequest
    from services.agent.subagents.liquidity_subagent import LiquiditySubagent

    req = AgentChatRequest(message="Which outflows drive our burn?")
    resp = LiquiditySubagent.handle_sub_intent(
        "OUTFLOW_BREAKDOWN",
        req,
        SAMPLE_CSV,
        lambda base, **_: base,
    )
    assert resp is not None
    assert "Operational Outflow Breakdown by Category" in resp.reply
    assert "Payroll & Wages" in resp.reply
    assert "$10,000.00" in resp.reply
    assert "Primary Cost Driver" in resp.reply
