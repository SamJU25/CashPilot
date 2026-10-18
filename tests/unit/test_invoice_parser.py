"""Unit tests for universal invoice CSV and dictionary ingestion."""

from datetime import date
from decimal import Decimal
import pytest

from services.ingestion.invoice_parser import (
    InvoiceIngestionError,
    InvoiceRecord,
    parse_invoice_csv,
    parse_invoices_from_dicts,
)


SAMPLE_INVOICE_CSV = """invoice_id,customer_name,issue_date,due_date,amount,status
INV-001,Acme Industrial,2026-08-01,2026-08-31,"$15,000.00",UNPAID
INV-002,Globex Corp,2026-09-01,2026-10-01,"$8,500.50",UNPAID
INV-003,Stark Industries,2026-09-15,2026-10-15,"$22,000.00",PAID
INV-004,Wayne Enterprises,2026-07-01,2026-07-31,"$12,000.00",UNPAID
"""


def test_parse_invoice_csv_basic():
    result = parse_invoice_csv(SAMPLE_INVOICE_CSV)
    assert result.currency == "USD"
    assert len(result.accepted_invoices) == 4
    assert len(result.rejected_rows) == 0

    inv1 = result.accepted_invoices[0]
    assert inv1.invoice_id == "INV-001"
    assert inv1.customer_name == "Acme Industrial"
    assert inv1.issue_date == date(2026, 8, 1)
    assert inv1.due_date == date(2026, 8, 31)
    assert inv1.amount == Decimal("15000.00")
    assert inv1.open_amount == Decimal("15000.00")

    # Paid invoice open amount must be 0
    inv3 = result.accepted_invoices[2]
    assert inv3.status == "PAID"
    assert inv3.open_amount == Decimal("0.00")


def test_parse_invoice_csv_alternate_headers_and_dates():
    alt_csv = """RefNo,Client,Date,Payment Due,Total,Paid
REF-101,Initech LLC,08/15/2026,09/15/2026,5000.00,1000.00
REF-102,Umbrella Corp,08/20/2026,09/20/2026,7500.00,0.00
"""
    result = parse_invoice_csv(alt_csv)
    assert len(result.accepted_invoices) == 2
    inv1 = result.accepted_invoices[0]
    assert inv1.invoice_id == "REF-101"
    assert inv1.customer_name == "Initech LLC"
    assert inv1.issue_date == date(2026, 8, 15)
    assert inv1.due_date == date(2026, 9, 15)
    assert inv1.amount == Decimal("5000.00")
    assert inv1.paid_amount == Decimal("1000.00")
    assert inv1.open_amount == Decimal("4000.00")


def test_parse_invoice_csv_rejected_rows():
    bad_csv = """invoice_id,customer,due_date,amount
INV-A,,2026-09-01,1000.00
INV-B,Good Client,invalid-date,2000.00
INV-C,Good Client,2026-09-01,not-a-number
INV-D,Valid Client,2026-09-01,3500.00
"""
    result = parse_invoice_csv(bad_csv)
    assert len(result.accepted_invoices) == 1
    assert len(result.rejected_rows) == 3

    reasons = [r.reason_code for r in result.rejected_rows]
    assert "MISSING_CUSTOMER" in reasons
    assert "INVALID_DATE" in reasons
    assert "INVALID_AMOUNT" in reasons


def test_parse_invoice_csv_empty_and_invalid_header():
    with pytest.raises(InvoiceIngestionError) as exc_empty:
        parse_invoice_csv("")
    assert exc_empty.value.code == "EMPTY_FILE"

    with pytest.raises(InvoiceIngestionError) as exc_hdr:
        parse_invoice_csv("col_a,col_b\n1,2")
    assert exc_hdr.value.code == "INVALID_HEADER"


def test_parse_invoices_from_dicts():
    records = [
        {
            "invoice_id": "INV-X",
            "customer": "Cyberdyne Systems",
            "amount": "14000.00",
            "due_date": "2026-10-01",
            "status": "UNPAID",
        },
        {
            "customer": "Soylent Corp",
            "amount": 6000,
            "due_date": date(2026, 9, 15),
            "paid_amount": 2000,
        },
    ]
    result = parse_invoices_from_dicts(records)
    assert len(result.accepted_invoices) == 2
    assert result.accepted_invoices[0].amount == Decimal("14000.00")
    assert result.accepted_invoices[1].open_amount == Decimal("4000.00")
