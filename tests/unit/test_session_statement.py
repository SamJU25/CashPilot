"""The session's canonical statement: layout, appended entries, and the typed-spend setting."""

from datetime import date
from decimal import Decimal

from services.agent.tools import _normalize_statement_bytes, tool_analyze_cash_flow
from services.ingestion.csv_parser import DemoTransaction, parse_bank_csv
from services.ingestion.session_statement import (
    append_entry,
    canonical_csv,
    declared_burn_applies,
    manual_statement,
    split_meta,
)

D = Decimal


def tx(n, day, amount, closing, desc="Card, with comma"):
    return DemoTransaction(n, f"t{n}", date(2026, 10, day), D(amount), "USD", desc, D(closing))


def test_canonical_statement_round_trips_through_the_parser():
    text = canonical_csv([tx(2, 2, "5", "95"), tx(1, 1, "-10", "90")], "USD")
    rows = parse_bank_csv(_normalize_statement_bytes(text)).accepted_rows
    assert [r.closing_balance for r in rows] == [D("90.00"), D("95.00")]
    assert rows[0].description == "Card, with comma"


def test_entry_dated_before_the_statement_end_is_placed_on_the_last_day():
    text = append_entry(canonical_csv([tx(1, 5, "-10", "90")], "USD"), date(2026, 10, 3), D("-20"), D("70"), "USD", "Taxi")
    rows = parse_bank_csv(_normalize_statement_bytes(text)).accepted_rows
    assert rows[-1].posted_on == date(2026, 10, 5)
    assert rows[-1].closing_balance == D("70.00")
    assert "dated 2026-10-03" in rows[-1].description


def test_typed_spend_applies_only_to_hand_entered_statements():
    manual = manual_statement(D("42000"), "USD", date(2026, 10, 20), D("500"))
    meta, _ = split_meta(manual)
    rows = parse_bank_csv(_normalize_statement_bytes(manual)).accepted_rows
    assert declared_burn_applies(meta, rows) == D("500.00")
    assert tool_analyze_cash_flow(manual)["runway_days"] == 84

    mixed = append_entry(canonical_csv([tx(1, 1, "-10", "90")], "USD"), date(2026, 10, 20), D("5"), D("95"), "USD", "", D("500"))
    meta, _ = split_meta(mixed)
    assert declared_burn_applies(meta, parse_bank_csv(_normalize_statement_bytes(mixed)).accepted_rows) is None
