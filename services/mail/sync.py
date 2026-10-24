"""Reads new bank alerts from the owner's alerts mailbox over IMAP, read-only.

The mailbox is opened with EXAMINE and messages are fetched with BODY.PEEK, so CashPilot cannot delete,
move or even mark anything as read. Only mail from trusted bank domains is searched for and downloaded.
"""

from __future__ import annotations

import imaplib
import logging
import socket
import ssl
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes
from email.policy import compat32
from typing import Callable

from services.mail.banks import BANKS
from services.mail.discover import needs_id_command, public_ips, stamps_auth_results
from services.mail import oauth
from services.mail.parser import parse_alert
from services.mail.store import MailStore

FIRST_SYNC_DAYS = 30  # a new connection reads this far back, not the whole mailbox
TIMEOUT_S = 20
IMAPS_PORT = 993

logger = logging.getLogger(__name__)


class MailError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _PinnedIMAP(imaplib.IMAP4_SSL):
    """Connects to an address checked beforehand while still verifying the certificate for the name,
    so DNS cannot be switched to a private address between the check and the connection."""

    def __init__(self, host: str, ip: str, **kw):
        self._ip = ip
        super().__init__(host, IMAPS_PORT, **kw)

    def _create_socket(self, timeout):
        sock = socket.create_connection((self._ip, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


def open_mailbox(host: str, port: int, username: str, secret: str, bearer: bool = False) -> imaplib.IMAP4:
    """Signs in over TLS (certificate checked) on port 993 and opens INBOX read-only.

    Unreachable, refused and bad-certificate all give one error, so this cannot map which hosts and
    ports answer on a network."""
    ips = public_ips(host) if port == IMAPS_PORT else []
    try:
        if not ips:
            raise OSError("not a public IMAPS server")
        box = _PinnedIMAP(host, ips[0], ssl_context=ssl.create_default_context(), timeout=TIMEOUT_S)
        box._encoding = "utf-8"
    except (OSError, ssl.SSLError, socket.timeout) as exc:
        raise MailError("unreachable", f"Could not open a secure connection to {host}.") from exc
    clean_secret = secret.strip()
    if not bearer and ("gmail" in host or "google" in host):
        clean_secret = clean_secret.replace(" ", "")
    try:
        if bearer:
            box.authenticate("XOAUTH2", lambda _: oauth.xoauth2(username, secret))
        else:
            box.login(username, clean_secret)
    except imaplib.IMAP4.error as exc:
        logger.warning("IMAP authentication failed for %s on %s: %s", username, host, exc)
        raise MailError("auth_failed", "The mail server refused the address or password.") from exc
    if needs_id_command(host):
        imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
        box._simple_command("ID", '("name" "CashPilot" "version" "1.0")')
    typ, _ = box.select("INBOX", readonly=True)
    if typ != "OK":
        raise MailError("no_inbox", "The mailbox has no INBOX to read.")
    return box


def _imap_date(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def sync(store: MailStore, opener: Callable[..., imaplib.IMAP4] = open_mailbox) -> dict:
    """Fetches alerts newer than the cursor; returns how many were read and added."""
    conn = store.data["connection"]
    if not conn:
        raise MailError("not_connected", "No alerts mailbox is connected.")
    secret = store.secret()
    if not secret:
        raise MailError("auth_failed", "The saved password is missing from this computer's credential store.")
    stamps = stamps_auth_results(conn["host"])
    if conn.get("oauth"):
        try:
            access, kept = oauth.refresh(conn["oauth"], secret)
        except oauth.OAuthError as exc:
            raise MailError("signin_expired" if exc.code == "revoked" else "unreachable", str(exc)) from exc
        if kept != secret:
            store.set_secret(kept)
        box = opener(conn["host"], conn["port"], conn["username"], access, True)
    else:
        box = opener(conn["host"], conn["port"], conn["username"], secret)
    try:
        validity = (box.response("UIDVALIDITY")[1] or [b""])[0]
        validity = validity.decode() if isinstance(validity, bytes) else str(validity or "")
        cursor = store.data["cursor"]
        # A changed UIDVALIDITY means the server renumbered the mailbox; start again (ids dedupe).
        if cursor.get("uidvalidity") != validity:
            cursor.clear()
        last = int(cursor.get("last_uid", 0))
        since = _imap_date(date.today() - timedelta(days=FIRST_SYNC_DAYS))

        uids: set[int] = set()
        # 1. Search known bank domains
        for domain in [*BANKS, *store.data["banks"]]:
            query = ["UID", f"{last + 1}:*", "FROM", f'"{domain}"'] if last else ["SINCE", since, "FROM", f'"{domain}"']
            try:
                typ, data = box.uid("SEARCH", *query)
                if typ == "OK" and data and data[0]:
                    uids.update(int(u) for u in data[0].split())
            except (imaplib.IMAP4.error, UnicodeError):
                continue
        # 2. Also search candidate alert subjects for unlisted/regional banks
        for kw in ["alert", "notification", "transaction", "动账", "支出", "转入"]:
            is_ascii = all(ord(c) < 128 for c in kw)
            if is_ascii:
                query = ["UID", f"{last + 1}:*", "SUBJECT", f'"{kw}"'] if last else ["SINCE", since, "SUBJECT", f'"{kw}"']
            else:
                query = ["CHARSET", "UTF-8", "UID", f"{last + 1}:*", "SUBJECT", f'"{kw}"'] if last else ["CHARSET", "UTF-8", "SINCE", since, "SUBJECT", f'"{kw}"']
            try:
                typ, data = box.uid("SEARCH", *query)
                if typ == "OK" and data and data[0]:
                    uids.update(int(u) for u in data[0].split())
            except (imaplib.IMAP4.error, UnicodeError):
                continue
        # "N:*" always returns the last message even when it is older than N.
        uids = {u for u in uids if u > last}

        added = 0
        extra = store.extra_banks()
        for uid in sorted(uids):
            typ, data = box.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None)
            if typ != "OK" or raw is None:
                continue
            msg = message_from_bytes(raw, policy=compat32)
            added += store.add(parse_alert(msg, raw, stamps, extra, store.data.get("trusted", [])))
            last = max(last, uid)
        cursor.update(uidvalidity=validity, last_uid=last)
        conn.update(last_sync=datetime.now(timezone.utc).isoformat(timespec="seconds"), last_error=None)
        return {"read": len(uids), "added": added}
    finally:
        try:
            box.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
