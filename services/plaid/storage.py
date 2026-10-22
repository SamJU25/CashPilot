"""Encrypted-at-rest storage for Plaid items and access tokens.
Aligns with services/security/crypto.py and the Three-Tier Security Gate.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.security.crypto import open_text, seal_text

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(".data")
PLAID_STORAGE_FILE = DEFAULT_DATA_DIR / "plaid_connections.json"


class PlaidStorage:
    """Thread-safe persistent store for connected Plaid institutions and accounts.
    Tokens are sealed with Fernet before writing to disk.
    """

    def __init__(self, file_path: Path | str | None = None):
        self.file_path = Path(file_path or PLAID_STORAGE_FILE)
        self._lock = threading.Lock()
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _ensure_dir(self) -> None:
        parent = self.file_path.parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass

    def _load(self) -> None:
        with self._lock:
            if not self.file_path.is_file():
                self._data = {}
                return
            try:
                raw = self.file_path.read_text(encoding="utf-8")
                decrypted = open_text(raw)
                self._data = json.loads(decrypted)
            except Exception as exc:
                logger.warning("Could not read Plaid connections file (%s); starting empty", exc)
                self._data = {}

    def _save(self) -> None:
        self._ensure_dir()
        raw_json = json.dumps(self._data, indent=2)
        sealed = seal_text(raw_json)
        tmp = self.file_path.with_suffix(".tmp")
        tmp.write_text(sealed, encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.file_path)

    def save_item(
        self,
        tenant_id: str,
        item_id: str,
        access_token: str,
        institution_name: str,
        institution_id: str | None = None,
        accounts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Saves a connected bank item for the tenant."""
        with self._lock:
            items = self._data.setdefault(tenant_id, [])
            # Deduplicate by item_id
            items = [it for it in items if it.get("item_id") != item_id]

            now_iso = datetime.now(timezone.utc).isoformat()
            record = {
                "item_id": item_id,
                "access_token": access_token,
                "institution_name": institution_name,
                "institution_id": institution_id or "ins_generic",
                "accounts": accounts or [],
                "connected_at": now_iso,
                "last_synced_at": now_iso,
                "cursor": None,
                "status": "ACTIVE",
            }
            items.append(record)
            self._data[tenant_id] = items
            self._save()
            return record

    def get_items(self, tenant_id: str) -> list[dict[str, Any]]:
        """Returns all connected bank items for the tenant."""
        with self._lock:
            items = self._data.get(tenant_id, [])
            # Return copy to prevent mutation
            return [dict(it) for it in items if it.get("status") == "ACTIVE"]

    def get_item(self, tenant_id: str, item_id: str) -> dict[str, Any] | None:
        """Returns a specific connected bank item."""
        with self._lock:
            for it in self._data.get(tenant_id, []):
                if it.get("item_id") == item_id:
                    return dict(it)
        return None

    def update_item_sync(
        self,
        tenant_id: str,
        item_id: str,
        cursor: str | None = None,
        accounts: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Updates the sync cursor and account balance cache."""
        with self._lock:
            items = self._data.get(tenant_id, [])
            for it in items:
                if it.get("item_id") == item_id:
                    if cursor:
                        it["cursor"] = cursor
                    if accounts is not None:
                        it["accounts"] = accounts
                    it["last_synced_at"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                    return True
        return False

    def remove_item(self, tenant_id: str, item_id: str) -> bool:
        """Disconnects an institution for the tenant."""
        with self._lock:
            items = self._data.get(tenant_id, [])
            initial_len = len(items)
            items = [it for it in items if it.get("item_id") != item_id]
            if len(items) != initial_len:
                self._data[tenant_id] = items
                self._save()
                return True
        return False

    def clear(self) -> None:
        """Clears all stored items (for test suites)."""
        with self._lock:
            self._data = {}
            if self.file_path.exists():
                try:
                    self.file_path.unlink()
                except OSError:
                    pass


plaid_storage = PlaidStorage()
