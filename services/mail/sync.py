"""Reads new bank alerts from the owner's alerts mailbox over IMAP, read-only.

The mailbox is opened with EXAMINE and messages are fetched with BODY.PEEK, so CashPilot cannot delete,
move or even mark anything as read. Only mail from trusted bank domains is searched for and downloaded.
"""

from __future__ import annotations

import imaplib
import logging
import re
import socket
import ssl
import threading
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes
from email.policy import compat32
from email.utils import parseaddr
from typing import TYPE_CHECKING, Callable, Optional

from services.mail.banks import BANKS
from services.mail.discover import needs_id_command, public_ips, stamps_auth_results
from services.mail import oauth
from services.mail.parser import parse_alert
from services.mail.store import MailStore

if TYPE_CHECKING:
    from services.agent.schema import LLMConfig

FIRST_SYNC_DAYS = 30  # a new connection reads this far back, not the whole mailbox
TIMEOUT_S = 20
IMAPS_PORT = 993

SUBJECT_KEYWORDS = [
    "alert", "notification", "transaction", "payment", "transfer", "deposit",
    "receipt", "payout", "debited", "credited", "purchase", "spent", "received",
    "sent", "动账", "支出", "转入", "汇款", "退款", "入账", "扣款",
]

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


def _candidate_folders(box: imaplib.IMAP4) -> list[str]:
    """Discovers subfolders relevant to banking/alerts/finance while skipping trash, spam and drafts."""
    folders: list[str] = []
    if not hasattr(box, "list"):
        return folders
    try:
        typ, raw_folders = box.list()
        if typ == "OK" and raw_folders:
            for item in raw_folders:
                if not isinstance(item, (bytes, str)):
                    continue
                s = item.decode(errors="ignore") if isinstance(item, bytes) else item
                m = re.search(r'\((?P<flags>[^)]*)\)\s+"?[^"]*"?\s+"?(?P<name>[^"]+)"?$', s.strip())
                if not m:
                    continue
                flags = m.group("flags").lower()
                name = m.group("name").strip().strip('"')
                name_lower = name.lower()
                if any(bad in flags for bad in ("trash", "junk", "spam", "drafts", "sent")):
                    continue
                if any(bad in name_lower for bad in ("trash", "junk", "spam", "draft", "sent", "deleted", "bin")):
                    continue
                if any(kw in name_lower for kw in ("bank", "alert", "finance", "notification", "transaction", "账单", "银行", "财务", "通知", "提醒", "动账")):
                    if name not in folders and name.upper() != "INBOX":
                        folders.append(name)
    except Exception:
        pass
    return folders


def _scan_folder(
    box: imaplib.IMAP4,
    last: int,
    since: str,
    stamps: bool,
    extra: dict,
    store: MailStore,
    abort_event: Optional[threading.Event] = None,
    llm_config: Optional[LLMConfig] = None,
) -> tuple[int, int, int]:
    uids: set[int] = set()
    new_last = last
    fast_search_done = False

    # 1. Fast path: 1 single bulk UID query instead of 100+ sequential round-trips
    if last > 0:
        try:
            typ, data = box.uid("SEARCH", "UID", f"{last + 1}:*")
            if typ == "OK" and data and data[0]:
                uids = {int(u) for u in data[0].split() if int(u) > last}
            fast_search_done = True
        except (imaplib.IMAP4.error, UnicodeError, AssertionError, OSError):
            fast_search_done = False
    elif last == 0:
        try:
            typ, data = box.uid("SEARCH", "SINCE", since)
            if typ == "OK" and data and data[0]:
                all_uids = [int(u) for u in data[0].split()]
                if all_uids:
                    uids = set(all_uids[-500:])  # Cap initial sync scan to recent 500
                    new_last = max(all_uids)
            fast_search_done = True
        except (imaplib.IMAP4.error, UnicodeError, AssertionError, OSError):
            fast_search_done = False

    # 2. Fallback path if bulk query failed or not supported
    if not fast_search_done:
        for domain in [*BANKS, *store.data.get("banks", {})]:
            if abort_event and abort_event.is_set():
                return len(uids), 0, last
            query = ["UID", f"{last + 1}:*", "FROM", f'"{domain}"'] if last else ["SINCE", since, "FROM", f'"{domain}"']
            try:
                typ, data = box.uid("SEARCH", *query)
                if typ == "OK" and data and data[0]:
                    uids.update(int(u) for u in data[0].split())
            except (imaplib.IMAP4.error, UnicodeError, AssertionError, OSError):
                continue
        for kw in SUBJECT_KEYWORDS:
            if abort_event and abort_event.is_set():
                return len(uids), 0, last
            is_ascii = all(ord(c) < 128 for c in kw)
            if is_ascii:
                query = ["UID", f"{last + 1}:*", "SUBJECT", f'"{kw}"'] if last else ["SINCE", since, "SUBJECT", f'"{kw}"']
            else:
                query = ["CHARSET", "UTF-8", "UID", f"{last + 1}:*", "SUBJECT", f'"{kw}"'] if last else ["CHARSET", "UTF-8", "SINCE", since, "SUBJECT", f'"{kw}"']
            try:
                typ, data = box.uid("SEARCH", *query)
                if typ == "OK" and data and data[0]:
                    uids.update(int(u) for u in data[0].split())
            except (imaplib.IMAP4.error, UnicodeError, AssertionError, OSError):
                continue

    uids = {u for u in uids if u > last}
    if not uids:
        return 0, 0, new_last

    new_last = max(new_last, max(uids))

    # 3. Header pre-filtering if more than 3 candidate messages
    candidate_uids = uids
    if len(uids) > 3 and fast_search_done:
        try:
            uid_seq = f"{min(uids)}:{max(uids)}"
            typ, hdr_data = box.uid("FETCH", uid_seq, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            if typ == "OK" and hdr_data:
                domains = set([*BANKS, *store.data.get("banks", {})])
                filtered_uids = set()
                for item in hdr_data:
                    if isinstance(item, tuple) and item[1]:
                        header_str = item[0].decode("ascii", errors="ignore")
                        m_uid = re.search(r"\bUID\s+(\d+)", header_str)
                        u = int(m_uid.group(1)) if m_uid else None
                        msg = message_from_bytes(item[1], policy=compat32)
                        f_addr = parseaddr(msg.get("From", ""))[1].lower()
                        dom = f_addr.rpartition("@")[2]
                        subj = (msg.get("Subject", "") or "").lower()
                        if any(dom == d or dom.endswith("." + d) for d in domains) or any(kw in subj for kw in SUBJECT_KEYWORDS):
                            if u:
                                filtered_uids.add(u)
                candidate_uids = filtered_uids
        except Exception as exc:
            logger.debug("Header pre-filtering skipped: %s", exc)
            candidate_uids = uids

    added = 0
    for uid in sorted(candidate_uids):
        if abort_event and abort_event.is_set():
            break
        try:
            typ, data = box.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None)
            if typ != "OK" or raw is None:
                continue
            msg = message_from_bytes(raw, policy=compat32)
            added += store.add(parse_alert(msg, raw, stamps, extra, store.data.get("trusted", []), llm_config=llm_config))
        except (imaplib.IMAP4.error, OSError):
            continue

    return len(uids), added, new_last


def sync(
    store: MailStore,
    opener: Optional[Callable[..., imaplib.IMAP4]] = None,
    abort_event: Optional[threading.Event] = None,
    llm_config: Optional[LLMConfig] = None,
) -> dict:
    """Fetches alerts newer than the cursor across all connected mailboxes."""
    if opener is None:
        opener = open_mailbox
    conns: list[dict] = store.data.get("connections") or ([store.data["connection"]] if store.data.get("connection") else [])
    if not conns:
        raise MailError("not_connected", "No alerts mailbox is connected.")

    total_read = 0
    total_added = 0
    since = _imap_date(date.today() - timedelta(days=FIRST_SYNC_DAYS))
    extra = store.extra_banks()
    last_exc: Optional[MailError] = None
    successful_conns = 0

    for conn in conns:
        if abort_event and abort_event.is_set():
            break
        addr = conn.get("address", "")
        secret = store.secret(addr)
        if not secret:
            continue
        stamps = stamps_auth_results(conn["host"])
        try:
            if conn.get("oauth"):
                try:
                    access, kept = oauth.refresh(conn["oauth"], secret)
                except oauth.OAuthError as exc:
                    conn["last_error"] = str(exc)
                    continue
                if kept != secret:
                    store.set_secret(kept, addr)
                box = opener(conn["host"], conn["port"], conn["username"], access, True)
            else:
                box = opener(conn["host"], conn["port"], conn["username"], secret)
        except MailError as exc:
            conn["last_error"] = exc.code
            last_exc = exc
            continue

        try:
            validity = (box.response("UIDVALIDITY")[1] or [b""])[0]
            validity = validity.decode() if isinstance(validity, bytes) else str(validity or "")
            cursor = store.data["cursor"]
            prefix = f"{addr.lower()}_" if len(conns) > 1 else ""

            # Check if UIDVALIDITY changed
            cur_validity = cursor.get(f"{prefix}uidvalidity") or cursor.get("uidvalidity")
            if cur_validity is not None and cur_validity != validity:
                cursor.pop(f"{prefix}last_uid", None)
                if not prefix:
                    cursor.pop("last_uid", None)

            last = int(cursor.get(f"{prefix}last_uid", cursor.get("last_uid", 0)))
            r, a, new_last = _scan_folder(box, last, since, stamps, extra, store, abort_event, llm_config=llm_config)
            total_read += r
            total_added += a

            if not (abort_event and abort_event.is_set()):
                for folder in _candidate_folders(box):
                    if abort_event and abort_event.is_set():
                        break
                    try:
                        typ, _ = box.select(folder, readonly=True)
                        if typ == "OK":
                            sub_last = int(cursor.get(f"{prefix}last_uid_{folder}", 0))
                            fr, fa, fn_last = _scan_folder(box, sub_last, since, stamps, extra, store, abort_event, llm_config=llm_config)
                            total_read += fr
                            total_added += fa
                            cursor[f"{prefix}last_uid_{folder}"] = fn_last
                    except Exception:
                        continue

            if not (abort_event and abort_event.is_set()):
                cursor[f"{prefix}uidvalidity"] = validity
                cursor[f"{prefix}last_uid"] = new_last
                if not prefix:
                    cursor["uidvalidity"] = validity
                    cursor["last_uid"] = new_last
                conn.update(last_sync=datetime.now(timezone.utc).isoformat(timespec="seconds"), last_error=None)
                successful_conns += 1
        except (socket.timeout, ssl.SSLError, TimeoutError, OSError, imaplib.IMAP4.error) as exc:
            err_code = "unreachable"
            logger.warning("Mailbox scan interrupted for %s on %s: %s", addr, conn.get("host"), exc)
            conn["last_error"] = err_code
            last_exc = MailError(err_code, f"Connection to {conn.get('host')} interrupted: {exc}")
            continue
        finally:
            try:
                box.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    if len(conns) == 1 and last_exc and successful_conns == 0:
        raise last_exc
    if len(conns) > 1 and successful_conns == 0 and last_exc:
        raise last_exc

    return {"read": total_read, "added": total_added}
