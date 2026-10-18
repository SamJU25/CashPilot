"""
In-memory staging ledger for Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
Enforces the Three-Tier Security Gate to prevent unauthorized automated money movements.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from services.security.passkeys import PasskeyError, PasskeyRegistry, passkey_registry
from services.security.three_tier_gate import StagedActionIntent, requires_biometric_execution

logger = logging.getLogger(__name__)

LEDGER_DIR = os.path.abspath(
    os.environ.get("COPILOT_LEDGER_DIR")
    or os.path.join(os.path.dirname(__file__), "../../.data")
)


class ActionStatus(str, Enum):
    STAGED_PENDING_HITL = "STAGED_PENDING_HITL"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class StagingLedgerError(Exception):
    """Base exception for staging ledger errors."""


class IntentNotFoundError(StagingLedgerError):
    """Raised when an intent ID does not exist in the ledger."""


class IntentStateError(StagingLedgerError):
    """Raised when an action is performed on an intent in an invalid state."""


class BiometricVerificationError(StagingLedgerError):
    """Raised when a Tier 3 action lacks a verified WebAuthn passkey assertion."""


class StagingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, TRANSFER, or PLEDGE_INVOICE")
    amount_cents: int = Field(gt=0, description="Exact integer amount in minor currency units (cents)")
    target_identifier: str = Field(min_length=1, description="Account, invoice ID, or facility ID")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    webauthn_assertion: Optional[dict[str, Any]] = Field(
        default=None,
        description="PublicKeyCredential JSON from navigator.credentials.get() over this intent's challenge",
    )


class StagingLedger:
    """Thread-safe persistent staging ledger for autonomous agent financial actions."""

    def __init__(
        self,
        passkeys: Optional[PasskeyRegistry] = None,
        storage_dir: Optional[str] = None,
    ) -> None:
        self._passkeys = passkeys or passkey_registry
        self._storage_dir = storage_dir
        self._file_path = os.path.join(self._storage_dir, "staged_intents.json") if self._storage_dir else None
        self._intents: dict[str, StagedActionIntent] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.values():
                    intent = StagedActionIntent.model_validate_json(json.dumps(item))
                    self._intents[intent.id] = intent
        except Exception as exc:
            logger.warning("Could not load persisted intents from %s: %s", self._file_path, exc)

    def _persist(self) -> None:
        if not self._file_path:
            return
        os.makedirs(self._storage_dir, exist_ok=True)
        tmp_path = f"{self._file_path}.tmp"
        try:
            data = {k: v.model_dump(mode="json") for k, v in self._intents.items()}
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._file_path)
        except OSError as exc:
            logger.warning("Failed to persist intents to %s: %s", self._file_path, exc)

    def stage_intent(self, request: StagingRequest) -> StagedActionIntent:
        """Stages an action proposal in Tier 2. No money moves."""
        intent_id = f"intent-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        intent = StagedActionIntent(
            id=intent_id,
            tenant_id=request.tenant_id,
            action_type=request.action_type,
            amount_cents=request.amount_cents,
            target_identifier=request.target_identifier,
            status=ActionStatus.STAGED_PENDING_HITL.value,
            staged_at=now,
            biometric_signature=None,
        )
        with self._lock:
            self._intents[intent_id] = intent
            self._persist()
        return intent

    def get_intent(self, intent_id: str) -> StagedActionIntent:
        """Retrieves a staged intent by ID."""
        with self._lock:
            intent = self._intents.get(intent_id)
        if intent is None:
            raise IntentNotFoundError(f"Action intent {intent_id} not found")
        return intent

    def list_intents(self, tenant_id: Optional[str] = None) -> list[StagedActionIntent]:
        """Lists staged action intents, optionally filtered by tenant."""
        with self._lock:
            all_intents = list(self._intents.values())
        if tenant_id:
            return [i for i in all_intents if i.tenant_id == tenant_id]
        return all_intents

    def execute_intent(
        self, intent_id: str, webauthn_assertion: Optional[dict[str, Any]] = None
    ) -> StagedActionIntent:
        """
        Executes a staged intent.
        Tier 3 actions require a passkey assertion signed over this intent's challenge.
        """
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot execute intent in status {intent.status}")

            proof = None
            if requires_biometric_execution(intent.action_type):
                if not webauthn_assertion:
                    raise BiometricVerificationError(
                        f"Tier 3 action '{intent.action_type}' requires biometric passkey verification."
                    )
                try:
                    proof = self._passkeys.verify_assertion(intent.tenant_id, intent_id, webauthn_assertion)
                except PasskeyError as exc:
                    raise BiometricVerificationError(
                        f"Tier 3 action '{intent.action_type}' biometric passkey verification failed: {exc}"
                    ) from exc

            executed_intent = intent.model_copy(
                update={
                    "status": ActionStatus.EXECUTED.value,
                    "biometric_signature": proof,
                }
            )
            self._intents[intent_id] = executed_intent
            self._persist()
            return executed_intent

    def reject_intent(self, intent_id: str, reason: str = "Rejected by user") -> StagedActionIntent:
        """Rejects a staged intent."""
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot reject intent in status {intent.status}")

            rejected_intent = intent.model_copy(
                update={"status": ActionStatus.REJECTED.value}
            )
            self._intents[intent_id] = rejected_intent
            self._persist()
            return rejected_intent

    def clear(self) -> None:
        """Clears all intents (used for testing)."""
        with self._lock:
            self._intents.clear()
            if self._file_path and os.path.exists(self._file_path):
                try:
                    os.remove(self._file_path)
                except OSError:
                    pass


# Shared singleton instance
staging_ledger = StagingLedger(storage_dir=LEDGER_DIR)
