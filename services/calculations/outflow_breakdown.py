"""Deterministic decomposition of bank statement gross outflows by category.

Categorizes negative transactions into banking-grade operational cost buckets
(Payroll, Facilities/Rent, Debt Service, Suppliers/Inventory, Software/Utilities,
Taxes, Operations/Other) to answer: "Which outflows drive our burn?".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Sequence

from services.ingestion.csv_parser import DemoTransaction

CENT = Decimal("0.01")
PERCENT = Decimal("0.1")

# Standard operational expense category patterns with word boundaries and disambiguation
CATEGORY_PATTERNS = [
    (
        "Payroll & Wages",
        re.compile(r"\b(payroll|salary|salaries|wages|direct\s*dep(?:osit)?|dir\s*dep|ach\s*payroll|gusto|adp|paychex|rippling|compensation|stipend)\b", re.IGNORECASE),
    ),
    (
        "Debt Service & Loans",
        re.compile(r"\b(loan|principal|debt\s*service|amortization|equipment\s*lease|equipment\s*financing|vehicle\s*lease|note\s*pay|interest\s*(?:charge|payment|expense)?|line\s*of\s*credit|credit\s*card\s*pay(?:ment)?|amex\s*epayment|chase\s*card|citi\s*card|capital\s*one|mortgage|sba\s*loan|term\s*loan)\b", re.IGNORECASE),
    ),
    (
        "Facilities & Rent",
        re.compile(r"\b(rent|office\s*rent|building\s*rent|property\s*lease|landlord|realty|storage|facility|office\s*space|building\s*lease)\b", re.IGNORECASE),
    ),
    (
        "Taxes & Government",
        re.compile(r"\b(tax|taxes|irs|hmrc|revenue\s*service|vat|state\s*tax|corp\s*tax|sales\s*tax|withholding|franchise\s*tax)\b", re.IGNORECASE),
    ),
    (
        "Suppliers & Inventory",
        re.compile(r"\b(supplier|suppliers|vendor|vendors|inventory|wholesale|materials|parts|logistics|freight|shipping|packaging|steel|ingredient|raw\s*material|fedex|ups|usps|dhl)\b", re.IGNORECASE),
    ),
    (
        "Software & Utilities",
        re.compile(r"\b(software|subscription|subscriptions|saas|aws|google(?!\s*ads)|microsoft|azure|slack|zoom|utilities|electric|electricity|water|gas\s*(?:utility|bill|co|service)?|internet|telecom|phone|hosting|quickbooks|intuit|xero|salesforce|hubspot|docusign|github|canva|adobe|figma|mailchimp|notion|dropbox|atlassian|jira|trello|shopify)\b", re.IGNORECASE),
    ),
    (
        "Professional Services",
        re.compile(r"\b(legal|accounting|consulting|contractor|contractors|audit|retainer|advisory|attorney|cpa|marketing\s*agency|advertising|seo)\b", re.IGNORECASE),
    ),
]


@dataclass(frozen=True)
class CategoryBreakdown:
    category: str
    total_amount: Decimal
    percentage_of_outflows: Decimal
    transaction_count: int
    average_transaction: Decimal
    largest_transaction: Decimal


@dataclass(frozen=True)
class OutflowBreakdownResult:
    gross_outflows: Decimal
    period_days: int
    average_daily_outflow: Decimal
    top_category: str
    top_category_amount: Decimal
    top_category_percentage: Decimal
    categories: List[CategoryBreakdown]


def categorize_transaction_description(description: str) -> str:
    """Classifies a transaction description into an operational expense category."""
    desc = description.strip()
    for cat_name, pattern in CATEGORY_PATTERNS:
        if pattern.search(desc):
            return cat_name
    return "Operations & Other"


def calculate_outflow_breakdown(
    rows: Sequence[DemoTransaction],
    period_days: Optional[int] = None,
) -> OutflowBreakdownResult:
    """Decomposes all negative transactions in rows by operational expense category.

    Args:
        rows: Sequence of transactions from parsed statement.
        period_days: Number of calendar days covered. If None, derived from transaction dates.

    Returns:
        OutflowBreakdownResult containing aggregated totals, percentages, and ranked categories.
    """
    outflows = [r for r in rows if r.amount < Decimal("0")]

    if not period_days:
        if rows:
            dates = [r.posted_on for r in rows]
            period_days = max(1, (max(dates) - min(dates)).days + 1)
        else:
            period_days = 30

    total_gross = sum((abs(r.amount) for r in outflows), Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)
    daily_avg = (total_gross / Decimal(period_days)).quantize(CENT, rounding=ROUND_HALF_UP)

    # Bucket outflows
    bucket_amounts: Dict[str, List[Decimal]] = {}
    for r in outflows:
        cat = categorize_transaction_description(r.description)
        bucket_amounts.setdefault(cat, []).append(abs(r.amount))

    categories: List[CategoryBreakdown] = []
    for cat_name, amounts in bucket_amounts.items():
        cat_total = sum(amounts, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)
        pct = (
            (cat_total / total_gross * Decimal("100")).quantize(PERCENT, rounding=ROUND_HALF_UP)
            if total_gross > Decimal("0")
            else Decimal("0.0")
        )
        count = len(amounts)
        avg = (cat_total / Decimal(count)).quantize(CENT, rounding=ROUND_HALF_UP)
        largest = max(amounts).quantize(CENT, rounding=ROUND_HALF_UP)
        categories.append(
            CategoryBreakdown(
                category=cat_name,
                total_amount=cat_total,
                percentage_of_outflows=pct,
                transaction_count=count,
                average_transaction=avg,
                largest_transaction=largest,
            )
        )

    # Sort descending by total_amount
    categories.sort(key=lambda c: c.total_amount, reverse=True)

    top_cat = categories[0].category if categories else "None"
    top_amt = categories[0].total_amount if categories else Decimal("0.00")
    top_pct = categories[0].percentage_of_outflows if categories else Decimal("0.0")

    return OutflowBreakdownResult(
        gross_outflows=total_gross,
        period_days=period_days,
        average_daily_outflow=daily_avg,
        top_category=top_cat,
        top_category_amount=top_amt,
        top_category_percentage=top_pct,
        categories=categories,
    )
