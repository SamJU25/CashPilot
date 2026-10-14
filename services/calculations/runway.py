"""
Deterministic CFO Financial Health Calculation Engine.
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math. Aligns with docs/system.md Section 2.1.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence


def calculate_net_burn(debits: Sequence[Decimal], credits: Sequence[Decimal], period_days: int) -> Decimal:
    """
    Calculate Net Daily Burn Rate.
    Formula: (Sum of Operating Debits - Sum of Operating Credits) / period_days
    """
    if period_days <= 0:
        raise ValueError("period_days must be greater than zero.")
    
    total_debits = sum(debits, Decimal("0.00"))
    total_credits = sum(credits, Decimal("0.00"))
    net_deficit = total_debits - total_credits
    
    daily_burn = net_deficit / Decimal(str(period_days))
    return daily_burn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_runway_days(cash_balance: Decimal, net_daily_burn: Decimal) -> Decimal:
    """
    Calculate exact Cash Runway in days.
    If net_daily_burn <= 0, the company is cash-flow positive (returns Decimal('999')).
    Otherwise, returns floor(cash_balance / net_daily_burn).
    """
    if net_daily_burn <= Decimal("0.00"):
        return Decimal("999")
    
    if cash_balance <= Decimal("0.00"):
        return Decimal("0")
    
    runway = cash_balance / net_daily_burn
    return runway.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_dab(daily_closing_balances: Sequence[Decimal]) -> Decimal:
    """
    Calculate Daily Average Balance (DAB) over N days.
    Formula: (Sum of daily closing balances) / N
    """
    if not daily_closing_balances:
        return Decimal("0.00")
    
    total = sum(daily_closing_balances, Decimal("0.00"))
    count = Decimal(str(len(daily_closing_balances)))
    dab = total / count
    return dab.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_dscr(net_operating_income: Decimal, total_debt_service: Decimal) -> Decimal:
    """
    Calculate Debt Service Coverage Ratio (DSCR).
    Formula: Net Operating Income / Total Debt Service
    Returns Decimal('999.00') if debt service is zero.
    """
    if total_debt_service <= Decimal("0.00"):
        return Decimal("999.00")
    
    dscr = net_operating_income / total_debt_service
    return dscr.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
