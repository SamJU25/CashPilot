"""What CashPilot keeps from a connected alerts mailbox, per tenant, on this machine.

The mailbox password (or a Google/Microsoft refresh token) is encrypted with a key that lives in the
operating system's credential store (Windows Credential Manager, macOS Keychain, Secret Service); only the
ciphertext is in this file. Windows caps a stored credential near 1,280 characters, which a Microsoft
refresh token can exceed, so the store holds the key rather than the secret itself. The file holds extracted alert fields, the
owner's account decisions and the sync cursor, sealed like the rest of .data/.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

import keyring
from cryptography.fernet import Fernet, InvalidToken

from services.mail.banks import Bank
from services.mail.discover import stamps_auth_results
from services.mail.parser import Alert, Parsed
from services.security.crypto import open_text, seal_text

DATA_DIR = Path(".data") / "mail"
KEYRING_SERVICE = "CashPilot mail alerts"
MAX_ALERTS = 1000  # newest kept; older ones are already confirmed by statements or reviewed

AccountStatus = Literal["pending", "use", "ignore"]
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def account_key(a: Alert | dict) -> str:
    d = asdict(a) if isinstance(a, Alert) else a
    return f"{d['bank_domain']}|{d['account_tail']}|{d['currency']}"


def tenant_lock(tenant: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(tenant, threading.Lock())


class MailStore:
    def __init__(self, tenant: str, root: Path | None = None):
        self.tenant = tenant
        # Tenant ids are opaque strings; hash them so none can name a path.
        self.path = (root or DATA_DIR) / f"{hashlib.sha256(tenant.encode()).hexdigest()[:32]}.json"
        # trusted: bank domains the owner trusts in this mailbox although its provider cannot check senders.
        self.data: dict[str, Any] = {"connection": None, "banks": {}, "accounts": {}, "alerts": [], "cursor": {}, "trusted": []}
        if self.path.is_file():
            self.data.update(json.loads(open_text(self.path.read_text(encoding="utf-8"))))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(seal_text(json.dumps(self.data, ensure_ascii=False)), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    # ---- connection and secret

    def _secret_name(self, address: str) -> str:
        return f"{self.tenant}:{address.lower()}"

    def connect(self, address: str, server: dict, secret: str, oauth: Optional[str] = None) -> None:
        """`server` holds host, port, username and the provider's display name; `oauth` names the
        provider when `secret` is a refresh token rather than a password."""
        old = self.data["connection"]
        if old and old["address"].lower() != address.lower():
            self.disconnect()
        self.data["connection"] = {
            "address": address,
            **{k: server[k] for k in ("host", "port", "username", "name")},
            "oauth": oauth,
            "last_sync": None,
            "last_error": None,
        }
        self.set_secret(secret)
        self.data["cursor"] = {}

    def set_secret(self, secret: str) -> None:
        name = self._secret_name(self.data["connection"]["address"])
        key = keyring.get_password(KEYRING_SERVICE, name)
        if not key:
            key = Fernet.generate_key().decode()
            keyring.set_password(KEYRING_SERVICE, name, key)
        self.data["connection"]["secret"] = Fernet(key.encode()).encrypt(secret.encode()).decode()

    def secret(self) -> Optional[str]:
        c = self.data["connection"]
        if not c or not c.get("secret"):
            return None
        key = keyring.get_password(KEYRING_SERVICE, self._secret_name(c["address"]))
        try:
            return Fernet(key.encode()).decrypt(c["secret"].encode()).decode() if key else None
        except InvalidToken:
            return None

    def disconnect(self) -> None:
        """Forgets the mailbox, its password and everything read from it."""
        c = self.data["connection"]
        if c:
            try:
                keyring.delete_password(KEYRING_SERVICE, self._secret_name(c["address"]))
            except keyring.errors.PasswordDeleteError:
                pass
        self.data.update({"connection": None, "accounts": {}, "alerts": [], "cursor": {}, "trusted": []})

    def extra_banks(self) -> dict[str, Bank]:
        return {d: Bank(b["name"], b["currency"]) for d, b in self.data["banks"].items()}

    # ---- alerts

    def add(self, parsed: Parsed) -> bool:
        """Records a parsed alert once; returns False for an email already seen."""
        if parsed.kind == "ignored" or not parsed.alert:
            return False
        a = parsed.alert
        if any(x["id"] == a.id for x in self.data["alerts"]):
            return False
        row = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(a).items()}
        row.update(review=parsed.review, resolved=None)
        self.data["alerts"].append(row)
        self.data["alerts"] = self.data["alerts"][-MAX_ALERTS:]
        if a.account_tail:
            key = account_key(a)
            acc = self.data["accounts"].setdefault(
                key,
                {"key": key, "bank": a.bank, "bank_domain": a.bank_domain, "tail": a.account_tail, "currency": a.currency, "status": "pending", "target": None},
            )
            acc["last_seen"] = a.occurred_on
        return True

    def decide_account(self, key: str, status: AccountStatus, target: Optional[str]) -> None:
        acc = self.data["accounts"][key]
        acc.update(status=status, target=target if status == "use" else None)

    def resolve_alert(self, alert_id: str, action: Literal["accept", "dismiss", "trust"]) -> None:
        row = next(x for x in self.data["alerts"] if x["id"] == alert_id)
        if action == "trust":
            # Only meaningful for an unchecked or unlisted sender; counts as verified from now on.
            if row["bank_domain"] not in self.data["trusted"]:
                self.data["trusted"].append(row["bank_domain"])
            if row["bank_domain"] not in self.data["banks"]:
                self.data["banks"][row["bank_domain"]] = {"name": row["bank"], "currency": row["currency"]}
            return
        row["resolved"] = action

    # ---- the view the app reads

    def view(self) -> dict[str, Any]:
        accounts = self.data["accounts"]
        alerts = sorted(self.data["alerts"], key=lambda x: x["occurred_on"])

        def status(x: dict) -> str:
            if x["resolved"] == "dismiss":
                return "dismissed"
            trusted = (x["review"] in ("unverified_sender", "unlisted_bank")) and x["bank_domain"] in self.data["trusted"]
            if x["review"] and x["resolved"] != "accept" and not trusted:
                return "review"
            acc = accounts.get(account_key(x)) if x["account_tail"] else None
            if not acc:
                return "review"
            return {"pending": "waiting", "ignore": "ignored", "use": "ready"}[acc["status"]]

        rows = [{**x, "status": status(x), "gap": None, "transfer_with": None} for x in alerts]
        _mark_gaps(rows)
        _pair_transfers(rows)
        latest: dict[str, dict] = {}
        for r in rows:
            if r["status"] != "dismissed" and r["account_tail"]:
                latest[account_key(r)] = r
        conn = self.data["connection"]
        return {
            "connection": conn and {**{k: v for k, v in conn.items() if k != "secret"}, "verifies_sender": stamps_auth_results(conn["host"])},
            "banks": self.data["banks"],
            "trusted": self.data["trusted"],
            "accounts": [
                {**acc, "balance": latest.get(k, {}).get("balance_after"), "alerts": sum(1 for r in rows if r["account_tail"] and account_key(r) == k)}
                for k, acc in accounts.items()
            ],
            "alerts": list(reversed(rows)),
        }


def _mark_gaps(rows: list[dict]) -> None:
    """Flags an alert whose balance does not follow from the one before it: an alert went missing."""
    last: dict[str, dict] = {}
    for r in rows:
        if r["status"] not in ("ready", "waiting") or not r["balance_after"]:
            continue
        key = account_key(r)
        prev = last.get(key)
        if prev:
            sign = Decimal(1) if r["direction"] == "IN" else Decimal(-1)
            expected = Decimal(prev["balance_after"]) + sign * Decimal(r["amount"])
            if expected != Decimal(r["balance_after"]):
                r["gap"] = str(Decimal(r["balance_after"]) - expected)
        last[key] = r


def _pair_transfers(rows: list[dict]) -> None:
    """Money out of one of the owner's accounts and the same amount into another on the same day is a
    transfer: both balances move, but it is neither spending nor income."""
    ready = [r for r in rows if r["status"] == "ready" and not r["transfer_with"]]
    for out in (r for r in ready if r["direction"] == "OUT"):
        match = next(
            (
                r
                for r in ready
                if r["direction"] == "IN"
                and not r["transfer_with"]
                and account_key(r) != account_key(out)
                and (r["amount"], r["currency"], r["occurred_on"]) == (out["amount"], out["currency"], out["occurred_on"])
            ),
            None,
        )
        if match:
            out["transfer_with"], match["transfer_with"] = match["id"], out["id"]
