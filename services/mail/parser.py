"""Turns one bank alert email into a transaction, deterministically.

Email is untrusted input: only the fields extracted here leave this module. The raw text never reaches
the agent's prompt, so an alert cannot carry instructions into the copilot.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Literal, Optional

from services.mail.banks import Bank, bank_for, infer_bank_info


@dataclass(frozen=True)
class Alert:
    id: str
    bank: str
    bank_domain: str
    account_tail: str
    currency: str
    direction: Literal["IN", "OUT"]
    amount: Decimal
    balance_after: Optional[Decimal]
    occurred_on: str  # ISO date
    counterparty: Optional[str]
    verified: bool


@dataclass(frozen=True)
class Parsed:
    """`alert` is set for a transaction; `review` says why it needs the owner's eye before it counts."""

    kind: Literal["transaction", "review", "ignored"]
    alert: Optional[Alert] = None
    review: Optional[str] = None
    reason: Optional[str] = None


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li", "td"):
            self.parts.append("\n" if tag != "td" else " ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def body_text(msg: Message) -> str:
    """Plain text of the message, preferring the text part and flattening HTML otherwise."""
    plain, html = [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html") or part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plain if ctype == "text/plain" else html).append(text)
    if plain:
        return "\n".join(plain)
    p = _Text()
    p.feed("\n".join(html))
    return "".join(p.parts)


def sender_domain(msg: Message) -> str:
    return parseaddr(msg.get("From", ""))[1].rpartition("@")[2].lower()


def verify_sender(msg: Message, domain: str, provider_stamps: bool) -> bool:
    """True when the receiving provider's own check says the bank really sent this.

    Providers add their Authentication-Results header on top, so only the topmost one is theirs; any
    lower one could have been written by the sender. Without a provider stamp nothing is trusted.
    """
    if not provider_stamps:
        return False
    results = msg.get_all("Authentication-Results") or []
    if not results:
        return False
    top = re.sub(r"\s+", " ", str(results[0])).lower()

    def passes(method: str, field: str) -> bool:
        m = re.search(rf"\b{method}=pass\b[^;]*?\b{field}=@?([a-z0-9.-]+)", top)
        return bool(m) and (m.group(1) == domain or m.group(1).endswith("." + domain) or domain.endswith("." + m.group(1)))

    return passes("dkim", r"header\.d") or passes("dmarc", r"header\.from")


# Login codes and one-time passwords are dropped, never stored.
_CODE = re.compile(r"验证码|校验码|动态密码|verification code|one[- ]time (?:pass(?:word|code)|code)|\bOTP\b|security code", re.I)
_TAIL = re.compile(
    r"(?:尾号|末四位|卡号后四位|账号后四位|ending(?:\s+(?:in|with))?|account\s*(?:no\.?|number)?\s*[x*•·]+|card\s*[x*•·]+|[x*•·]{2,})\s*[:：]?\s*(\d{4})(?!\d)",
    re.I,
)
_OUT = re.compile(r"支出|消费|转出|扣款|取现|付款|debited|\bspent\b|withdrawn|withdrawal|\bpurchase\b|\bpaid\b|payment (?:of|to)|\bsent\b", re.I)
_IN = re.compile(r"收入|存入|转入|入账|汇入|credited|\bdeposit(?:ed)?\b|\breceived\b|incoming", re.I)
_BALANCE = re.compile(r"余额|可用余额|balance|avl\.? bal|avail(?:able)? bal", re.I)
from services.calculations.currency_registry import CurrencyRegistry, SYMBOL_MAP

_SYMS = sorted(list(SYMBOL_MAP.keys()) + ["¥", "￥", "Rs", "Rs.", "₹"], key=len, reverse=True)
_SYM_PATTERN = "|".join(re.escape(s) for s in _SYMS)
_CODES_PATTERN = r"\b[A-Za-z]{3}\b|RMB|元"

_MONEY = re.compile(
    rf"(?:(?P<code>{_CODES_PATTERN})\s*|(?P<sym>{_SYM_PATTERN})\s*)(?P<n>-?\d[\d,]*(?:\.\d{{1,2}})?)"
    rf"|(?P<n2>-?\d[\d,]*(?:\.\d{{1,2}})?)\s*(?:(?P<code2>{_CODES_PATTERN})|(?P<sym2>{_SYM_PATTERN}))",
    re.I,
)
_DATE_NUM = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
_DATE_CN_SHORT = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日")
# The other party: a label then a name, stopping at punctuation or a sentence end ("CAFE. Avl bal").
_PARTY = re.compile(r"(?:对方户名|对方账户名|商户名称|商户|付款人|收款人|\bfrom\b|\bat\b)\s*[:：]?\s*([^\n,，。;；:：]{2,40}?)(?=\.\s|\.$|[\n,，。;；:：]|\s+(?:on|was|has|is|into|to your)\s|$)", re.I)


def _money(text: str, default_currency: str) -> list[tuple[int, str, Decimal]]:
    out = []
    for m in _MONEY.finditer(text):
        raw = (m.group("n") or m.group("n2")).replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        code = (m.group("code") or m.group("code2") or "").strip()
        sym = (m.group("sym") or m.group("sym2") or "").strip()

        if code:
            if code.upper() in ("RMB", "元"):
                currency = "CNY"
            else:
                resolved = CurrencyRegistry.resolve_currency(code, default="")
                if not resolved:
                    continue  # Skip non-currency words before numbers
                currency = resolved
        elif sym:
            if sym in ("¥", "￥"):
                currency = "JPY" if default_currency.upper() == "JPY" else "CNY"
            elif sym == "$":
                currency = default_currency if default_currency.upper() in ("CAD", "AUD", "SGD", "HKD", "NZD", "USD") else "USD"
            else:
                currency = CurrencyRegistry.resolve_currency(sym, default_currency)
        else:
            currency = default_currency

        out.append((m.start(), currency, value))
    return out


def _occurred(text: str, msg: Message) -> str:
    sent: Optional[datetime] = None
    try:
        sent = parsedate_to_datetime(msg.get("Date", ""))
    except (TypeError, ValueError):
        pass
    if m := _DATE_NUM.search(text):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    if (m := _DATE_CN_SHORT.search(text)) and sent:
        try:
            return date(sent.year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            pass
    return (sent or datetime.now()).date().isoformat()


def message_id(msg: Message, raw: bytes) -> str:
    """Stable id: the Message-ID when present, else a hash of the bytes; the same email never counts twice."""
    basis = (msg.get("Message-ID") or "").strip().encode() or raw
    return hashlib.sha256(basis).hexdigest()[:24]


def parse_alert(
    msg: Message,
    raw: bytes,
    provider_stamps: bool,
    extra_banks: Optional[dict[str, Bank]] = None,
    trusted: Optional[list[str]] = None,
    default_currency: str = "USD",
) -> Parsed:
    domain = sender_domain(msg)
    found = bank_for(domain, extra_banks)
    is_unlisted = False
    if found:
        bank_domain, bank = found
    else:
        is_unlisted = True
        bank_domain = domain
        bank = infer_bank_info(domain, default_currency)

    text = f"{msg.get('Subject', '')}\n{body_text(msg)}"
    if _CODE.search(text):
        return Parsed("ignored", reason="login_code")

    money = _money(text, bank.currency)
    balance = next((m for m in money if _BALANCE.search(text[max(0, m[0] - 24) : m[0]])), None)
    amounts = [m for m in money if m is not balance and m[2] > 0]
    if not amounts:
        return Parsed("ignored", reason="no_amount")
    pos, currency, amount = amounts[0]

    # The direction word nearest before the amount wins: "转出…余额" style alerts name both.
    before = text[:pos]
    out_at = max((m.end() for m in _OUT.finditer(before)), default=-1)
    in_at = max((m.end() for m in _IN.finditer(before)), default=-1)
    if out_at < 0 and in_at < 0:
        out_at = 0 if _OUT.search(text) else -1
        in_at = 0 if _IN.search(text) else -1
    direction: Optional[Literal["IN", "OUT"]] = "OUT" if out_at > in_at else "IN" if in_at > out_at else None

    tail = _TAIL.search(text)
    # If unlisted and lacks account tail or direction, ignore as non-bank email
    if is_unlisted and (not tail or direction is None):
        return Parsed("ignored", reason="sender_not_trusted")

    party = next((m for m in [*_PARTY.finditer(text[pos:]), *_PARTY.finditer(text)] if re.search(r"[^\W\d_]", m.group(1))), None)
    verified = (bank_domain in (trusted or [])) or verify_sender(msg, bank_domain, provider_stamps)
    alert = Alert(
        id=message_id(msg, raw),
        bank=bank.name,
        bank_domain=bank_domain,
        account_tail=tail.group(1) if tail else "",
        currency=currency,
        direction=direction or "IN",
        amount=amount,
        balance_after=balance[2] if balance else None,
        occurred_on=_occurred(text, msg),
        counterparty=party.group(1).strip()[:40] if party else None,
        verified=verified,
    )
    if is_unlisted and bank_domain not in (trusted or []):
        return Parsed("review", alert, review="unlisted_bank")
    if not tail:
        return Parsed("review", alert, review="no_account")
    if direction is None:
        return Parsed("review", alert, review="no_direction")
    if not verified:
        return Parsed("review", alert, review="unverified_sender")
    return Parsed("transaction", alert)
