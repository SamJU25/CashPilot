"""Unit tests for the deterministic bridge financing plan: ranking, coverage, staging and routing."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest

from services.agent.dynamic_router import classify_sub_intent_dynamic
from services.agent.schema import AgentChatRequest
from services.agent.subagents.liquidity_subagent import LiquiditySubagent
from services.agent.tools import tool_build_bridge_plan
from services.calculations.bridge_plan import FundingSource, calculate_bridge_plan

LINE = FundingSource("DRAW_CREDIT_LINE", "Working Capital Line", Decimal("20000.00"), Decimal("12.00"), 90, "DRAW_CREDIT_LINE")
FACTOR = FundingSource("FACTOR_INVOICE", "Receivables Advance", Decimal("8500.00"), Decimal("24.00"), 30, "FACTOR_INVOICE")
DEFER = FundingSource("SUPPLIER_DEFERRAL", "Supplier payment deferral", Decimal("3000.00"), Decimal("0.00"), 30, None)


def test_cheapest_sources_fill_the_target_first():
    plan = calculate_bridge_plan(Decimal("10000.00"), Decimal("12500.00"), [FACTOR, LINE, DEFER])
    assert [leg.source.kind for leg in plan.legs] == ["SUPPLIER_DEFERRAL", "DRAW_CREDIT_LINE"]
    assert [leg.amount for leg in plan.legs] == [Decimal("3000.00"), Decimal("9500.00")]
    assert plan.buffer == Decimal("2500.00")
    assert plan.uncovered == Decimal("0.00")


def test_leg_cost_is_simple_interest_over_its_term():
    plan = calculate_bridge_plan(Decimal("10000.00"), Decimal("12500.00"), [FACTOR, LINE, DEFER])
    # 9,500 x 12% x 90/365 = 281.10; deferral costs nothing.
    assert plan.legs[1].cost == Decimal("281.10")
    assert plan.total_cost == Decimal("281.10")


def test_capacity_shortfall_is_reported_as_uncovered():
    plan = calculate_bridge_plan(Decimal("30000.00"), Decimal("36000.00"), [FACTOR, DEFER])
    assert sum(leg.amount for leg in plan.legs) == Decimal("11500.00")
    assert plan.uncovered == Decimal("24500.00")


def test_predatory_sources_are_never_used():
    mca = FundingSource("DRAW_CREDIT_LINE", "Merchant advance", Decimal("50000.00"), Decimal("48.00"), 90, "DRAW_CREDIT_LINE")
    plan = calculate_bridge_plan(Decimal("5000.00"), Decimal("6000.00"), [mca])
    assert plan.legs == []
    assert plan.uncovered == Decimal("6000.00")


def test_no_shortfall_needs_no_plan():
    plan = calculate_bridge_plan(Decimal("0.00"), Decimal("0.00"), [LINE])
    assert plan.legs == [] and plan.uncovered == Decimal("0.00") and plan.total_cost == Decimal("0.00")


@lru_cache(maxsize=1)
def _deficit_statement() -> str:
    path = Path(__file__).resolve().parents[2] / "data" / "samples" / "deficit_statement.csv"
    if not path.is_file():
        pytest.skip("deficit_statement.csv sample fixture not found")
    return path.read_text(encoding="utf-8")


def test_tool_question_mode_stages_nothing():
    res = tool_build_bridge_plan(_deficit_statement())
    assert res["staged"] == []
    assert Decimal(res["target"]) >= Decimal(res["shortfall"])


def test_tool_stage_mode_stages_only_financing_legs():
    res = tool_build_bridge_plan(_deficit_statement(), stage=True, tenant_id="TEST-BRIDGE")
    staged_actions = {s["action_type"] for s in res["staged"]}
    assert staged_actions and staged_actions <= {"DRAW_CREDIT_LINE", "FACTOR_INVOICE"}
    assert all(s["biometric_required"] for s in res["staged"])


def _handle(message, csv, allow_staging=False):
    return LiquiditySubagent.handle_sub_intent(
        "BRIDGE_PLAN",
        AgentChatRequest(message=message),
        csv,
        lambda base, **_: base,
        allow_staging=allow_staging,
    )


def test_handler_question_offers_to_stage_and_request_stages():
    csv = _deficit_statement()
    asked = _handle("How should we cover the projected shortfall?", csv, allow_staging=True)
    assert asked.staged_action is None and "Bridge Target" in asked.reply
    told = _handle("Prepare a bridge financing plan for the shortfall.", csv, allow_staging=True)
    assert told.staged_action is not None and told.requires_biometric_hitl is True


def test_handler_without_staging_permission_never_stages():
    csv = _deficit_statement()
    resp = _handle("Prepare a bridge financing plan for the shortfall.", csv)
    assert resp.staged_action is None
    assert resp.requires_biometric_hitl is False
    assert "advisory only" in resp.reply


@pytest.mark.parametrize(
    "text",
    [
        "How should we cover the projected shortfall?",
        "What is the cheapest way to bridge our cash gap?",
        "Prepare a bridge financing plan for the shortfall.",
    ],
)
def test_bridge_questions_route_to_bridge_plan(text):
    assert classify_sub_intent_dynamic(text) == "BRIDGE_PLAN"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Will we go negative in the next few months?", "DEFICIT"),
        ("How many days of runway do we have?", "RUNWAY"),
    ],
)
def test_plain_cash_questions_keep_their_routes(text, expected):
    assert classify_sub_intent_dynamic(text) == expected
