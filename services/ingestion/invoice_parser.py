"""Universal Invoice CSV & Structured Data Ingestion Service.

Parses accounts receivable invoice records for aging analysis, concentration risk,
and collections tracking. Follows strict row-level error provenance and pure Decimal conversion.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Sequence, Tuple

from services.ingestion.financial_parsers import (
    _detect_delimiter,
    _normalize_col_name,
    _parse_universal_amount,
    _parse_universal_date,
)


class InvoiceIngestionError(ValueError):
    """File-level or schema error during invoice parsing with stable error codes."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InvoiceRecord:
    row_number: int
    invoice_id: str
    customer_name: str
    issue_date: date
    due_date: date
    amount: Decimal
    currency: str = "USD"
    status: str = "UNPAID"
    paid_amount: Decimal = Decimal("0.00")

    @property
    def open_amount(self) -> Decimal:
        """Remaining unpaid balance on the invoice."""
        if self.status.upper() in ("PAID", "SETTLED", "CLOSED"):
            return Decimal("0.00")
        bal = self.amount - self.paid_amount
        return bal if bal > Decimal("0.00") else Decimal("0.00")


@dataclass(frozen=True)
class InvoiceRejectedRow:
    row_number: int
    reason_code: str
    raw_content: Optional[str] = None


@dataclass(frozen=True)
class InvoiceIngestionResult:
    currency: str
    accepted_invoices: List[InvoiceRecord]
    rejected_rows: List[InvoiceRejectedRow]
    total_invoiced_amount: Decimal = Decimal("0.00")
    total_open_amount: Decimal = Decimal("0.00")


_INVOICE_ID_ALIASES = {
    "invoiceid", "id", "invoiceno", "invoicenumber", "invno", "billid", "referenceno", "refno", "number"
}
_CUSTOMER_ALIASES = {
    "customername", "customer", "client", "clientname", "debtor", "buyer", "counterparty", "accountname", "name"
}
_ISSUE_DATE_ALIASES = {
    "issuedate", "invoicedate", "date", "createddate", "issuedon", "issued", "postdate", "postingdate"
}
_DUE_DATE_ALIASES = {
    "duedate", "due", "paymentduedate", "paymentdue", "termsdate", "expirydate", "maturitydate"
}
_AMOUNT_ALIASES = {
    "amount", "total", "balance", "openbalance", "invoiceamount", "grandtotal", "totalamount", "invoicedamount"
}
_PAID_AMOUNT_ALIASES = {
    "paidamount", "amountpaid", "paid", "received", "payments"
}
_STATUS_ALIASES = {
    "status", "state", "paymentstatus", "invoicestatus"
}
_CURRENCY_ALIASES = {
    "currency", "curr", "ccy"
}


def _match_column(headers: List[str], aliases: set[str]) -> Optional[int]:
    for idx, h in enumerate(headers):
        norm = _normalize_col_name(h)
        if norm in aliases:
            return idx
    return None


def parse_invoice_csv(
    csv_content: str,
    tenant_id: str = "SME-DEFAULT",
) -> InvoiceIngestionResult:
    """Parses raw CSV string containing accounts receivable invoices.

    Returns an InvoiceIngestionResult with accepted InvoiceRecords and row-level rejection codes.
    """
    raw_text = csv_content.strip()
    if not raw_text:
        raise InvoiceIngestionError("EMPTY_FILE", "Invoice CSV content is empty.")

    delimiter = _detect_delimiter(raw_text)
    reader = csv.reader(io.StringIO(raw_text), delimiter=delimiter)

    try:
        header_row = next(reader)
    except StopIteration:
        raise InvoiceIngestionError("EMPTY_FILE", "Invoice CSV has no rows.")

    cleaned_headers = [h.strip() for h in header_row]
    col_id = _match_column(cleaned_headers, _INVOICE_ID_ALIASES)
    col_cust = _match_column(cleaned_headers, _CUSTOMER_ALIASES)
    col_issue = _match_column(cleaned_headers, _ISSUE_DATE_ALIASES)
    col_due = _match_column(cleaned_headers, _DUE_DATE_ALIASES)
    col_amt = _match_column(cleaned_headers, _AMOUNT_ALIASES)
    col_paid = _match_column(cleaned_headers, _PAID_AMOUNT_ALIASES)
    col_status = _match_column(cleaned_headers, _STATUS_ALIASES)
    col_ccy = _match_column(cleaned_headers, _CURRENCY_ALIASES)

    # Minimal required: customer and amount, plus at least one date (due date or issue date)
    if col_cust is None or col_amt is None or (col_due is None and col_issue is None):
        raise InvoiceIngestionError(
            "INVALID_HEADER",
            "Invoice CSV must contain at least customer, amount, and due_date (or issue_date) columns.",
        )

    accepted: List[InvoiceRecord] = []
    rejected: List[InvoiceRejectedRow] = []
    detected_currency = "USD"
    seen_ids: set[str] = set()

    row_num = 1  # 1 is header
    for raw_row in reader:
        row_num += 1
        if not raw_row or all(not cell.strip() for cell in raw_row):
            continue

        # Extract Customer
        cust_val = raw_row[col_cust].strip() if col_cust < len(raw_row) else ""
        if not cust_val:
            rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="MISSING_CUSTOMER"))
            continue

        # Extract Amount
        amt_str = raw_row[col_amt].strip() if col_amt < len(raw_row) else ""
        try:
            amt_val, row_ccy = _parse_universal_amount(amt_str)
            if row_ccy:
                detected_currency = row_ccy
        except (ValueError, InvalidOperation):
            rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="INVALID_AMOUNT"))
            continue

        if amt_val <= Decimal("0.00"):
            rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="INVALID_AMOUNT"))
            continue

        # Extract Dates
        due_val: Optional[date] = None
        issue_val: Optional[date] = None

        if col_due is not None and col_due < len(raw_row) and raw_row[col_due].strip():
            try:
                due_val = _parse_universal_date(raw_row[col_due].strip())
            except ValueError:
                rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="INVALID_DATE"))
                continue

        if col_issue is not None and col_issue < len(raw_row) and raw_row[col_issue].strip():
            try:
                issue_val = _parse_universal_date(raw_row[col_issue].strip())
            except ValueError:
                if due_val is None:
                    rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="INVALID_DATE"))
                    continue

        if due_val is None:
            # Fall back to issue date + 30 days default terms
            if issue_val is not None:
                from datetime import timedelta
                due_val = issue_val + timedelta(days=30)
            else:
                rejected.append(InvoiceRejectedRow(row_number=row_num, reason_code="INVALID_DATE"))
                continue

        if issue_val is None:
            issue_val = due_val

        # Extract Invoice ID
        inv_id = (
            raw_row[col_id].strip()
            if (col_id is not None and col_id < len(raw_row) and raw_row[col_id].strip())
            else f"INV-{row_num:04d}"
        )
        if inv_id in seen_ids:
            inv_id = f"{inv_id}-R{row_num}"
        seen_ids.add(inv_id)

        # Extract Currency if explicitly columned
        if col_ccy is not None and col_ccy < len(raw_row) and raw_row[col_ccy].strip():
            detected_currency = raw_row[col_ccy].strip().upper()

        # Extract Status
        status_val = "UNPAID"
        if col_status is not None and col_status < len(raw_row) and raw_row[col_status].strip():
            status_val = raw_row[col_status].strip().upper()

        # Extract Paid Amount
        paid_val = Decimal("0.00")
        if col_paid is not None and col_paid < len(raw_row) and raw_row[col_paid].strip():
            try:
                p_amt, _ = _parse_universal_amount(raw_row[col_paid].strip())
                if p_amt > Decimal("0.00"):
                    paid_val = p_amt
            except Exception:
                pass

        record = InvoiceRecord(
            row_number=row_num,
            invoice_id=inv_id,
            customer_name=cust_val,
            issue_date=issue_val,
            due_date=due_val,
            amount=amt_val,
            currency=detected_currency,
            status=status_val,
            paid_amount=paid_val,
        )
        accepted.append(record)

    total_invoiced = sum((r.amount for r in accepted), Decimal("0.00"))
    total_open = sum((r.open_amount for r in accepted), Decimal("0.00"))

    return InvoiceIngestionResult(
        currency=detected_currency,
        accepted_invoices=accepted,
        rejected_rows=rejected,
        total_invoiced_amount=total_invoiced,
        total_open_amount=total_open,
    )


def parse_invoices_from_dicts(records: Sequence[dict[str, Any]]) -> InvoiceIngestionResult:
    """Parses a sequence of invoice dictionaries into typed InvoiceRecords."""
    accepted: List[InvoiceRecord] = []
    rejected: List[InvoiceRejectedRow] = []
    detected_currency = "USD"

    for idx, item in enumerate(records, start=1):
        cust = str(item.get("customer_name") or item.get("customer") or item.get("client") or "").strip()
        if not cust:
            rejected.append(InvoiceRejectedRow(row_number=idx, reason_code="MISSING_CUSTOMER"))
            continue

        amt_raw = item.get("amount") or item.get("open_amount") or item.get("total") or 0
        try:
            amt_val = Decimal(str(amt_raw))
        except (InvalidOperation, ValueError):
            rejected.append(InvoiceRejectedRow(row_number=idx, reason_code="INVALID_AMOUNT"))
            continue

        if amt_val <= Decimal("0.00"):
            rejected.append(InvoiceRejectedRow(row_number=idx, reason_code="INVALID_AMOUNT"))
            continue

        # Dates
        due_raw = item.get("due_date") or item.get("due")
        issue_raw = item.get("issue_date") or item.get("date")

        due_val: Optional[date] = None
        issue_val: Optional[date] = None

        if due_raw:
            try:
                due_val = due_raw if isinstance(due_raw, date) else _parse_universal_date(str(due_raw))
            except Exception:
                pass

        if issue_raw:
            try:
                issue_val = issue_raw if isinstance(issue_raw, date) else _parse_universal_date(str(issue_raw))
            except Exception:
                pass

        if due_val is None and issue_val is not None:
            from datetime import timedelta
            due_val = issue_val + timedelta(days=30)
        elif due_val is not None and issue_val is None:
            issue_val = due_val

        if due_val is None:
            rejected.append(InvoiceRejectedRow(row_number=idx, reason_code="INVALID_DATE"))
            continue

        inv_id = str(item.get("invoice_id") or item.get("id") or f"INV-{idx:04d}")
        ccy = str(item.get("currency") or "USD").upper()
        status_val = str(item.get("status") or "UNPAID").upper()

        paid_raw = item.get("paid_amount") or Decimal("0.00")
        try:
            paid_val = Decimal(str(paid_raw))
        except Exception:
            paid_val = Decimal("0.00")

        accepted.append(
            InvoiceRecord(
                row_number=idx,
                invoice_id=inv_id,
                customer_name=cust,
                issue_date=issue_val,
                due_date=due_val,
                amount=amt_val,
                currency=ccy,
                status=status_val,
                paid_amount=paid_val,
            )
        )

    total_invoiced = sum((r.amount for r in accepted), Decimal("0.00"))
    total_open = sum((r.open_amount for r in accepted), Decimal("0.00"))

    return InvoiceIngestionResult(
        currency=detected_currency,
        accepted_invoices=accepted,
        rejected_rows=rejected,
        total_invoiced_amount=total_invoiced,
        total_open_amount=total_open,
    )
