"""
Unit tests for the Three-Tier Security Gate and Staging Ledger.
Verifies proposal staging, deduplication, expiry, and the owner's two decisions: prepare or dismiss.
There is no execution path to test: CashPilot never moves money.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from services.security import (
    StagingLedger,
    StagingRequest,
    ActionStatus,
    IntentNotFoundError,
    IntentStateError,
)

TENANT = "SME-100"


@pytest.fixture
def ledger():
    test_ledger = StagingLedger()
    yield test_ledger
    test_ledger.clear()


def _stage(ledger, action_type="TRANSFER", amount_cents=100000, target="ACC-998877"):
    return ledger.stage_intent(
        StagingRequest(tenant_id=TENANT, action_type=action_type, amount_cents=amount_cents, target_identifier=target)
    )


def test_repeated_instruction_reuses_the_pending_proposal(ledger):
    first = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=500000, target="INV-DEDUPE")
    second = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=500000, target="INV-DEDUPE")

    assert second.id == first.id
    assert len(ledger.list_intents()) == 1


def test_a_different_target_is_a_new_proposal(ledger):
    first = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=500000, target="INV-A")
    second = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=500000, target="INV-B")

    assert second.id != first.id
    assert len(ledger.list_intents()) == 2


def test_expired_pending_proposals_are_purged(ledger, monkeypatch):
    import sys

    # services.security re-exports the singleton under the same name, so reach the module via sys.modules.
    ledger_module = sys.modules["services.security.staging_ledger"]
    monkeypatch.setattr(ledger_module, "STAGED_INTENT_TTL_HOURS", 1)
    stale = _stage(ledger, action_type="TRANSFER", amount_cents=1000, target="ACC-OLD")
    with ledger._lock:
        ledger._intents[stale.id] = stale.model_copy(
            update={"staged_at": datetime.now(timezone.utc) - timedelta(hours=2)}
        )

    fresh = _stage(ledger, action_type="TRANSFER", amount_cents=1000, target="ACC-NEW")
    remaining = {intent.id for intent in ledger.list_intents()}
    assert stale.id not in remaining
    assert fresh.id in remaining


def test_stage_intent_creates_pending_proposal(ledger):
    intent = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=500000, target="INV-2026-001")

    assert intent.id.startswith("intent-")
    assert intent.tenant_id == TENANT
    assert intent.action_type == "FACTOR_INVOICE"
    assert intent.amount_cents == 500000
    assert intent.status == ActionStatus.STAGED_PENDING_HITL.value


def test_the_ledger_offers_no_way_to_execute(ledger):
    assert not hasattr(ledger, "execute_intent")
    assert "EXECUTED" not in {s.value for s in ActionStatus}


def test_prepare_records_the_owners_decision(ledger):
    intent = _stage(ledger, action_type="DRAW_CREDIT_LINE", amount_cents=750000, target="Harbor Community Bank")
    prepared = ledger.prepare_intent(intent.id)

    assert prepared.status == ActionStatus.PREPARED.value
    assert ledger.get_intent(intent.id).status == ActionStatus.PREPARED.value


def test_a_decided_intent_cannot_change_again(ledger):
    intent = _stage(ledger, action_type="DRAW_CREDIT_LINE", amount_cents=50000, target="FACILITY-01")
    ledger.prepare_intent(intent.id)

    with pytest.raises(IntentStateError):
        ledger.prepare_intent(intent.id)
    with pytest.raises(IntentStateError):
        ledger.reject_intent(intent.id)


def test_reject_staged_intent(ledger):
    intent = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=150000, target="INV-002")
    rejected = ledger.reject_intent(intent.id)
    assert rejected.status == ActionStatus.REJECTED.value

    with pytest.raises(IntentStateError):
        ledger.prepare_intent(intent.id)


def test_ledger_written_before_passkey_removal_still_loads(tmp_path):
    # Older ledgers stored a biometric_signature on every intent; loading must not drop them.
    legacy = {
        "intent-old": {
            "id": "intent-old",
            "tenant_id": TENANT,
            "action_type": "TRANSFER",
            "amount_cents": 1000,
            "target_identifier": "ACC-1",
            "status": "STAGED_PENDING_HITL",
            "staged_at": datetime.now(timezone.utc).isoformat(),
            "biometric_signature": None,
        }
    }
    (tmp_path / "staged_intents.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = StagingLedger(storage_dir=str(tmp_path))
    assert loaded.get_intent("intent-old").target_identifier == "ACC-1"


def test_intent_not_found(ledger):
    with pytest.raises(IntentNotFoundError):
        ledger.get_intent("non-existent-id")
