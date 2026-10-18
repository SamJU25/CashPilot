"""Deterministic Accounts Receivable (AR) Ageing and Collections Risk Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.

Computes:
1. Standard AR aging buckets (Current, 1-30, 31-60, 61-90, 90+ days past due).
2. Delinquency ratio (Overdue AR / Total AR).
3. Weighted Average Days Overdue (WADO).
4. Debtor concentration & delinquent customer prioritization.
5. Receivables collection risk tier and prescriptive treasury actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Sequence, Union

from services.ingestion.invoice_parser import InvoiceRecord


@dataclass(frozen=True)
class AgeingBucketSummary:
    bucket_key: str
    label: str
    amount: Decimal
    percentage: Decimal
    invoice_count: int


@dataclass(frozen=True)
class CustomerDebtorSummary:
    customer_name: str
    total_open_balance: Decimal
    current_amount: Decimal
    overdue_amount: Decimal
    max_days_overdue: int
    invoice_count: int
    share_of_total_ar: Decimal
    oldest_unpaid_invoice: Optional[str] = None


@dataclass(frozen=True)
class ReceivablesAgeingResult:
    as_of_date: date
    total_ar: Decimal
    current_amount: Decimal
    total_overdue: Decimal
    overdue_ratio_pct: Decimal
    weighted_average_days_overdue: Decimal
    buckets: Dict[str, AgeingBucketSummary]
    top_debtors: List[CustomerDebtorSummary]
    top_1_concentration_pct: Decimal
    risk_tier: str  # "HEALTHY" | "WATCH" | "WARNING" | "CRITICAL"
    summary_advisory: str
    recommended_actions: List[str]


def calculate_receivables_ageing(
    invoices: Sequence[Union[InvoiceRecord, dict]],
    as_of_date: Optional[Union[date, str]] = None,
) -> ReceivablesAgeingResult:
    """Calculates deterministic AR aging schedule and debtor risk analysis.

    Args:
        invoices: List of InvoiceRecord dataclasses or raw invoice dicts.
        as_of_date: Snapshot audit date. If None, defaults to date.today().
    """
    normalized_invoices: List[InvoiceRecord] = []
    for inv in invoices:
        if isinstance(inv, InvoiceRecord):
            normalized_invoices.append(inv)
        elif isinstance(inv, dict):
            from services.ingestion.invoice_parser import parse_invoices_from_dicts
            res = parse_invoices_from_dicts([inv])
            if res.accepted_invoices:
                normalized_invoices.append(res.accepted_invoices[0])

    # Filter to only open/unpaid receivables
    open_invoices = [inv for inv in normalized_invoices if inv.open_amount > Decimal("0.00")]

    # Determine snapshot date: default to today so future due dates are not treated as overdue
    snapshot: date
    if as_of_date is not None:
        if isinstance(as_of_date, str):
            from services.ingestion.financial_parsers import _parse_universal_date
            snapshot = _parse_universal_date(as_of_date)
        else:
            snapshot = as_of_date
    else:
        snapshot = date.today()

    if not open_invoices:
        zero = Decimal("0.00")
        empty_buckets = {
            "CURRENT": AgeingBucketSummary("CURRENT", "Current (Not Overdue)", zero, zero, 0),
            "1_30": AgeingBucketSummary("1_30", "1-30 Days Past Due", zero, zero, 0),
            "31_60": AgeingBucketSummary("31_60", "31-60 Days Past Due", zero, zero, 0),
            "61_90": AgeingBucketSummary("61_90", "61-90 Days Past Due", zero, zero, 0),
            "OVER_90": AgeingBucketSummary("OVER_90", "90+ Days Past Due", zero, zero, 0),
        }
        return ReceivablesAgeingResult(
            as_of_date=snapshot,
            total_ar=zero,
            current_amount=zero,
            total_overdue=zero,
            overdue_ratio_pct=zero,
            weighted_average_days_overdue=zero,
            buckets=empty_buckets,
            top_debtors=[],
            top_1_concentration_pct=zero,
            risk_tier="HEALTHY",
            summary_advisory="Zero outstanding accounts receivable. All client billing is settled.",
            recommended_actions=["Maintain same-day billing discipline."],
        )

    total_ar = sum((inv.open_amount for inv in open_invoices), Decimal("0.00"))

    # Bucket tracking
    bucket_amounts = {
        "CURRENT": Decimal("0.00"),
        "1_30": Decimal("0.00"),
        "31_60": Decimal("0.00"),
        "61_90": Decimal("0.00"),
        "OVER_90": Decimal("0.00"),
    }
    bucket_counts = {k: 0 for k in bucket_amounts}

    total_overdue = Decimal("0.00")
    weighted_days_sum = Decimal("0.00")

    # Group by customer
    debtor_map: Dict[str, List[tuple[InvoiceRecord, int]]] = {}

    for inv in open_invoices:
        days_past_due = (snapshot - inv.due_date).days
        cust = inv.customer_name

        if cust not in debtor_map:
            debtor_map[cust] = []
        debtor_map[cust].append((inv, days_past_due))

        if days_past_due <= 0:
            bucket = "CURRENT"
        elif days_past_due <= 30:
            bucket = "1_30"
            total_overdue += inv.open_amount
            weighted_days_sum += Decimal(str(days_past_due)) * inv.open_amount
        elif days_past_due <= 60:
            bucket = "31_60"
            total_overdue += inv.open_amount
            weighted_days_sum += Decimal(str(days_past_due)) * inv.open_amount
        elif days_past_due <= 90:
            bucket = "61_90"
            total_overdue += inv.open_amount
            weighted_days_sum += Decimal(str(days_past_due)) * inv.open_amount
        else:
            bucket = "OVER_90"
            total_overdue += inv.open_amount
            weighted_days_sum += Decimal(str(days_past_due)) * inv.open_amount

        bucket_amounts[bucket] += inv.open_amount
        bucket_counts[bucket] += 1

    current_amount = bucket_amounts["CURRENT"]

    # Ratios
    overdue_ratio_pct = (
        (total_overdue / total_ar * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_ar > Decimal("0.00")
        else Decimal("0.00")
    )

    weighted_average_days = (
        (weighted_days_sum / total_overdue).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_overdue > Decimal("0.00")
        else Decimal("0.00")
    )

    # Compile Bucket Summaries
    bucket_labels = {
        "CURRENT": "Current (Not Overdue)",
        "1_30": "1-30 Days Past Due",
        "31_60": "31-60 Days Past Due",
        "61_90": "61-90 Days Past Due",
        "OVER_90": "90+ Days Past Due",
    }
    buckets_summary: Dict[str, AgeingBucketSummary] = {}
    for b_key in ("CURRENT", "1_30", "31_60", "61_90", "OVER_90"):
        b_amt = bucket_amounts[b_key]
        b_pct = (
            (b_amt / total_ar * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total_ar > Decimal("0.00")
            else Decimal("0.00")
        )
        buckets_summary[b_key] = AgeingBucketSummary(
            bucket_key=b_key,
            label=bucket_labels[b_key],
            amount=b_amt,
            percentage=b_pct,
            invoice_count=bucket_counts[b_key],
        )

    # Customer Aggregations
    top_debtors: List[CustomerDebtorSummary] = []
    for cust_name, items in debtor_map.items():
        cust_open = sum((inv.open_amount for inv, _ in items), Decimal("0.00"))
        cust_overdue = sum((inv.open_amount for inv, d in items if d > 0), Decimal("0.00"))
        cust_current = cust_open - cust_overdue
        max_d = max(d for _, d in items)
        oldest_inv = min(items, key=lambda x: x[0].due_date)[0].invoice_id
        share = (
            (cust_open / total_ar * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total_ar > Decimal("0.00")
            else Decimal("0.00")
        )
        top_debtors.append(
            CustomerDebtorSummary(
                customer_name=cust_name,
                total_open_balance=cust_open,
                current_amount=cust_current,
                overdue_amount=cust_overdue,
                max_days_overdue=max(0, max_d),
                invoice_count=len(items),
                share_of_total_ar=share,
                oldest_unpaid_invoice=oldest_inv,
            )
        )

    # Sort debtors: highest overdue first, then highest total open
    top_debtors.sort(key=lambda d: (d.overdue_amount, d.total_open_balance), reverse=True)

    largest_debtor = max(top_debtors, key=lambda d: d.share_of_total_ar, default=None)
    top_1_concentration = largest_debtor.share_of_total_ar if largest_debtor else Decimal("0.00")

    # Risk Tier Assessment
    over_90_pct = buckets_summary["OVER_90"].percentage
    if overdue_ratio_pct > Decimal("50.00") or over_90_pct > Decimal("25.00"):
        risk_tier = "CRITICAL"
        summary_advisory = (
            f"CRITICAL COLLECTION DELAYS: {overdue_ratio_pct}% of total AR (${total_overdue:,.2f}) is past due, "
            f"with {over_90_pct}% severely delinquent (>90 days). Immediate escalation required."
        )
    elif overdue_ratio_pct > Decimal("30.00") or over_90_pct > Decimal("10.00"):
        risk_tier = "WARNING"
        summary_advisory = (
            f"ELEVATED RECEIVABLES DISTRESS: {overdue_ratio_pct}% of AR is past due. "
            f"Collection delays threaten operating liquidity and payroll coverage."
        )
    elif overdue_ratio_pct > Decimal("15.00"):
        risk_tier = "WATCH"
        summary_advisory = (
            f"MODERATE RECEIVABLES DRAG: {overdue_ratio_pct}% past due. "
            f"Follow up on 1-30 and 31-60 day aging accounts before aging worsens."
        )
    else:
        risk_tier = "HEALTHY"
        summary_advisory = (
            f"HEALTHY RECEIVABLES PROFILE: {buckets_summary['CURRENT'].percentage}% of AR is current. "
            f"Collection turnaround is disciplined."
        )

    # Recommended Actions
    actions: List[str] = []
    if top_debtors and top_debtors[0].overdue_amount > Decimal("0.00"):
        lead_debtor = top_debtors[0]
        actions.append(
            f"Prioritize collection on {lead_debtor.customer_name}: ${lead_debtor.overdue_amount:,.2f} overdue "
            f"({lead_debtor.max_days_overdue}d past due, oldest invoice {lead_debtor.oldest_unpaid_invoice})."
        )

    if over_90_pct > Decimal("0.00"):
        actions.append(
            f"Issue formal demand letters and place credit holds on accounts in the 90+ days bucket "
            f"(${bucket_amounts['OVER_90']:,.2f} at default risk)."
        )

    if top_1_concentration > Decimal("35.00") and largest_debtor:
        actions.append(
            f"High debtor concentration risk: {largest_debtor.customer_name} represents {top_1_concentration}% of total AR. "
            f"Negotiate milestone progress billing or letters of credit."
        )

    if current_amount > Decimal("10000.00") and overdue_ratio_pct > Decimal("20.00"):
        actions.append(
            f"Consider receivables factoring or asset-based advance on current AR (${current_amount:,.2f}) "
            f"to bridge cash shortfall without waiting on overdue debtors."
        )

    if not actions:
        actions.append("Maintain regular 7-day payment reminder cycles before invoice due dates.")

    return ReceivablesAgeingResult(
        as_of_date=snapshot,
        total_ar=total_ar.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        current_amount=current_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        total_overdue=total_overdue.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        overdue_ratio_pct=overdue_ratio_pct,
        weighted_average_days_overdue=weighted_average_days,
        buckets=buckets_summary,
        top_debtors=top_debtors,
        top_1_concentration_pct=top_1_concentration,
        risk_tier=risk_tier,
        summary_advisory=summary_advisory,
        recommended_actions=actions,
    )
