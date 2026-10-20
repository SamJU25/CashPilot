"""Deterministic what-if cash scenarios rerun against the uploaded statement.

Each scenario adjusts the statement's average daily cash flow (or, for a late invoice, the balance
during the delay) and reruns the same runway rule and predictive deficit engine used for the
baseline, so baseline and scenario figures are always directly comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from services.calculations.cash_analysis import runway_days_for
from services.calculations.predictive_cash import PredictiveDeficitResult, calculate_predictive_cash
from services.ingestion.csv_parser import DemoTransaction
from services.calculations.currency_registry import format_money

SCENARIOS = ("INVOICE_DELAY", "COST_CUT", "NEW_EXPENSE", "REVENUE_DROP")
# Same 30-day month the predictive engine uses for recurring obligations.
DAYS_PER_MONTH = Decimal("30")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class CashScenarioResult:
    scenario: str
    assumption: str
    baseline_daily_burn: Decimal
    scenario_daily_burn: Decimal
    baseline_runway_days: Optional[int]
    scenario_runway_days: Optional[int]
    runway_change_days: Optional[int]
    baseline_deficit: PredictiveDeficitResult
    scenario_deficit: PredictiveDeficitResult
    balance_during_delay: Optional[Decimal] = None


def _burn(net_daily: Decimal) -> Decimal:
    return max(Decimal("0"), -net_daily).quantize(CENT, rounding=ROUND_HALF_UP)


def _validate(scenario: str, amount: Optional[Decimal], percent: Optional[Decimal], delay_days: Optional[int]) -> None:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
    if scenario == "REVENUE_DROP":
        if percent is None or not Decimal("0") < percent <= Decimal("100"):
            raise ValueError("REVENUE_DROP needs a percent between 0 and 100")
        return
    if amount is None or amount <= 0:
        raise ValueError(f"{scenario} needs a positive amount")
    if scenario == "INVOICE_DELAY" and (delay_days is None or delay_days < 1):
        raise ValueError("INVOICE_DELAY needs delay_days of at least 1")


def calculate_cash_scenario(
    current_balance: Decimal,
    net_period_change: Decimal,
    gross_inflows: Decimal,
    period_days: int,
    rows: Sequence[DemoTransaction],
    scenario: str,
    amount: Optional[Decimal] = None,
    percent: Optional[Decimal] = None,
    delay_days: Optional[int] = None,
    currency: str = "USD",
) -> CashScenarioResult:
    """Reruns runway and deficit for one what-if change against the statement baseline.

    amount is monthly for COST_CUT and NEW_EXPENSE and one-off for INVOICE_DELAY.
    """
    _validate(scenario, amount, percent, delay_days)
    if period_days < 1:
        raise ValueError("period_days must be at least 1")

    net_daily = net_period_change / Decimal(period_days)
    baseline_burn = _burn(net_daily)
    baseline_runway = runway_days_for(current_balance, baseline_burn)
    baseline_deficit = calculate_predictive_cash(current_balance, baseline_burn, rows, currency=currency)

    balance_during_delay: Optional[Decimal] = None
    if scenario == "INVOICE_DELAY":
        # The invoice was due now and lands delay_days late: the balance is short by its amount
        # for the whole delay, then returns to the baseline path once it is paid.
        scenario_burn = baseline_burn
        balance_during_delay = (current_balance - amount).quantize(CENT, rounding=ROUND_HALF_UP)
        runway_during = runway_days_for(balance_during_delay, scenario_burn)
        scenario_runway = runway_during if runway_during is not None and runway_during < delay_days else baseline_runway
        scenario_deficit = calculate_predictive_cash(balance_during_delay, scenario_burn, rows, projection_days=delay_days, currency=currency)
        assumption = (
            f"Assumes the {format_money(amount, currency)} invoice was due now and arrives {delay_days} days late, "
            "with all other cash flows following the statement average."
        )
    else:
        if scenario == "COST_CUT":
            net_daily += amount / DAYS_PER_MONTH
            assumption = f"Assumes monthly outflows fall by {format_money(amount, currency)} from today."
        elif scenario == "NEW_EXPENSE":
            net_daily -= amount / DAYS_PER_MONTH
            assumption = f"Assumes a new {format_money(amount, currency)} monthly cost starts today."
        else:
            net_daily -= gross_inflows * percent / Decimal("100") / Decimal(period_days)
            assumption = f"Assumes customer inflows run {percent}% below the statement average while costs stay the same."
        scenario_burn = _burn(net_daily)
        scenario_runway = runway_days_for(current_balance, scenario_burn)
        scenario_deficit = calculate_predictive_cash(current_balance, scenario_burn, rows, currency=currency)

    change = None
    if baseline_runway is not None and scenario_runway is not None:
        change = scenario_runway - baseline_runway

    return CashScenarioResult(
        scenario=scenario,
        assumption=assumption,
        baseline_daily_burn=baseline_burn,
        scenario_daily_burn=scenario_burn,
        baseline_runway_days=baseline_runway,
        scenario_runway_days=scenario_runway,
        runway_change_days=change,
        baseline_deficit=baseline_deficit,
        scenario_deficit=scenario_deficit,
        balance_during_delay=balance_during_delay,
    )
