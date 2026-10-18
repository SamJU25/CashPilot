"""
Unit tests for the Three-Tier Security Gate and Staging Ledger.
Verifies proposal staging, state transitions, and HITL WebAuthn passkey verification.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from services.security import (
    StagingLedger,
    StagingRequest,
    ActionStatus,
    BiometricVerificationError,
    IntentNotFoundError,
    IntentStateError,
)
from services.security.passkeys import (
    PasskeyAlreadyRegisteredError,
    PasskeyError,
    PasskeyRegistry,
)
from tests.passkey_authenticator import FLAG_USER_PRESENT, SoftAuthenticator

TENANT = "SME-100"


@pytest.fixture
def passkeys():
    return PasskeyRegistry(rp_id="localhost", rp_name="Test", origins=["http://localhost:3000"])


@pytest.fixture
def authenticator(passkeys):
    device = SoftAuthenticator()
    options = json.loads(passkeys.registration_options(TENANT))
    passkeys.register(TENANT, device.create(options))
    return device


@pytest.fixture
def ledger(passkeys):
    test_ledger = StagingLedger(passkeys=passkeys)
    yield test_ledger
    test_ledger.clear()


def _stage(ledger, action_type="TRANSFER", amount_cents=100000, target="ACC-998877"):
    return ledger.stage_intent(
        StagingRequest(tenant_id=TENANT, action_type=action_type, amount_cents=amount_cents, target_identifier=target)
    )


def _sign(passkeys, device, intent_id):
    return device.get(json.loads(passkeys.authentication_options(TENANT, intent_id)))


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
    assert intent.biometric_signature is None


def test_tier_3_transfer_requires_signed_passkey_assertion(ledger, passkeys, authenticator):
    intent = _stage(ledger)

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=None)

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion={"id": "forged", "response": {}})

    executed = ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))
    assert executed.status == ActionStatus.EXECUTED.value
    assert executed.biometric_signature == bytes_to_base64url(authenticator.credential_id)


def test_draw_credit_line_requires_passkey(ledger, passkeys, authenticator):
    intent = _stage(ledger, action_type="DRAW_CREDIT_LINE", amount_cents=2500000, target="FACILITY-CREDIT-01")

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=None)

    executed = ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))
    assert executed.status == ActionStatus.EXECUTED.value


def test_prefix_tokens_no_longer_accepted(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    for token in ("webauthn_verified_user_fido2", "otp_token_991823", "approved_founder_session"):
        with pytest.raises(BiometricVerificationError):
            ledger.execute_intent(intent.id, webauthn_assertion={"id": token})


def test_assertion_for_one_intent_cannot_execute_another(ledger, passkeys, authenticator):
    first = _stage(ledger)
    second = _stage(ledger, target="ACC-ATTACKER")
    passkeys.authentication_options(TENANT, second.id)

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(second.id, webauthn_assertion=_sign(passkeys, authenticator, first.id))


def test_tampered_signature_rejected(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    assertion = _sign(passkeys, authenticator, intent.id)
    sig = bytearray(base64url_to_bytes(assertion["response"]["signature"]))
    sig[-1] ^= 0x01
    assertion["response"]["signature"] = bytes_to_base64url(bytes(sig))

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=assertion)


def test_challenge_is_single_use(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    assertion = _sign(passkeys, authenticator, intent.id)
    assertion["response"]["signature"] = assertion["response"]["signature"][::-1]

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=assertion)

    # A correctly signed retry over the consumed challenge must still fail.
    challenge = json.loads(base64url_to_bytes(assertion["response"]["clientDataJSON"]))["challenge"]
    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=authenticator.get({"challenge": challenge}))


def test_missing_user_verification_flag_rejected(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    options = json.loads(passkeys.authentication_options(TENANT, intent.id))
    assertion = authenticator.get(options, flags=FLAG_USER_PRESENT)

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=assertion)


def test_wrong_origin_rejected(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    authenticator.origin = "https://evil.example"

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))


def test_registration_from_a_foreign_origin_rejected(passkeys):
    options = json.loads(passkeys.registration_options("SME-201"))

    with pytest.raises(PasskeyError):
        passkeys.register("SME-201", SoftAuthenticator(origin="https://evil.example").create(options))
    assert not passkeys.has_passkey("SME-201")


def test_wrong_rp_id_rejected(ledger, passkeys, authenticator):
    intent = _stage(ledger)
    # A credential minted for another relying party must not unlock this tenant's intent.
    authenticator.rp_id = "evil.example"

    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))


def test_registration_with_mismatched_rp_id_refused(passkeys):
    options = json.loads(passkeys.registration_options("SME-201"))

    with pytest.raises(PasskeyError):
        passkeys.register("SME-201", SoftAuthenticator(rp_id="evil.example").create(options))
    assert not passkeys.has_passkey("SME-201")


def test_second_passkey_registration_refused(passkeys, authenticator):
    with pytest.raises(PasskeyAlreadyRegisteredError):
        passkeys.registration_options(TENANT)


def test_registration_requires_user_verification(passkeys):
    options = json.loads(passkeys.registration_options("SME-200"))
    with pytest.raises(PasskeyError):
        passkeys.register("SME-200", SoftAuthenticator().create(options, flags=FLAG_USER_PRESENT))
    assert not passkeys.has_passkey("SME-200")


def test_cannot_execute_already_executed_intent(ledger, passkeys, authenticator):
    intent = _stage(ledger, action_type="DRAW_CREDIT_LINE", amount_cents=50000, target="FACILITY-01")
    ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))

    with pytest.raises(IntentStateError):
        ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))


def test_reject_staged_intent(ledger, passkeys, authenticator):
    intent = _stage(ledger, action_type="FACTOR_INVOICE", amount_cents=150000, target="INV-002")
    rejected = ledger.reject_intent(intent.id, reason="Owner declined terms")
    assert rejected.status == ActionStatus.REJECTED.value

    with pytest.raises(IntentStateError):
        ledger.execute_intent(intent.id, webauthn_assertion=_sign(passkeys, authenticator, intent.id))


def test_intent_not_found(ledger):
    with pytest.raises(IntentNotFoundError):
        ledger.get_intent("non-existent-id")
