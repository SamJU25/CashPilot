"""Turns a statement like "I spent $500 on rent yesterday" into a proposed cash entry.

Deterministic on purpose: the owner confirms every entry on a card before anything changes, and the card
shows exactly what was read, so a rule-based reading that is wrong is visible and harmless. Questions
("how much did I spend on rent?") and sentences without both a direction and an amount are not entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

OUT_VERBS = r"spent|spend|paid|pay(?:ed)?|bought|purchased|sent|wired|withdrew|transferred\s+out|lost|refunded"
IN_VERBS = r"received|receive|got\s+paid|was\s+paid|were\s+paid|earned|collected|deposited|sold|came\s+in|invoiced\s+and\s+got"
QUESTION_START = re.compile(r"^\s*(?:how|what|why|when|where|which|who|should|can|could|would|will|do|does|did|is|are|am)\b", re.I)
DIRECTION = re.compile(rf"\b(?P<out>{OUT_VERBS})\b|\b(?P<in>{IN_VERBS})\b", re.I)
# A money amount: optional symbol, thousands separators, up to 2 decimals, optional k. Dates are removed first.
AMOUNT = re.compile(r"(?P<sym>[$€£৳₹¥])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s?(?P<k>[kK])?\b")
ISO_DATE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH_DAY = re.compile(r"\b(?:on\s+)?(?:(?P<mon1>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<day1>\d{1,2})(?:st|nd|rd|th)?|(?P<day2>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon2>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b", re.I)
YEAR_CONTEXT = re.compile(r"\b(?:in|of|since|during|year|fy)\s*$", re.I)
DAYS_AGO = re.compile(r"\b(?P<n>\d{1,2})\s+days?\s+ago\b", re.I)
# Account names are one to four words that are not prepositions, e.g. "from my SVB account".
_WORD = r"(?!(?:from|in|on|for|to|into|via|with|of)\b)[A-Za-z][\w&'-]*"
ACCOUNT = re.compile(rf"\b(?:from|in|out\s+of|into|via|with)\s+(?:my\s+|our\s+|the\s+)?(?P<acc>{_WORD}(?:\s+{_WORD}){{0,3}}?)\s+(?:account|card|bank)\b", re.I)
DESCRIPTION = re.compile(r"\b(?:on|for|to|from)\s+(?P<desc>[^.,;!]+)", re.I)
FILLER = re.compile(r"\b(?:today|yesterday|this\s+morning|last\s+night|\d{1,2}\s+days?\s+ago)\b", re.I)


@dataclass(frozen=True)
class CashEntry:
    adjustment_type: Literal["INFLOW", "OUTFLOW"]
    amount: Decimal
    entry_date: date
    description: str
    account_hint: Optional[str]


def _entry_date(text: str, today: date) -> tuple[date, str]:
    """The date the sentence names (defaults to today) and the text with that date removed."""
    if re.search(r"\byesterday\b|\blast\s+night\b", text, re.I):
        return today - timedelta(days=1), text
    if m := DAYS_AGO.search(text):
        return today - timedelta(days=int(m["n"])), text
    if m := ISO_DATE.search(text):
        try:
            return date(int(m["y"]), int(m["m"]), int(m["d"])), text[: m.start()] + text[m.end():]
        except ValueError:
            pass
    if m := MONTH_DAY.search(text):
        month = MONTHS[(m["mon1"] or m["mon2"]).lower()[:3]]
        day = int(m["day1"] or m["day2"])
        try:
            when = date(today.year, month, day)
            # "Dec 28" said in January means last December, never a future date.
            if when > today:
                when = date(today.year - 1, month, day)
            return when, text[: m.start()] + text[m.end():]
        except ValueError:
            pass
    return today, text


def parse_cash_entry(message: str, today: Optional[date] = None) -> Optional[CashEntry]:
    """A proposed entry for the owner to confirm, or None when the message is not a cash statement."""
    text = (message or "").strip()
    if not text or len(text) > 300 or text.endswith("?") or QUESTION_START.match(text):
        return None
    direction = DIRECTION.search(text)
    if not direction:
        return None

    today = today or date.today()
    when, rest = _entry_date(text, today)
    found = list(AMOUNT.finditer(rest))

    # "spent 2000 on rent" is money; "in 2025" or a second number beside it makes a bare 1900-2100 a year.
    def year_like(m: re.Match) -> bool:
        return not m["sym"] and not m["k"] and m["num"].isdigit() and len(m["num"]) == 4 and 1900 <= int(m["num"]) <= 2100

    def money_like(m: re.Match) -> bool:
        return bool(m["sym"] or m["k"] or "," in m["num"] or "." in m["num"] or Decimal(m["num"]) >= 100)

    # Only a clearly monetary number competes with a year; "Pier 9" does not.
    has_other = any(money_like(m) and not year_like(m) for m in found)
    amounts = [m for m in found if not (year_like(m) and (has_other or YEAR_CONTEXT.search(rest[: m.start()])))]
    if not amounts:
        return None
    chosen = next((m for m in amounts if m["sym"]), amounts[0])
    try:
        amount = Decimal(chosen["num"].replace(",", ""))
    except InvalidOperation:
        return None
    if chosen["k"]:
        amount *= 1000
    if amount <= 0 or amount >= Decimal("100000000000000"):
        return None

    # What is left after removing the amount, the account phrase and date words describes the entry.
    described = rest[: chosen.start()] + " " + rest[chosen.end():]
    account = ACCOUNT.search(described)
    account_hint = account["acc"].strip() if account else None
    if account:
        described = described[: account.start()] + " " + described[account.end():]
    described = FILLER.sub("", described)
    desc_match = DESCRIPTION.search(described)
    description = re.sub(r"\s+", " ", desc_match["desc"]).strip(" -") if desc_match else ""

    return CashEntry(
        adjustment_type="OUTFLOW" if direction["out"] else "INFLOW",
        amount=amount.quantize(Decimal("0.01")),
        entry_date=when,
        description=description[:120],
        account_hint=account_hint,
    )
