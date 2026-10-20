"""Reading "I spent ... on ..." into a proposed entry, and leaving questions alone."""

from datetime import date
from decimal import Decimal

import pytest

from services.agent.entry_parser import parse_cash_entry

TODAY = date(2026, 10, 20)


@pytest.mark.parametrize(
    "text,kind,amount,day,desc,account",
    [
        ("I spent $500 on rent today", "OUTFLOW", "500.00", TODAY, "rent", None),
        ("Paid 1,200.50 for payroll yesterday", "OUTFLOW", "1200.50", date(2026, 10, 19), "payroll", None),
        ("We received $3,000 from Acme Foods", "INFLOW", "3000.00", TODAY, "Acme Foods", None),
        ("spent 45.50 on office supplies from my SVB account", "OUTFLOW", "45.50", TODAY, "office supplies", "SVB"),
        ("Got paid 2.5k for the Northwind order on Oct 3", "INFLOW", "2500.00", date(2026, 10, 3), "the Northwind order", None),
        ("I paid €80 for internet 3 days ago", "OUTFLOW", "80.00", date(2026, 10, 17), "internet", None),
        ("Deposited 900 on 2026-10-12", "INFLOW", "900.00", date(2026, 10, 12), "", None),
        ("Paid the Dec 28 invoice 300", "OUTFLOW", "300.00", date(2025, 12, 28), "", None),
    ],
)
def test_reads_cash_statements(text, kind, amount, day, desc, account):
    entry = parse_cash_entry(text, today=TODAY)
    assert entry is not None
    assert entry.adjustment_type == kind
    assert entry.amount == Decimal(amount)
    assert entry.entry_date == day
    assert entry.description == desc
    assert entry.account_hint == account


@pytest.mark.parametrize(
    "text",
    [
        "How much did I spend on rent?",
        "what did we pay for payroll last month",
        "Should I pay the supplier 5,000 now?",
        "I spent a lot on marketing",  # no amount
        "Our revenue is 40,000 a month",  # no direction
        "Explain DSCR",
        "",
    ],
)
def test_leaves_questions_and_vague_sentences_alone(text):
    assert parse_cash_entry(text, today=TODAY) is None


def test_a_year_is_not_read_as_an_amount():
    entry = parse_cash_entry("Paid 2026 taxes 1,500", today=TODAY)
    assert entry is not None and entry.amount == Decimal("1500.00")


@pytest.mark.parametrize(
    "text,amount",
    [
        ("I spent 2000 on rent today", "2000.00"),
        ("Received 1950 from Pier 9", "1950.00"),
        ("Paid 1,800 for the 2025 audit", "1800.00"),
    ],
)
def test_a_bare_year_like_number_is_money_unless_it_reads_as_a_year(text, amount):
    entry = parse_cash_entry(text, today=TODAY)
    assert entry is not None and entry.amount == Decimal(amount)


def test_in_2025_alone_is_not_an_amount():
    assert parse_cash_entry("Paid the supplier in 2025", today=TODAY) is None
