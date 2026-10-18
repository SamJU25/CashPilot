"""In-memory and persistent session store for Autonomous SME Finance Copilot.

Provides:
1. Thread-safe multi-tenant session lifecycle management.
2. In-memory session cache with file-backed persistence.
3. Cached transactional statement dossiers (eliminates redundant CSV re-parsing).
4. Episodic financial fact extraction (preserves loan terms, EBITDA, fixed costs beyond 6 turns).
5. Full multi-turn conversation history retention.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.agent.schema import ChatHistoryItem

logger = logging.getLogger(__name__)

# Overridable so the test suite never touches (or wipes) real sessions.
SESSION_CACHE_DIR = os.path.abspath(
    os.environ.get("COPILOT_SESSION_DIR") or os.path.join(os.path.dirname(__file__), "../../.sessions")
)
# Sessions hold raw bank statements; untouched ones are dropped instead of kept forever.
SESSION_TTL_DAYS = 30
# Facts derived from the loaded statement; stale the moment a different statement arrives.
STATEMENT_FACTS = (
    "current_balance",
    "average_daily_burn",
    "runway_days",
    "cash_status",
    "daily_average_balance",
    "risk_tier",
    "max_qualified_limit",
)


class SessionRecord(BaseModel):
    """Encapsulates active session state, transactional dossier, and episodic memory."""

    session_id: str
    tenant_id: str = "SME-DEFAULT"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: List[ChatHistoryItem] = Field(default_factory=list)
    csv_content: Optional[str] = None
    invoices_csv: Optional[str] = None
    cached_dossier: Optional[Dict[str, Any]] = None
    cached_ageing: Optional[Dict[str, Any]] = None
    financial_facts: Dict[str, Any] = Field(default_factory=dict)
    rolling_summary: Optional[str] = None


class SessionStore:
    """Thread-safe singleton store managing agent sessions and financial context memory."""

    _instance: Optional[SessionStore] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._store_lock = threading.Lock()
        os.makedirs(SESSION_CACHE_DIR, exist_ok=True)
        self._load_persisted_sessions()

    @classmethod
    def get_instance(cls) -> SessionStore:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SessionStore()
            return cls._instance

    def _get_session_path(self, session_id: str) -> str:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(SESSION_CACHE_DIR, f"{safe_id}.json")

    def _load_persisted_sessions(self) -> None:
        """Loads serialized sessions from disk on startup, deleting ones idle past SESSION_TTL_DAYS."""
        if not os.path.exists(SESSION_CACHE_DIR):
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=SESSION_TTL_DAYS)
        for fname in os.listdir(SESSION_CACHE_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(SESSION_CACHE_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        rec = SessionRecord(**json.load(f))
                    if datetime.fromisoformat(rec.updated_at) < cutoff:
                        os.remove(fpath)
                        continue
                    self._sessions[rec.session_id] = rec
                except (OSError, ValueError) as exc:
                    logger.warning("Skipping unreadable session file %s: %s", fname, exc)

    def _persist_session(self, record: SessionRecord) -> None:
        """Saves session state to disk for cross-restart recovery."""
        fpath = self._get_session_path(record.session_id)
        tmp_path = f"{fpath}.tmp"
        try:
            # Write-then-rename: a crash mid-write used to leave a truncated file the loader dropped.
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(record.model_dump_json(indent=2))
            os.replace(tmp_path, fpath)
        except OSError as exc:
            logger.warning("Session disk write error for %s: %s", record.session_id, exc)

    def get_or_create(self, session_id: str, tenant_id: str = "SME-DEFAULT") -> SessionRecord:
        """
        Retrieves an existing session record or initializes a new one. A session belongs to the tenant
        that created it: presenting its id under another tenant opens a fresh session with a new id
        (callers must use the returned record's session_id) instead of exposing the statement.
        """
        with self._store_lock:
            rec = self._sessions.get(session_id)
            if rec is not None and rec.tenant_id == tenant_id:
                return rec
            if rec is not None:
                logger.warning("Session %s requested by a different tenant; issuing a new session", session_id)
                session_id = f"sess_{uuid.uuid4().hex[:12]}"

            rec = SessionRecord(session_id=session_id, tenant_id=tenant_id)
            self._sessions[session_id] = rec
            self._persist_session(rec)
            return rec

    def get(self, session_id: str) -> Optional[SessionRecord]:
        with self._store_lock:
            return self._sessions.get(session_id)

    def get_for_tenant(self, session_id: str, tenant_id: str) -> Optional[SessionRecord]:
        """The session only if it belongs to this tenant; API reads and deletes go through here."""
        rec = self.get(session_id)
        return rec if rec is not None and rec.tenant_id == tenant_id else None

    def update_statement(
        self,
        session_id: str,
        csv_content: str,
        dossier: Optional[Dict[str, Any]] = None,
        tenant_id: str = "SME-DEFAULT",
    ) -> SessionRecord:
        """Stores statement CSV and cached calculation metrics in the session."""
        rec = self.get_or_create(session_id, tenant_id=tenant_id)
        with self._store_lock:
            if rec.csv_content is not None and rec.csv_content != csv_content:
                rec.cached_dossier = None
                for fact in STATEMENT_FACTS:
                    rec.financial_facts.pop(fact, None)
            rec.csv_content = csv_content
            if dossier is not None:
                rec.cached_dossier = dossier
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def clear_statement(self, session_id: str) -> Optional[SessionRecord]:
        """Clears statement CSV, cached dossier, and statement-derived facts from the session."""
        with self._store_lock:
            rec = self._sessions.get(session_id)
            if not rec:
                return None
            rec.csv_content = None
            rec.cached_dossier = None
            for fact in STATEMENT_FACTS:
                rec.financial_facts.pop(fact, None)
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def update_invoices(
        self,
        session_id: str,
        invoices_csv: str,
        tenant_id: str = "SME-DEFAULT",
        ageing: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        """Stores the uploaded invoices CSV and optional cached ageing analysis for the session."""
        rec = self.get_or_create(session_id, tenant_id=tenant_id)
        with self._store_lock:
            rec.invoices_csv = invoices_csv
            if ageing is not None:
                rec.cached_ageing = ageing
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def clear_invoices(self, session_id: str) -> Optional[SessionRecord]:
        """Clears invoices CSV and cached ageing from the session."""
        with self._store_lock:
            rec = self._sessions.get(session_id)
            if not rec:
                return None
            rec.invoices_csv = None
            rec.cached_ageing = None
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def append_turn(
        self,
        session_id: str,
        user_text: str,
        agent_text: str,
        tenant_id: str = "SME-DEFAULT",
    ) -> SessionRecord:
        """Appends user and agent turns to session history and updates episodic facts."""
        rec = self.get_or_create(session_id, tenant_id=tenant_id)
        with self._store_lock:
            if user_text:
                rec.messages.append(ChatHistoryItem(role="user", text=user_text))
            if agent_text:
                rec.messages.append(ChatHistoryItem(role="agent", text=agent_text))

            # Maintain reasonable maximum capacity (last 50 turns) to prevent memory leak
            if len(rec.messages) > 50:
                rec.messages = rec.messages[-50:]

            # If messages exceed active sliding window (6 turns), maintain rolling summary of older turns
            if len(rec.messages) > 6:
                try:
                    from services.agent.context_summarizer import generate_deterministic_summary
                    rec.rolling_summary = generate_deterministic_summary(rec.messages[:-6])
                except Exception as exc:
                    logger.debug("Could not generate rolling summary for session %s: %s", session_id, exc)

            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)
            return rec

    def set_financial_fact(self, session_id: str, key: str, value: Any) -> None:
        """Stores an episodic business fact (e.g. loan_amount, target_horizon)."""
        # The caller already resolved the session; get_or_create here would read a missing tenant
        # as a different one and fork a new session on every fact.
        rec = self.get(session_id) or self.get_or_create(session_id)
        with self._store_lock:
            rec.financial_facts[key] = value
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_session(rec)

    def get_financial_facts(self, session_id: str) -> Dict[str, Any]:
        rec = self.get(session_id)
        if rec is None:
            return {}
        with self._store_lock:
            return dict(rec.financial_facts)

    def clear(self, session_id: str) -> bool:
        """Clears session data from memory and removes file from disk."""
        with self._store_lock:
            removed = self._sessions.pop(session_id, None)
            fpath = self._get_session_path(session_id)
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
            return removed is not None

    def clear_all(self) -> None:
        """Wipes all sessions (primarily for unit test isolation)."""
        with self._store_lock:
            self._sessions.clear()
            if os.path.exists(SESSION_CACHE_DIR):
                for fname in os.listdir(SESSION_CACHE_DIR):
                    if fname.endswith(".json"):
                        try:
                            os.remove(os.path.join(SESSION_CACHE_DIR, fname))
                        except OSError:
                            pass


# Global singleton instance
session_store = SessionStore.get_instance()
