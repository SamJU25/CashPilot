"""The statement a chat session reasons over, kept in one canonical CSV.

Uploads arrive in each bank's own layout, and several files may cover several accounts. The session stores
one CSV in a fixed layout built from the consolidated rows, so the chat tools always read the same totals
the app shows. Entries the owner records afterwards (quick cash, the chat's confirm card) are appended as
dated rows with the new consolidated balance, so every tool sees them without special cases.

A "#cashpilot " first line carries settings that rows cannot express, today the daily spend an owner typed
for a balance entered by hand. Readers strip it before parsing (see strip_meta).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from services.ingestion.csv_parser import DemoTransaction

HEADER = ["transaction_id", "posted_on", "amount", "currency", "description", "closing_balance"]
META_PREFIX = "#cashpilot "
MANUAL_PREFIX = "manual-"


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def split_meta(text: str) -> tuple[dict, str]:
    """The settings line (if any) and the CSV without it."""
    if text and text.startswith(META_PREFIX):
        first, _, rest = text.partition("\n")
        try:
            meta = json.loads(first[len(META_PREFIX):])
        except ValueError:
            meta = {}
        return (meta if isinstance(meta, dict) else {}), rest
    return {}, text


def strip_meta(text: str) -> str:
    return split_meta(text)[1]


def _write(rows: list[list[str]], meta: Optional[dict] = None) -> str:
    out = io.StringIO()
    if meta:
        out.write(META_PREFIX + json.dumps(meta, separators=(",", ":")) + "\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return out.getvalue()


def canonical_csv(rows: Sequence[DemoTransaction], currency: str) -> str:
    """The consolidated rows in the fixed layout, oldest first."""
    ordered = sorted(rows, key=lambda r: (r.posted_on, r.row_number))
    return _write(
        [[r.transaction_id, r.posted_on.isoformat(), _money(r.amount), currency or r.currency, r.description, _money(r.closing_balance)] for r in ordered]
    )


def manual_statement(balance: Decimal, currency: str, as_of: date, declared_daily_burn: Optional[Decimal]) -> str:
    """A hand-entered balance as a one-row statement, with the typed daily spend when there is one."""
    meta = {"declared_daily_burn": _money(declared_daily_burn)} if declared_daily_burn is not None else None
    return _write(
        [[f"{MANUAL_PREFIX}{uuid.uuid4().hex[:10]}", as_of.isoformat(), _money(balance), currency, "Balance entered by owner", _money(balance)]],
        meta,
    )


def append_entry(
    text: str,
    entry_date: date,
    amount: Decimal,
    new_balance: Decimal,
    currency: str,
    description: str,
    declared_daily_burn: Optional[Decimal] = None,
) -> str:
    """The statement with one owner-recorded row added.

    Rows are read in date order and the last closing balance is the current one, so an entry dated before
    the statement's last day is placed on that day (its own date stays in the description) rather than
    rewriting the balances the bank reported.
    """
    meta, body = split_meta(text)
    reader = list(csv.reader(io.StringIO(body)))
    rows = [r for r in reader[1:] if r]
    last_day = max((date.fromisoformat(r[1]) for r in rows), default=entry_date)
    posted = max(entry_date, last_day)
    label = description or "Entry recorded by owner"
    if posted != entry_date:
        label = f"{label} (dated {entry_date.isoformat()})"
    rows.append([f"{MANUAL_PREFIX}{uuid.uuid4().hex[:10]}", posted.isoformat(), _money(amount), currency, label, _money(new_balance)])
    if declared_daily_burn is not None:
        meta = {**meta, "declared_daily_burn": _money(declared_daily_burn)}
    return _write(rows, meta or None)


def declared_burn_applies(meta: dict, rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """The owner's typed daily spend, but only when every row was entered by hand.

    Once real statement rows exist, the burn they show is the measured one and outranks a typed figure.
    """
    value = meta.get("declared_daily_burn")
    if value is None or not rows or not all(r.transaction_id.startswith(MANUAL_PREFIX) for r in rows):
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None
