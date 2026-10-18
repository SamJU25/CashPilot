"""Deterministic bridge financing plan: the cheapest mix of sources that covers a projected shortfall.

Costs are linear in the amount drawn and each source has a capacity, so filling the target from the
cheapest APR upward is the exact optimum (fractional knapsack); no solver is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Sequence

CENT = Decimal("0.01")
# Matches the project-wide predatory lending flag.
PREDATORY_APR_PERCENT = Decimal("36.00")


def is_predatory_apr(apr_percent: Decimal, product_type: str = "BRIDGE_FACILITY") -> bool:
    """Evaluates predatory APR ceiling via DecisionDomain.USURY_COMPLIANCE with deterministic fallback."""
    try:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

        decision_req = DecisionRequest(
            domain=DecisionDomain.USURY_COMPLIANCE,
            input_state={"apr": float(apr_percent), "product_type": product_type},
            execution_mode="DETERMINISTIC_ONLY",
        )
        decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
        return bool(decision_res.output_payload.get("is_predatory", apr_percent > PREDATORY_APR_PERCENT))
    except Exception:
        return apr_percent > PREDATORY_APR_PERCENT


@dataclass(frozen=True)
class FundingSource:
    kind: str  # DRAW_CREDIT_LINE | FACTOR_INVOICE | SUPPLIER_DEFERRAL
    name: str
    capacity: Decimal
    apr_percent: Decimal
    term_days: int
    stage_action: Optional[str]  # staging-ledger action type; None when no money moves (e.g. deferral)


@dataclass(frozen=True)
class PlanLeg:
    source: FundingSource
    amount: Decimal
    cost: Decimal


@dataclass(frozen=True)
class BridgePlanResult:
    shortfall: Decimal
    target: Decimal
    buffer: Decimal
    legs: List[PlanLeg]
    total_cost: Decimal
    uncovered: Decimal


def calculate_bridge_plan(shortfall: Decimal, target: Decimal, sources: Sequence[FundingSource]) -> BridgePlanResult:
    """Allocates target (shortfall plus cash buffer) across sources, cheapest APR first, skipping predatory ones."""
    if shortfall < 0 or target < shortfall:
        raise ValueError("target must cover the shortfall, and neither can be negative")

    remaining = target
    legs: List[PlanLeg] = []
    usable = [s for s in sources if s.capacity > 0 and not is_predatory_apr(s.apr_percent, s.kind)]
    for src in sorted(usable, key=lambda s: (s.apr_percent, s.term_days)):
        if remaining <= 0:
            break
        amount = min(src.capacity, remaining).quantize(CENT, rounding=ROUND_HALF_UP)
        cost = (amount * src.apr_percent / Decimal("100") * Decimal(src.term_days) / Decimal("365")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        legs.append(PlanLeg(source=src, amount=amount, cost=cost))
        remaining -= amount

    return BridgePlanResult(
        shortfall=shortfall,
        target=target,
        buffer=target - shortfall,
        legs=legs,
        total_cost=sum((leg.cost for leg in legs), Decimal("0.00")),
        uncovered=max(Decimal("0.00"), remaining).quantize(CENT, rounding=ROUND_HALF_UP),
    )
