"""Deterministic Predictive Cash Flow and Early-Warning Crunch Engine.

Projects forward-looking cash positions across 30, 60, and 90 days based on:
1. Current verified closing balance
2. Average daily burn rate
3. Recurring obligations (payroll, rent, debt service)
4. Deficit horizon thresholding (CRITICAL, WARNING, WATCH, SAFE)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
import re
from typing import Optional, Sequence

from services.ingestion.csv_parser import DemoTransaction


MAX_FORECAST_HORIZON_DAYS = 365
STANDARD_TREASURY_HORIZON_DAYS = 90


@dataclass(frozen=True)
class PredictiveDeficitResult:
    has_projected_deficit: bool
    severity: str  # "SAFE" | "WATCH" | "WARNING" | "CRITICAL"
    days_until_deficit: Optional[int]
    projected_deficit_date: Optional[str]
    projected_shortfall_amount: Decimal
    recommended_bridge_amount: Decimal
    detected_recurring_payroll: Optional[Decimal]
    detected_recurring_rent: Optional[Decimal] = None
    detected_recurring_debt: Optional[Decimal] = None
    primary_deficit_trigger: Optional[str] = None
    forecast_30d_balance: Decimal = Decimal("0.00")
    forecast_60d_balance: Decimal = Decimal("0.00")
    forecast_90d_balance: Decimal = Decimal("0.00")
    target_horizon_days: Optional[int] = None
    target_horizon_date: Optional[str] = None
    forecast_target_balance: Optional[Decimal] = None
    confidence_tier: str = "HIGH"  # "HIGH" (<=90d) | "INDICATIVE" (91-365d)
    horizon_capped: bool = False
    advisory_note: Optional[str] = None
    explanation: str = ""


PAYROLL_PATTERN = re.compile(r"\b(payroll|salary|salaries|wages|stipend|direct\s*dep|gusto|adp|paychex)\b", re.IGNORECASE)
# "property tax" and "equipment lease" are not rent; whole words keep "current"/"parent" out.
RENT_PATTERN = re.compile(r"\b(rent|(?<!equipment\s)lease|property\s+management|landlord|realty|storage)\b", re.IGNORECASE)
DEBT_PATTERN = re.compile(r"\b(loan|principal|debt\s*service|amortization|equipment\s*lease|note\s*pay(?:able)?)\b", re.IGNORECASE)
# Checked in order so each outflow lands in exactly one obligation.
OBLIGATION_PATTERNS = (("DEBT_SERVICE", DEBT_PATTERN), ("PAYROLL", PAYROLL_PATTERN), ("RENT", RENT_PATTERN))


@dataclass(frozen=True)
class DetectedObligation:
    category: str
    average_amount: Decimal
    primary_day_of_month: int


@dataclass(frozen=True)
class CashScenario:
    """What-if levers on top of the detected pattern; all zero is the plain forecast."""
    variable_cut_pct: Decimal = Decimal("0")  # cut to day-to-day (non-recurring) spending, 0 to 100
    extra_monthly_payroll: Decimal = Decimal("0")  # added to every payroll run, e.g. a new hire
    one_off_inflows: tuple[tuple[date, Decimal], ...] = ()  # e.g. an overdue invoice collected on a date

    @property
    def is_base(self) -> bool:
        return not self.variable_cut_pct and not self.extra_monthly_payroll and not self.one_off_inflows


def _classify_outflow(description: str, cache: dict) -> Optional[str]:
    """One obligation category per memo: keyword patterns first, then EXPENSE_TRIAGE; cached per memo."""
    if description in cache:
        return cache[description]
    category = next((name for name, pattern in OBLIGATION_PATTERNS if pattern.search(description)), None)
    if category is None:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

        triage_res = DecisionEngineRegistry.get_instance().evaluate(
            DecisionRequest(domain=DecisionDomain.EXPENSE_TRIAGE, input_state={"description": description})
        )
        if triage_res.confidence_score >= 0.85:
            category = triage_res.selected_choice
    cache[description] = category
    return category


def _detect_obligation(
    rows: Sequence[DemoTransaction], category: str, cache: Optional[dict] = None
) -> Optional[DetectedObligation]:
    """Identifies recurring obligation amount and primary day-of-month for one category."""
    cache = {} if cache is None else cache
    matching_amounts: list[Decimal] = []
    days_of_month: list[int] = []

    for r in rows:
        if r.amount < 0 and _classify_outflow(r.description, cache) == category:
            matching_amounts.append(abs(r.amount))
            days_of_month.append(r.posted_on.day)

    if not matching_amounts:
        return None

    avg_amount = sum(matching_amounts, Decimal("0")) / Decimal(len(matching_amounts))
    primary_day = max(set(days_of_month), key=days_of_month.count)
    return DetectedObligation(
        category=category,
        average_amount=avg_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        primary_day_of_month=primary_day,
    )


def detect_obligations(rows: Sequence[DemoTransaction], cache: Optional[dict] = None) -> list[DetectedObligation]:
    """Recurring payroll, rent and debt service found in the statement, in that order."""
    cache = {} if cache is None else cache
    found = (_detect_obligation(rows, category, cache) for category in ("PAYROLL", "RENT", "DEBT_SERVICE"))
    return [ob for ob in found if ob is not None]


def simulate_balances(
    current_balance: Decimal,
    average_daily_burn: Decimal,
    obligations: Sequence[DetectedObligation],
    anchor_date: date,
    days: int,
    scenario: Optional[CashScenario] = None,
) -> list[tuple[date, Decimal, str]]:
    """Day-by-day balance after the anchor: (date, balance, what moved it that day).

    When the statement shows recurring obligations that fit inside the burn, they leave on their
    usual day of the month and only the remainder is spread daily; otherwise the whole burn is daily.
    The deficit forecast and the chart both read this one simulation, so they cannot disagree.
    """
    scenario = scenario or CashScenario()
    total_recurring = sum((ob.average_amount for ob in obligations), Decimal("0.00"))
    lumpy = bool(obligations) and (average_daily_burn * Decimal(30)) > total_recurring
    if lumpy:
        variable = max(Decimal("0.00"), (average_daily_burn * Decimal(30) - total_recurring) / Decimal(30)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        variable = max(Decimal("0.00"), average_daily_burn)
    if scenario.variable_cut_pct:
        variable = (variable * (Decimal(100) - scenario.variable_cut_pct) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    # Extra payroll leaves on the statement's payday whenever one is known, even when net burn is spread daily.
    payday = next((ob.primary_day_of_month for ob in obligations if ob.category == "PAYROLL"), None)
    if scenario.extra_monthly_payroll and payday is None:
        # No payroll day in the statement: spread the extra cost evenly instead of inventing a date.
        variable += (scenario.extra_monthly_payroll / Decimal(30)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    balance = current_balance
    out: list[tuple[date, Decimal, str]] = []
    for day_i in range(1, days + 1):
        sim_dt = anchor_date + timedelta(days=day_i)
        balance -= variable
        trigger = "OPERATING_BURN"
        if lumpy:
            for ob in obligations:
                if sim_dt.day == ob.primary_day_of_month:
                    balance -= ob.average_amount
                    trigger = ob.category
        if payday is not None and scenario.extra_monthly_payroll and sim_dt.day == payday:
            balance -= scenario.extra_monthly_payroll
            trigger = "PAYROLL"
        for when, amount in scenario.one_off_inflows:
            if when == sim_dt:
                balance += amount
        out.append((sim_dt, balance, trigger))
    return out


def detect_recurring_payroll(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring payroll or lump-sum wage obligations from historical descriptions."""
    ob = _detect_obligation(rows, "PAYROLL")
    return ob.average_amount if ob else None


def detect_recurring_rent(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring commercial rent or property lease obligations."""
    ob = _detect_obligation(rows, "RENT")
    return ob.average_amount if ob else None


def detect_recurring_debt(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring debt service, loan amortization, or equipment financing."""
    ob = _detect_obligation(rows, "DEBT_SERVICE")
    return ob.average_amount if ob else None


def calculate_predictive_cash(
    current_balance: Decimal,
    average_daily_burn: Decimal,
    rows: Sequence[DemoTransaction],
    anchor_date: Optional[date] = None,
    projection_days: int = 90,
    target_horizon_days: Optional[int] = None,
    obligations: Optional[Sequence[DetectedObligation]] = None,
    scenario: Optional[CashScenario] = None,
) -> PredictiveDeficitResult:
    """Calculates forward cash trajectory and flags predictive shortfall events."""
    if projection_days <= 0:
        raise ValueError("projection_days must be positive")
    if target_horizon_days is not None and target_horizon_days <= 0:
        raise ValueError("target_horizon_days must be at least 1 day")

    # Use the latest transaction date as anchor, or today
    latest_date = anchor_date or (max(r.posted_on for r in rows) if rows else date.today())
    # Obligations come from the statement, or are passed in when only the summary is known (what-if).
    obligations = list(detect_obligations(rows) if obligations is None else obligations)
    by_category = {ob.category: ob.average_amount for ob in obligations}
    payroll_estimate = by_category.get("PAYROLL")
    rent_estimate = by_category.get("RENT")
    debt_estimate = by_category.get("DEBT_SERVICE")
    scenario = scenario or CashScenario()

    # Treasury boundary and confidence evaluation
    horizon_capped = False
    advisory_note: Optional[str] = None
    effective_target_days = target_horizon_days
    confidence_tier = "HIGH"

    if target_horizon_days is not None:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

        horizon_req = DecisionRequest(
            domain=DecisionDomain.DEFICIT_SEVERITY,
            input_state={
                "eval_horizon_confidence": True,
                "target_horizon_days": target_horizon_days,
            },
            execution_mode="DETERMINISTIC_ONLY",
        )
        horizon_res = DecisionEngineRegistry.get_instance().evaluate(horizon_req)
        confidence_tier = horizon_res.selected_choice
        horizon_capped = horizon_res.output_payload.get("horizon_capped", False)
        effective_target_days = horizon_res.output_payload.get("effective_target_days", target_horizon_days)
        advisory_note = horizon_res.output_payload.get("advisory_note")

    effective_sim_days = min(
        MAX_FORECAST_HORIZON_DAYS,
        max(projection_days, effective_target_days or 0),
    )

    # 30, 60, 90 day base projections
    d30 = current_balance - (average_daily_burn * Decimal(30))
    d60 = current_balance - (average_daily_burn * Decimal(60))
    d90 = current_balance - (average_daily_burn * Decimal(90))

    # Dynamic arbitrary target horizon projection
    target_date: Optional[str] = None
    target_balance: Optional[Decimal] = None
    if effective_target_days is not None:
        target_dt = latest_date + timedelta(days=effective_target_days)
        target_date = target_dt.isoformat()
        target_balance = (current_balance - (average_daily_burn * Decimal(effective_target_days))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # Day-by-day simulation to pinpoint exact deficit day
    days_until_deficit: Optional[int] = None
    projected_date: Optional[str] = None
    shortfall = Decimal("0.00")
    primary_deficit_trigger: Optional[str] = None

    # If already nonpositive
    if current_balance <= 0:
        days_until_deficit = 0
        projected_date = latest_date.isoformat()
        shortfall = abs(current_balance)
        primary_deficit_trigger = "EXISTING_OVERDRAFT"
    elif average_daily_burn > 0 or not scenario.is_base:
        for day_i, (sim_dt, sim_balance, trigger) in enumerate(
            simulate_balances(current_balance, average_daily_burn, obligations, latest_date, effective_sim_days, scenario),
            start=1,
        ):
            if sim_balance < 0:
                days_until_deficit = day_i
                projected_date = sim_dt.isoformat()
                shortfall = abs(sim_balance).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                primary_deficit_trigger = trigger
                break

    # Calculate recommended buffer bridge (shortfall + 20% safety margin, rounded to hundreds)
    has_prelim_deficit = days_until_deficit is not None or current_balance <= 0
    if has_prelim_deficit:
        raw_bridge = shortfall * Decimal("1.20")
        remainder = raw_bridge % Decimal("500")
        if remainder > 0:
            recommended_bridge = raw_bridge + (Decimal("500") - remainder)
        else:
            recommended_bridge = raw_bridge
        recommended_bridge = recommended_bridge.quantize(Decimal("0.01"), rounding=ROUND_UP)
    else:
        recommended_bridge = Decimal("0.00")

    # Evaluate deficit severity horizon and explanatory narrative by reference (zero hardcoding)
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={
            "days_until_deficit": days_until_deficit,
            "has_deficit": has_prelim_deficit,
            "projected_date": projected_date,
            "primary_deficit_trigger": primary_deficit_trigger,
            "shortfall": f"{shortfall:,.2f}",
            "recommended_bridge": f"{recommended_bridge:,.2f}",
            "d90": f"{d90:,.2f}",
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    severity = decision_res.output_payload.get("severity", decision_res.selected_choice)
    has_deficit = bool(decision_res.output_payload.get("has_projected_deficit", severity != "SAFE"))
    explanation = decision_res.output_payload.get("explanation") or decision_res.rationale or ""

    if effective_target_days is not None and target_balance is not None:
        explanation += f" Target {effective_target_days}-day forecast ({target_date}) [{confidence_tier} CONFIDENCE]: projected balance ${target_balance:,.2f}."
        if advisory_note:
            explanation += f" Note: {advisory_note}"

    return PredictiveDeficitResult(
        has_projected_deficit=has_deficit,
        severity=severity,
        days_until_deficit=days_until_deficit,
        projected_deficit_date=projected_date,
        projected_shortfall_amount=shortfall,
        recommended_bridge_amount=recommended_bridge,
        detected_recurring_payroll=payroll_estimate,
        detected_recurring_rent=rent_estimate,
        detected_recurring_debt=debt_estimate,
        primary_deficit_trigger=primary_deficit_trigger,
        forecast_30d_balance=d30.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        forecast_60d_balance=d60.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        forecast_90d_balance=d90.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        target_horizon_days=effective_target_days,
        target_horizon_date=target_date,
        forecast_target_balance=target_balance,
        confidence_tier=confidence_tier,
        horizon_capped=horizon_capped,
        advisory_note=advisory_note,
        explanation=explanation,
    )
