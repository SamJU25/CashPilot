"""
Unit tests for disk persistence across process restarts.
Verifies crash-safe storage for StagingLedger and ConsortiumInvoiceRegistry.
"""

import tempfile
import pytest

from services.blockchain.invoice_hasher import (
    ConsortiumInvoiceRegistry,
    InvoiceStatus,
    calculate_canonical_invoice_hash,
)
from services.security.staging_ledger import StagingLedger, StagingRequest


def test_staging_ledger_disk_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger1 = StagingLedger(storage_dir=tmp_dir)
        intent = ledger1.stage_intent(
            StagingRequest(
                tenant_id="SME-CORP-01",
                action_type="FACTOR_INVOICE",
                amount_cents=500000,
                target_identifier="INV-1001",
            )
        )
        assert intent.id.startswith("intent-")

        # Simulate process restart by creating a new instance pointing to same dir
        ledger2 = StagingLedger(storage_dir=tmp_dir)
        restored_intent = ledger2.get_intent(intent.id)
        assert restored_intent.tenant_id == "SME-CORP-01"
        assert restored_intent.amount_cents == 500000
        assert restored_intent.target_identifier == "INV-1001"
        assert restored_intent.status == "STAGED_PENDING_HITL"


def test_consortium_invoice_registry_disk_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg1 = ConsortiumInvoiceRegistry(storage_dir=tmp_dir)
        inv_hash = calculate_canonical_invoice_hash("TAX-999", "BUYER-ABC", "INV-2026-X", 750000)
        record = reg1.pledge_invoice(inv_hash, lender_id=202)
        assert record.status == InvoiceStatus.PLEDGED
        assert record.block_number is not None
        assert record.tx_hash is not None and record.tx_hash.startswith("0x")

        # Simulate process restart
        reg2 = ConsortiumInvoiceRegistry(storage_dir=tmp_dir)
        assert reg2.get_invoice_status(inv_hash) == InvoiceStatus.PLEDGED
        restored = reg2.get_record(inv_hash)
        assert restored is not None
        assert restored.lender_id == 202
        assert restored.block_number == record.block_number
        assert restored.tx_hash == record.tx_hash
