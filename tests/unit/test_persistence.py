"""
Unit tests for disk persistence across process restarts.
Verifies crash-safe storage for StagingLedger, PasskeyRegistry, and ConsortiumInvoiceRegistry.
"""

import tempfile
import pytest

from services.blockchain.invoice_hasher import (
    ConsortiumInvoiceRegistry,
    InvoiceStatus,
    calculate_canonical_invoice_hash,
)
from services.security.passkeys import PasskeyRegistry, _StoredCredential
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


def test_passkey_registry_disk_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        registry1 = PasskeyRegistry(
            rp_id="localhost",
            rp_name="Test",
            origins=["http://localhost:3000"],
            storage_dir=tmp_dir,
        )
        # Directly store a credential to test serialization round-trip
        tenant = "SME-TENANT-PERSIST"
        cred_id = b"cred_id_bytes_12345"
        pub_key = b"pub_key_bytes_67890"
        registry1._credentials[tenant] = _StoredCredential(
            credential_id=cred_id,
            public_key=pub_key,
            sign_count=42,
        )
        registry1._persist()

        # Simulate process restart
        registry2 = PasskeyRegistry(
            rp_id="localhost",
            rp_name="Test",
            origins=["http://localhost:3000"],
            storage_dir=tmp_dir,
        )
        assert registry2.has_passkey(tenant) is True
        stored = registry2._credentials[tenant]
        assert stored.credential_id == cred_id
        assert stored.public_key == pub_key
        assert stored.sign_count == 42


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
