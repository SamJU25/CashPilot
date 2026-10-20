"""Daily balance history from statement rows, per account and in total, for the runway chart.

Statements give each row's closing balance. The end-of-day balance is the last row's closing balance that
day, carried forward on days without activity. Before an account's first row its opening balance is used
for the total (the money existed, the statement just starts later); after its last row the account line
stops, because nothing is known, while the total keeps its last balance.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Optional, Sequence

from services.ingestion.csv_parser import DemoTransaction


def daily_balance_history(
    rows: Sequence[DemoTransaction],
    account_of: Callable[[DemoTransaction], str],
) -> tuple[list[tuple[date, Decimal]], dict[str, list[tuple[date, Optional[Decimal]]]]]:
    """Returns (total per day, {account: [(day, balance or None outside its statement)]})."""
    if not rows:
        return [], {}

    by_account: dict[str, list[DemoTransaction]] = {}
    for r in rows:
        by_account.setdefault(account_of(r), []).append(r)

    first_day = min(r.posted_on for r in rows)
    last_day = max(r.posted_on for r in rows)
    days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]

    per_account: dict[str, list[tuple[date, Optional[Decimal]]]] = {}
    contribution: dict[str, list[Decimal]] = {}
    for account, txs in by_account.items():
        txs = sorted(txs, key=lambda t: (t.posted_on, t.row_number))
        end_of_day: dict[date, Decimal] = {}
        for t in txs:
            end_of_day[t.posted_on] = t.closing_balance
        opening = txs[0].closing_balance - txs[0].amount
        start, end = txs[0].posted_on, txs[-1].posted_on

        line: list[tuple[date, Optional[Decimal]]] = []
        totals: list[Decimal] = []
        carried = opening
        for d in days:
            if d in end_of_day:
                carried = end_of_day[d]
            line.append((d, carried if start <= d <= end else None))
            totals.append(carried)
        per_account[account] = line
        contribution[account] = totals

    total = [(d, sum((contribution[a][i] for a in contribution), Decimal("0.00"))) for i, d in enumerate(days)]
    return total, per_account
