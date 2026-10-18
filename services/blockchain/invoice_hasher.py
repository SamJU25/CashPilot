"""
Consortium Blockchain Invoice Registry Service.
Calculates deterministic canonical SHA-256 hashes for B2B e-invoices.
Maintains double-financing defense matching on-chain invoice registry contracts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from services.security.crypto import open_text

logger = logging.getLogger(__name__)

BLOCKCHAIN_STORAGE_DIR = os.path.abspath(
    os.environ.get("COPILOT_LEDGER_DIR")
    or os.path.join(os.path.dirname(__file__), "../../.data")
)


class InvoiceStatus(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    PLEDGED = "PLEDGED"
    SETTLED = "SETTLED"


class InvoiceAlreadyPledgedError(Exception):
    """Raised when an invoice hash has already been pledged to a lender (double financing)."""


class InvoiceNotPledgedError(Exception):
    """Raised when trying to settle an invoice that was never pledged."""


class InvoicePledgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    invoice_hash: str = Field(description="0x-prefixed 32-byte hexadecimal SHA-256 hash")
    lender_id: int = Field(gt=0, description="Unique identifier of lending institution")
    pledged_timestamp: int = Field(description="Unix timestamp in seconds")
    status: InvoiceStatus
    block_number: Optional[int] = Field(default=None, description="Consortium block height")
    tx_hash: Optional[str] = Field(default=None, description="Consortium transaction hash receipt")


def calculate_canonical_invoice_hash(
    tax_id: str,
    buyer_id: str,
    invoice_num: str,
    amount_cents: int
) -> str:
    """
    Computes a deterministic canonical SHA-256 hash of invoice identity attributes.
    Matches the input format expected by on-chain consortium registry smart contracts.
    """
    if not tax_id.strip() or not buyer_id.strip() or not invoice_num.strip():
        raise ValueError("tax_id, buyer_id, and invoice_num cannot be empty")
    if amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer")

    payload = {
        "amount_cents": amount_cents,
        "buyer_id": buyer_id.strip().upper(),
        "invoice_num": invoice_num.strip().upper(),
        "tax_id": tax_id.strip().upper(),
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sha256_hex = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"0x{sha256_hex}"


class ConsortiumInvoiceRegistry:
    """Thread-safe persistent ledger matching the FISCO BCOS InvoiceRegistry.sol smart contract."""

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self._storage_dir = storage_dir
        self._file_path = os.path.join(self._storage_dir, "blockchain_ledger.json") if self._storage_dir else None
        self._records: dict[str, InvoicePledgeRecord] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.loads(open_text(f.read()))
                for item in data.values():
                    record = InvoicePledgeRecord.model_validate_json(json.dumps(item))
                    self._records[record.invoice_hash] = record
        except Exception as exc:
            logger.warning("Could not load persisted blockchain records from %s: %s", self._file_path, exc)

    def _persist(self) -> None:
        if not self._file_path:
            return
        from services.security.crypto import seal_text
        from services.security.file_utils import ensure_private_dir

        ensure_private_dir(self._storage_dir)
        tmp_path = f"{self._file_path}.tmp"
        try:
            data = {k: v.model_dump(mode="json") for k, v in self._records.items()}
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(seal_text(json.dumps(data, indent=2)))
            os.replace(tmp_path, self._file_path)
            from services.security.file_utils import restrict_file

            restrict_file(self._file_path)
        except OSError as exc:
            logger.warning("Failed to persist blockchain records to %s: %s", self._file_path, exc)

    def pledge_invoice(self, invoice_hash: str, lender_id: int) -> InvoicePledgeRecord:
        """
        Pledges an invoice to a lender. Reverts if already pledged or settled.
        Replicates require(record.status == Status.UNREGISTERED, 'ERR_INVOICE_ALREADY_PLEDGED').
        Generates simulated consortium block receipts (block height and tx hash).
        """
        if lender_id <= 0:
            raise ValueError("lender_id must be a positive integer")

        with self._lock:
            existing = self._records.get(invoice_hash)
            if existing and existing.status in (InvoiceStatus.PLEDGED, InvoiceStatus.SETTLED):
                raise InvoiceAlreadyPledgedError("ERR_INVOICE_ALREADY_PLEDGED")

            now = int(time.time())
            block_number = 100000 + len(self._records) + 1
            tx_seed = f"{invoice_hash}:{lender_id}:{now}:{block_number}"
            tx_hash = f"0x{hashlib.sha256(tx_seed.encode('utf-8')).hexdigest()}"

            record = InvoicePledgeRecord(
                invoice_hash=invoice_hash,
                lender_id=lender_id,
                pledged_timestamp=now,
                status=InvoiceStatus.PLEDGED,
                block_number=block_number,
                tx_hash=tx_hash,
            )
            self._records[invoice_hash] = record
            self._persist()
            return record

    def settle_invoice(self, invoice_hash: str) -> InvoicePledgeRecord:
        """
        Settles a pledged invoice upon loan repayment.
        Replicates require(record.status == Status.PLEDGED, 'ERR_INVOICE_NOT_PLEDGED').
        """
        with self._lock:
            existing = self._records.get(invoice_hash)
            if not existing or existing.status != InvoiceStatus.PLEDGED:
                raise InvoiceNotPledgedError("ERR_INVOICE_NOT_PLEDGED")

            settled = existing.model_copy(update={"status": InvoiceStatus.SETTLED})
            self._records[invoice_hash] = settled
            self._persist()
            return settled

    def get_invoice_status(self, invoice_hash: str) -> InvoiceStatus:
        """Queries the current on-chain status of an invoice hash."""
        with self._lock:
            record = self._records.get(invoice_hash)
            return record.status if record else InvoiceStatus.UNREGISTERED

    def get_record(self, invoice_hash: str) -> Optional[InvoicePledgeRecord]:
        """Queries the complete pledge record."""
        with self._lock:
            return self._records.get(invoice_hash)

    def clear(self) -> None:
        """Clears all records (used for test isolation)."""
        with self._lock:
            self._records.clear()
            if self._file_path and os.path.exists(self._file_path):
                try:
                    os.remove(self._file_path)
                except OSError:
                    pass


# Shared singleton instance
invoice_registry = ConsortiumInvoiceRegistry(storage_dir=BLOCKCHAIN_STORAGE_DIR)
