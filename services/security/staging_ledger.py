"""
Staging ledger for drafted actions. CashPilot works from uploaded statements and has no bank or lender
connection, so a drafted action never executes: the owner either prepares it (gets the request to send
themselves) or dismisses it. There is no code path that moves money.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from services.security.crypto import open_text, seal_text
from services.security.file_utils import ensure_private_dir, restrict_file
from services.security.three_tier_gate import StagedActionIntent

logger = logging.getLogger(__name__)

LEDGER_DIR = os.path.abspath(
    os.environ.get("COPILOT_LEDGER_DIR")
    or os.path.join(os.path.dirname(__file__), "../../.data")
)
# Pending proposals are a queue for a human, not an archive: stale ones are dropped.
STAGED_INTENT_TTL_HOURS = max(1, int(os.environ.get("STAGED_INTENT_TTL_HOURS", "72")))
# Repeating the same instruction (double-click, retry) reuses the pending proposal.
STAGED_INTENT_DEDUPE_SECONDS = max(0, int(os.environ.get("STAGED_INTENT_DEDUPE_SECONDS", "300")))


class ActionStatus(str, Enum):
    STAGED_PENDING_HITL = "STAGED_PENDING_HITL"
    # The owner took the prepared request to send it; CashPilot itself sent nothing.
    PREPARED = "PREPARED"
    REJECTED = "REJECTED"


class StagingLedgerError(Exception):
    """Base exception for staging ledger errors."""


class IntentNotFoundError(StagingLedgerError):
    """Raised when an intent ID does not exist in the ledger."""


class IntentStateError(StagingLedgerError):
    """Raised when an action is performed on an intent in an invalid state."""


class StagingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Optional so the API layer can supply the verified tenant identity from a signed token.
    # When present it must match that identity; the route rejects mismatches.
    tenant_id: Optional[str] = Field(default=None, description="Must match the authenticated tenant")
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, TRANSFER, or PLEDGE_INVOICE")
    amount_cents: int = Field(gt=0, description="Exact integer amount in minor currency units (cents)")
    target_identifier: str = Field(min_length=1, description="Account, invoice ID, or facility ID")


class StagingLedger:
    """Thread-safe persistent staging ledger for autonomous agent financial actions."""

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self._storage_dir = storage_dir
        self._file_path = os.path.join(self._storage_dir, "staged_intents.json") if self._storage_dir else None
        self._intents: dict[str, StagedActionIntent] = {}
        self._lock = threading.Lock()
        self._load_persisted()
        with self._lock:
            if self._purge_expired_locked():
                self._persist()

    def _load_persisted(self) -> None:
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.loads(open_text(f.read()))
                for item in data.values():
                    # Ledgers written before passkeys were removed carry this field.
                    item.pop("biometric_signature", None)
                    intent = StagedActionIntent.model_validate_json(json.dumps(item))
                    self._intents[intent.id] = intent
        except Exception as exc:
            logger.warning("Could not load persisted intents from %s: %s", self._file_path, exc)

    def _persist(self) -> None:
        if not self._file_path:
            return
        ensure_private_dir(self._storage_dir)
        tmp_path = f"{self._file_path}.tmp"
        try:
            data = {k: v.model_dump(mode="json") for k, v in self._intents.items()}
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(seal_text(json.dumps(data, indent=2)))
            os.replace(tmp_path, self._file_path)
            restrict_file(self._file_path)
        except OSError as exc:
            logger.warning("Failed to persist intents to %s: %s", self._file_path, exc)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        """Persisted/constructed timestamps may be naive; compare them as UTC."""
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _purge_expired_locked(self) -> int:
        """Drops pending intents older than the TTL. Caller must hold _lock."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STAGED_INTENT_TTL_HOURS)
        expired = [
            intent_id
            for intent_id, intent in self._intents.items()
            if intent.status == ActionStatus.STAGED_PENDING_HITL.value
            and self._aware(intent.staged_at) < cutoff
        ]
        for intent_id in expired:
            self._intents.pop(intent_id, None)
        return len(expired)

    def _find_recent_duplicate_locked(self, request: StagingRequest, tenant_id: str, now: datetime) -> Optional[StagedActionIntent]:
        """Returns an equivalent pending proposal created inside the dedupe window, if any."""
        if STAGED_INTENT_DEDUPE_SECONDS <= 0:
            return None
        cutoff = now - timedelta(seconds=STAGED_INTENT_DEDUPE_SECONDS)
        for intent in self._intents.values():
            if (
                intent.status == ActionStatus.STAGED_PENDING_HITL.value
                and intent.tenant_id == tenant_id
                and intent.action_type == request.action_type
                and intent.amount_cents == request.amount_cents
                and intent.target_identifier == request.target_identifier
                and self._aware(intent.staged_at) >= cutoff
            ):
                return intent
        return None

    def stage_intent(self, request: StagingRequest) -> StagedActionIntent:
        """Stages an action proposal in Tier 2. No money moves.

        Expired pending proposals are purged, and an identical pending proposal inside the
        dedupe window is returned instead of minting another ID for the same instruction.
        """
        tenant_id = (request.tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("A verified tenant identity is required to stage an action")
        now = datetime.now(timezone.utc)
        with self._lock:
            purged = self._purge_expired_locked()
            duplicate = self._find_recent_duplicate_locked(request, tenant_id, now)
            if duplicate is not None:
                if purged:
                    self._persist()
                return duplicate

            intent = StagedActionIntent(
                id=f"intent-{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                action_type=request.action_type,
                amount_cents=request.amount_cents,
                target_identifier=request.target_identifier,
                status=ActionStatus.STAGED_PENDING_HITL.value,
                staged_at=now,
            )
            self._intents[intent.id] = intent
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

    def _decide(self, intent_id: str, status: ActionStatus) -> StagedActionIntent:
        """Moves a pending intent to the owner's decision; a decided intent stays as it is."""
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")
            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot change intent in status {intent.status}")
            decided = intent.model_copy(update={"status": status.value})
            self._intents[intent_id] = decided
            self._persist()
            return decided

    def prepare_intent(self, intent_id: str) -> StagedActionIntent:
        """Records that the owner took the request to send it themselves. Nothing is sent from here."""
        return self._decide(intent_id, ActionStatus.PREPARED)

    def reject_intent(self, intent_id: str) -> StagedActionIntent:
        """Records that the owner dismissed the drafted action."""
        return self._decide(intent_id, ActionStatus.REJECTED)

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
