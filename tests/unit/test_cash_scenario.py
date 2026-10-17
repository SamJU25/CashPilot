"""Unit tests for the deterministic cash scenario (what-if) engine, its extractor, routing and handler."""

from datetime import date
from decimal import Decimal

import pytest

from services.agent.dynamic_router import classify_sub_intent_dynamic
from services.agent.param_extractor import extract_cash_scenario_params
from services.agent.schema import AgentChatRequest
from services.agent.subagents.liquidity_subagent import LiquiditySubagent
from services.agent.tools import tool_run_cash_scenario
from services.calculations.cash_scenario import calculate_cash_scenario
from services.ingestion.csv_parser import DemoTransaction

ANCHOR = [
    DemoTransaction(
        row_number=1,
        transaction_id="tx_001",
        posted_on=date(2026, 3, 30),
        amount=Decimal("-100.00"),
        currency="USD",
        description="Standard Vendor Fee",
        closing_balance=Decimal("30000.00"),
    )
]


def run(balance, net_change, inflows="0.00", period=30, **kw):
    return calculate_cash_scenario(
        current_balance=Decimal(balance),
        net_period_change=Decimal(net_change),
        gross_inflows=Decimal(inflows),
        period_days=period,
        rows=ANCHOR,
        **kw,
    )


def test_cost_cut_extends_runway_exactly():
    res = run("30000.00", "-30000.00", scenario="COST_CUT", amount=Decimal("6000.00"))
    assert res.baseline_daily_burn == Decimal("1000.00")
    assert res.scenario_daily_burn == Decimal("800.00")
    assert res.baseline_runway_days == 30
    assert res.scenario_runway_days == 37
    assert res.runway_change_days == 7


def test_new_expense_shortens_runway():
    res = run("30000.00", "-30000.00", scenario="NEW_EXPENSE", amount=Decimal("3000.00"))
    assert res.scenario_daily_burn == Decimal("1100.00")
    assert res.scenario_runway_days == 27
    assert res.runway_change_days == -3


def test_revenue_drop_raises_burn_from_statement_inflows():
    res = run("60000.00", "-30000.00", inflows="60000.00", scenario="REVENUE_DROP", percent=Decimal("25"))
    assert res.scenario_daily_burn == Decimal("1500.00")
    assert res.baseline_runway_days == 60
    assert res.scenario_runway_days == 40


def test_revenue_drop_can_turn_cash_positive_business_into_burn():
    res = run("20000.00", "15000.00", inflows="45000.00", scenario="REVENUE_DROP", percent=Decimal("50"))
    assert res.baseline_daily_burn == Decimal("0.00")
    assert res.baseline_runway_days is None
    assert res.scenario_daily_burn == Decimal("250.00")
    assert res.scenario_runway_days == 80
    assert res.runway_change_days is None


def test_invoice_delay_that_outlasts_the_balance_flags_a_deficit():
    res = run("20000.00", "-30000.00", scenario="INVOICE_DELAY", amount=Decimal("15000.00"), delay_days=14)
    assert res.balance_during_delay == Decimal("5000.00")
    assert res.scenario_runway_days == 5
    assert res.scenario_deficit.has_projected_deficit is True
    assert res.scenario_deficit.days_until_deficit == 6


def test_invoice_delay_absorbed_by_reserves_keeps_baseline_runway():
    res = run("100000.00", "-30000.00", scenario="INVOICE_DELAY", amount=Decimal("10000.00"), delay_days=30)
    assert res.balance_during_delay == Decimal("90000.00")
    assert res.scenario_runway_days == res.baseline_runway_days == 100
    assert res.scenario_deficit.days_until_deficit is None


@pytest.mark.parametrize(
    "kw",
    [
        {"scenario": "LOTTERY_WIN", "amount": Decimal("1")},
        {"scenario": "COST_CUT"},
        {"scenario": "COST_CUT", "amount": Decimal("-5")},
        {"scenario": "REVENUE_DROP", "percent": Decimal("120")},
        {"scenario": "INVOICE_DELAY", "amount": Decimal("5000")},
    ],
)
def test_invalid_scenario_inputs_raise(kw):
    with pytest.raises(ValueError):
        run("30000.00", "-30000.00", **kw)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("What if Apex Logistics delays their $30,000 invoice by 21 days?", {"scenario": "INVOICE_DELAY", "amount": Decimal("30000"), "delay_days": 21}),
        ("If a customer pays their $12,500 bill 14 days late, do we go negative?", {"scenario": "INVOICE_DELAY", "amount": Decimal("12500"), "delay_days": 14}),
        ("What if we cut costs by $5,000 a month?", {"scenario": "COST_CUT", "amount": Decimal("5000")}),
        ("How does our runway change if we hire someone at $4,500 per month?", {"scenario": "NEW_EXPENSE", "amount": Decimal("4500")}),
        ("What happens if we add a new $2k monthly software expense?", {"scenario": "NEW_EXPENSE", "amount": Decimal("2000")}),
        ("What if our revenue drops 20%?", {"scenario": "REVENUE_DROP", "percent": Decimal("20")}),
    ],
)
def test_extract_cash_scenario_params(text, expected):
    params = extract_cash_scenario_params(text)
    for key, value in expected.items():
        assert params[key] == value


@pytest.mark.parametrize(
    "text",
    [
        "What if Apex Logistics delays their $30,000 invoice by 21 days?",
        "What if we cut costs by $5,000 a month?",
        "How does our runway change if we hire someone at $4,500 per month?",
        "What if our revenue drops 20%?",
    ],
)
def test_what_if_questions_route_to_cash_scenario(text):
    assert classify_sub_intent_dynamic(text) == "CASH_SCENARIO"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How many days of runway do we have?", "RUNWAY"),
        ("Will we go negative in the next few months?", "DEFICIT"),
        ("What is our daily net cash burn velocity?", "BURN"),
        ("What is our verified statement ending balance?", "BALANCE"),
    ],
)
def test_plain_cash_questions_keep_their_routes(text, expected):
    assert classify_sub_intent_dynamic(text) == expected


STATEMENT = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx_0001,2026-03-01,-3000.00,USD,Office Rent,47000.00\n"
    "tx_0002,2026-03-10,4000.00,USD,Client Invoice Payment,51000.00\n"
    "tx_0003,2026-03-20,-6000.00,USD,Payroll Run,45000.00\n"
    "tx_0004,2026-03-30,-5000.00,USD,Supplier Payment,40000.00\n"
)


def test_tool_runs_scenario_against_uploaded_statement():
    res = tool_run_cash_scenario(STATEMENT, scenario="COST_CUT", amount="3000")
    assert Decimal(res["scenario_daily_burn"]) < Decimal(res["baseline_daily_burn"])
    assert res["scenario_runway_days"] > res["baseline_runway_days"]


def _handle(message, csv):
    captured = {}

    def capture(base_reply, prompt_type="diagnostic", **_):
        captured["base"] = base_reply
        return base_reply

    resp = LiquiditySubagent.handle_sub_intent("CASH_SCENARIO", AgentChatRequest(message=message), csv, capture)
    return resp, captured.get("base", "")


def test_handler_reports_baseline_and_scenario_runway():
    resp, base = _handle("What if we cut costs by $3,000 a month?", STATEMENT)
    assert resp is not None
    assert "Scenario Runway" in base and "Baseline Runway" in base


def test_handler_without_statement_asks_for_one():
    resp, base = _handle("What if we cut costs by $3,000 a month?", None)
    assert resp is not None
    assert "Scenario Runway" not in resp.reply
