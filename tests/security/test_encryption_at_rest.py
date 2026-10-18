"""Tests for optional Fernet encryption at rest on session and .data stores."""

import importlib

import pytest
from cryptography.fernet import Fernet

from services.blockchain.invoice_hasher import ConsortiumInvoiceRegistry
from services.security.crypto import (
    MAGIC,
    DataDecryptionError,
    DataEncryptionError,
    open_text,
    seal_text,
    validate_configuration,
)
from services.security.passkeys import PasskeyRegistry, _StoredCredential
from services.security.staging_ledger import StagingLedger, StagingRequest


@pytest.fixture
def data_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("COPILOT_DATA_KEY", key)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    return key


def test_seal_round_trip_and_legacy_plaintext(data_key):
    sealed = seal_text('{"secret": "cash"}')

    assert sealed.startswith(MAGIC)
    assert "cash" not in sealed
    assert open_text(sealed) == '{"secret": "cash"}'
    # Files written before encryption was enabled stay readable.
    assert open_text('{"legacy": true}') == '{"legacy": true}'


def test_wrong_key_fails_clearly(monkeypatch, data_key):
    sealed = seal_text("payload")
    monkeypatch.setenv("COPILOT_DATA_KEY", Fernet.generate_key().decode())

    with pytest.raises(DataDecryptionError):
        open_text(sealed)


def test_deployed_environment_requires_a_data_key(monkeypatch):
    monkeypatch.delenv("COPILOT_DATA_KEY", raising=False)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("COPILOT_ENV", "production")

    with pytest.raises(DataEncryptionError):
        validate_configuration()


def test_local_environment_may_run_without_a_data_key(monkeypatch):
    monkeypatch.delenv("COPILOT_DATA_KEY", raising=False)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("COPILOT_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    validate_configuration()


def test_invalid_key_fails_at_startup(monkeypatch):
    monkeypatch.setenv("COPILOT_DATA_KEY", "not-a-fernet-key")

    with pytest.raises(DataDecryptionError):
        validate_configuration()


def test_missing_key_rejects_a_sealed_payload(monkeypatch, data_key):
    sealed = seal_text("payload")
    monkeypatch.delenv("COPILOT_DATA_KEY", raising=False)

    with pytest.raises(DataDecryptionError):
        open_text(sealed)


def test_staging_ledger_encrypts_and_reloads(tmp_path, data_key):
    path = tmp_path / "ledger"
    ledger = StagingLedger(storage_dir=str(path))
    intent = ledger.stage_intent(
        StagingRequest(
            tenant_id="TENANT-CRYPTO",
            action_type="TRANSFER",
            amount_cents=100,
            target_identifier="ACC-SECRET",
        )
    )

    raw = (path / "staged_intents.json").read_text(encoding="utf-8")
    assert raw.startswith(MAGIC)
    assert "ACC-SECRET" not in raw

    reopened = StagingLedger(storage_dir=str(path))
    assert reopened.get_intent(intent.id).target_identifier == "ACC-SECRET"


def test_session_store_encrypts_and_reloads(tmp_path, monkeypatch, data_key):
    store_module = importlib.import_module("services.agent.session_store")
    monkeypatch.setattr(store_module, "SESSION_CACHE_DIR", str(tmp_path))

    store = store_module.SessionStore()
    record = store.get_or_create("sess_crypto", tenant_id="TENANT-CRYPTO")
    store.update_statement(
        record.session_id,
        "transaction_id,date,amount\n1,2026-01-01,10.00",
        tenant_id="TENANT-CRYPTO",
    )

    raw = (tmp_path / "sess_crypto.json").read_text(encoding="utf-8")
    assert raw.startswith(MAGIC)
    assert "transaction_id" not in raw

    reopened = store_module.SessionStore()
    assert reopened.get("sess_crypto").csv_content.startswith("transaction_id")


def test_passkey_store_encrypts_and_reloads(tmp_path, data_key):
    storage = str(tmp_path / "passkeys")
    registry = PasskeyRegistry(
        rp_id="localhost",
        rp_name="Test",
        origins=["http://localhost:3000"],
        storage_dir=storage,
    )
    registry._credentials["TENANT-CRYPTO"] = _StoredCredential(
        credential_id=b"credential-id",
        public_key=b"public-key",
        sign_count=0,
    )
    registry._persist()

    raw = (tmp_path / "passkeys" / "passkeys.json").read_text(encoding="utf-8")
    assert raw.startswith(MAGIC)
    assert "credential-id" not in raw

    reopened = PasskeyRegistry(
        rp_id="localhost",
        rp_name="Test",
        origins=["http://localhost:3000"],
        storage_dir=storage,
    )
    assert reopened.has_passkey("TENANT-CRYPTO")


def test_invoice_registry_encrypts_and_reloads(tmp_path, data_key):
    storage = str(tmp_path / "chain")
    registry = ConsortiumInvoiceRegistry(storage_dir=storage)
    invoice_hash = "0x" + "a" * 64
    registry.pledge_invoice(invoice_hash, lender_id=7)

    raw = (tmp_path / "chain" / "blockchain_ledger.json").read_text(encoding="utf-8")
    assert raw.startswith(MAGIC)
    assert invoice_hash not in raw

    reopened = ConsortiumInvoiceRegistry(storage_dir=storage)
    assert reopened.get_record(invoice_hash) is not None
