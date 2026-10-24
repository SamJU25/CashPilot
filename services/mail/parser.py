"""Turns one bank alert email into a transaction, deterministically.

Email is untrusted input: only the fields extracted here leave this module. The raw text never reaches
the agent's prompt, so an alert cannot carry instructions into the copilot.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Literal, Optional

import pypdf

from services.mail.banks import Bank, bank_for, infer_bank_info

if TYPE_CHECKING:
    from services.agent.schema import LLMConfig

logger = logging.getLogger(__name__)


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


def decode_header_text(val: str | None) -> str:
    if not val:
        return ""
    try:
        return str(make_header(decode_header(val)))
    except Exception:
        return str(val)


def decode_payload(payload: bytes, charset: str | None) -> str:
    if not payload:
        return ""
    if charset:
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, Exception):
            pass
    for enc in ("utf-8", "gb18030", "latin1"):
        try:
            return payload.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode("utf-8", errors="replace")


def body_text(msg: Message) -> str:
    """Plain text of the message, preferring the text part and flattening HTML otherwise, with PDF and CSV/TSV/TXT attachment fallback."""
    plain, html, attachment_parts = [], [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        fname = (part.get_filename() or "").lower()
        if ctype == "application/pdf" or fname.endswith(".pdf"):
            try:
                raw_pdf = part.get_payload(decode=True)
                if raw_pdf:
                    reader = pypdf.PdfReader(io.BytesIO(raw_pdf))
                    for page in reader.pages:
                        extracted = page.extract_text()
                        if extracted:
                            attachment_parts.append(extracted)
            except Exception:
                pass
            continue
        if fname.endswith((".csv", ".tsv", ".txt")) or ctype in ("text/csv", "text/tab-separated-values"):
            try:
                payload = part.get_payload(decode=True) or b""
                text = decode_payload(payload, part.get_content_charset())
                if text.strip():
                    attachment_parts.append(text)
            except Exception:
                pass
            continue
        if ctype not in ("text/plain", "text/html") or part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        text = decode_payload(payload, part.get_content_charset())
        (plain if ctype == "text/plain" else html).append(text)

    body = ""
    if plain:
        body = "\n".join(plain)
    elif html:
        p = _Text()
        p.feed("\n".join(html))
        body = "".join(p.parts)

    if attachment_parts:
        att_text = "\n".join(attachment_parts)
        body = f"{body}\n{att_text}" if body else att_text
    return body


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

# Broadened account tail pattern: supports "ending in 1234", "account ...1234", "card ••1234", "acct: 1234", "A/C 1234", etc.
_TAIL = re.compile(
    r"(?:尾号|末四位|卡号后四位|账号后四位|账户后[四4]位|ending(?:\s+(?:in|with))?|account\s*(?:no\.?|number|#)?\s*[x*•·#]+|card\s*[x*•·#]+|[x*•·#]{2,}|a/c\s*(?:no\.?|#)?\s*[x*•·#]*)\s*[:：#]?\s*(\d{4})(?!\d)"
    r"|(?:account|card|acct|visa|mastercard|amex|debit|checking)\s*[:：#]?\s*(?:[x*•·#]{1,16}|\.{2,4})\s*(\d{4})(?!\d)",
    re.I,
)

# Compound phrases to accurately resolve direction without confusing "received a payment" for an outflow
_IN = re.compile(
    r"(?:received (?:a )?payment|payment (?:was )?received|paid you|direct deposit|refund(?:ed)?|credit(?:ed)?|transferred? from|funds (?:were )?(?:added|received|credited)|money (?:was )?received|incoming (?:wire|transfer|payment)|payout|cash ?back|payroll|interest (?:earned|paid|credited)|收入|存入|转入|入账|汇入|退款|到账|\bdeposit(?:ed)?\b|\breceived\b|incoming)",
    re.I,
)
_OUT = re.compile(
    r"(?:payment to|paid to|\bpaid\b|\bspent\b|debited|debit of|withdrawal|withdrawn|purchase(?:d)?|transferred? to|sent (?:a )?payment|money sent|\bsent\b|bill payment|charge(?:d)?|\bfee\b|支出|消费|转出|扣款|取现|付款)",
    re.I,
)
_BALANCE = re.compile(r"余额|可用余额|balance|avl\.? bal|avail(?:able)? bal", re.I)

from services.calculations.currency_registry import CurrencyRegistry, SYMBOL_MAP

_SYMS = sorted(list(SYMBOL_MAP.keys()) + ["¥", "￥", "Rs", "Rs.", "₹"], key=len, reverse=True)
_SYM_PATTERN = "|".join(re.escape(s) for s in _SYMS)
_CODES_PATTERN = r"\b[A-Za-z]{3}\b|RMB|元"

_MONEY = re.compile(
    rf"(?:(?P<code>{_CODES_PATTERN})\s*|(?P<sym>{_SYM_PATTERN})\s*)(?P<n>[-+]?\d[\d,]*(?:\.\d{{1,2}})?)"
    rf"|(?P<n2>[-+]?\d[\d,]*(?:\.\d{{1,2}})?)\s*(?:(?P<code2>{_CODES_PATTERN})|(?P<sym2>{_SYM_PATTERN}))",
    re.I,
)
_DATE_NUM = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
_DATE_CN_SHORT = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATE_EN = re.compile(
    r"\b(?P<m>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>20\d{2})\b"
    r"|\b(?P<d2>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m2>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?),?\s+(?P<y2>20\d{2})\b",
    re.I,
)
_PARTY = re.compile(
    r"(?:对方户名|对方账户名|商户名称|商户|交易对手|付款人|收款人|\bpaid to\b|\bsent to\b|\bto(?!\s+(?:your|account|card|acct|checking|savings))\b|\bfrom(?!\s+(?:your|account|card|acct|checking|savings))\b|\bat\b)\s*[:：]?\s*([^\n,，。;；:：]{2,40}?)(?=\.\s|\.$|[\n,，。;；:：]|\s+(?:on|was|has|is|into|for)\s|$)",
    re.I,
)


def _money(text: str, default_currency: str) -> list[tuple[int, int, str, Decimal]]:
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

        out.append((m.start(), m.end(), currency, value))
    return out


def _occurred(text: str, msg: Message) -> str:
    sent: Optional[datetime] = None
    try:
        sent = parsedate_to_datetime(msg.get("Date", ""))
    except Exception:
        pass
    if m := _DATE_NUM.search(text):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    if m := _DATE_EN.search(text):
        try:
            m_str = (m.group("m") or m.group("m2"))[:3].lower()
            d_val = int(m.group("d") or m.group("d2"))
            y_val = int(m.group("y") or m.group("y2"))
            return date(y_val, _MONTHS[m_str], d_val).isoformat()
        except (KeyError, ValueError):
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


def resolve_direction(text: str, pos: int, end_pos: int, amount: Decimal) -> Optional[Literal["IN", "OUT"]]:
    surrounding_before = text[max(0, pos - 10) : pos].strip()
    surrounding_after = text[end_pos : min(len(text), end_pos + 15)].strip()

    if amount < 0 or surrounding_before.endswith("-") or re.search(r"^\s*-\s*", surrounding_before):
        return "OUT"
    if surrounding_before.endswith("+") or re.search(r"^\s*\+\s*", surrounding_before):
        return "IN"
    if re.search(r"^(?:CR|Cr)\b", surrounding_after):
        return "IN"
    if re.search(r"^(?:DR|Dr)\b", surrounding_after):
        return "OUT"

    window = text[max(0, pos - 120) : min(len(text), end_pos + 60)]
    in_strong = re.search(
        r"(?:received (?:a )?payment|payment (?:was )?received|paid you|direct deposit|\bdeposit(?:ed)?\b|refund(?:ed)?|\bcredit(?:ed)?\b|transferred? from|transfer from|funds (?:were )?(?:added|received|credited)|money (?:was )?received|incoming (?:wire|transfer|payment)|payout|cash ?back|payroll|interest (?:earned|paid|credited)|收入|存入|转入|入账|汇入|退款|到账)",
        window,
        re.I,
    )
    out_strong = re.search(
        r"(?:payment to|paid to|sent (?:a )?payment|debited|debit of|withdrawal|withdrawn|purchase(?:d)?|transferred? to|transfer to|money sent|\bsent\b|bill payment|charge(?:d)?|\bfee\b|\bspent\b|支出|消费|转出|扣款|取现|付款)",
        window,
        re.I,
    )

    if in_strong and not out_strong:
        return "IN"
    if out_strong and not in_strong:
        return "OUT"
    if in_strong and out_strong:
        if re.search(r"(?:received|deposit|credit|refund|from|paid you|入账|转入|到账)", in_strong.group(0), re.I):
            return "IN"
        return "OUT" if out_strong.start() > in_strong.start() else "IN"

    before = text[:pos]
    out_at = max((m.end() for m in _OUT.finditer(before)), default=-1)
    in_at = max((m.end() for m in _IN.finditer(before)), default=-1)
    if out_at < 0 and in_at < 0:
        out_at = 0 if _OUT.search(text) else -1
        in_at = 0 if _IN.search(text) else -1
    return "OUT" if out_at > in_at else "IN" if in_at > out_at else None


KIE_ALERT_DIRECTIVE = (
    "You are a bank transaction Key Information Extraction (KIE) engine.\n"
    "Your role is strictly to extract structured transaction data from bank notification emails.\n"
    "Respond ONLY with a valid JSON object matching this schema:\n"
    "{\n"
    '  "is_bank_alert": true,\n'
    '  "bank_name": "string or null",\n'
    '  "account_tail": "string (last 4 digits of card/account) or null",\n'
    '  "direction": "IN" or "OUT" or null,\n'
    '  "amount": "string number, e.g. 1250.00, or null",\n'
    '  "currency": "ISO 3-letter currency code or null",\n'
    '  "balance_after": "string number or null",\n'
    '  "counterparty": "string or null",\n'
    '  "occurred_on": "YYYY-MM-DD or null"\n'
    "}\n"
    "Rules:\n"
    "- Set is_bank_alert to false if the email is marketing, spam, newsletter, or a one-time verification password (OTP).\n"
    '- "direction": "IN" for deposits, incoming transfers, salary, credits, received payments, refunds. "OUT" for withdrawals, purchases, payments, debits, charges, fees.\n'
    "- Output ONLY the JSON string without any markdown formatting, backticks, or explanation.\n"
)


def extract_alert_with_llm(
    text: str,
    llm_config: Optional[LLMConfig],
    default_currency: str = "USD",
) -> Optional[dict]:
    """Fallback extractor using an LLM to resolve ambiguous alerts (e.g. unknown direction or account phrasing)."""
    if not llm_config or getattr(llm_config, "provider", "offline").lower() == "offline":
        return None
    try:
        from services.agent.llm_bridge import mask_pii, query_external_llm

        sanitized = mask_pii(text[:2500])
        prompt = f"Extract transaction details from this bank notification:\n\n{sanitized}"
        raw_res = query_external_llm(
            prompt=prompt,
            system_instruction=KIE_ALERT_DIRECTIVE,
            config=llm_config,
        )
        if not raw_res:
            return None
        cleaned = raw_res.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return None
        if not data.get("is_bank_alert", True):
            return None
        return data
    except Exception as exc:
        logger.debug("LLM KIE extraction skipped or failed: %s", exc)
        return None


def parse_alert(
    msg: Message,
    raw: bytes,
    provider_stamps: bool,
    extra_banks: Optional[dict[str, Bank]] = None,
    trusted: Optional[list[str]] = None,
    default_currency: str = "USD",
    llm_config: Optional[LLMConfig] = None,
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

    subject = decode_header_text(msg.get("Subject", ""))
    text = f"{subject}\n{body_text(msg)}"
    if _CODE.search(text):
        return Parsed("ignored", reason="login_code")

    money = _money(text, bank.currency)
    balance = next((m for m in money if _BALANCE.search(text[max(0, m[0] - 24) : m[0]])), None)
    amounts = [m for m in money if m is not balance and abs(m[3]) > 0]

    kie_data: Optional[dict] = None

    if not amounts and llm_config:
        kie_data = extract_alert_with_llm(text, llm_config, default_currency=bank.currency)
        if kie_data and kie_data.get("amount"):
            try:
                amt_str = str(kie_data["amount"]).replace(",", "").strip()
                val = Decimal(amt_str)
                if val > 0:
                    curr_str = str(kie_data.get("currency") or bank.currency).strip().upper()
                    resolved_curr = CurrencyRegistry.resolve_currency(curr_str, bank.currency) or bank.currency
                    amounts = [(0, len(text), resolved_curr, val)]
            except Exception:
                pass

    if not amounts:
        return Parsed("ignored", reason="no_amount")
    pos, end_pos, currency, raw_amount = amounts[0]

    direction = resolve_direction(text, pos, end_pos, raw_amount)
    amount = abs(raw_amount)

    tail = _TAIL.search(text)
    tail_val = (tail.group(1) or tail.group(2)) if tail else None

    # If direction or account tail is missing and LLM fallback is configured, extract via KIE
    if (direction is None or not tail_val) and llm_config and not kie_data:
        kie_data = extract_alert_with_llm(text, llm_config, default_currency=currency)

    if kie_data:
        if direction is None and kie_data.get("direction") in ("IN", "OUT"):
            direction = kie_data["direction"]
        if not tail_val and kie_data.get("account_tail"):
            raw_tail = str(kie_data["account_tail"]).strip()
            m_t = re.search(r"(\d{4})", raw_tail)
            if m_t:
                tail_val = m_t.group(1)
            elif len(raw_tail) in (4, 5, 6) and raw_tail.isalnum():
                tail_val = raw_tail

    # If unlisted and lacks account tail or direction, ignore as non-bank email
    if is_unlisted and (not tail_val or direction is None):
        return Parsed("ignored", reason="sender_not_trusted")

    party = next((m for m in [*_PARTY.finditer(text[pos:]), *_PARTY.finditer(text)] if re.search(r"[^\W\d_]", m.group(1))), None)
    counterparty = party.group(1).strip()[:40] if party else None
    if not counterparty and kie_data and kie_data.get("counterparty"):
        cp = str(kie_data["counterparty"]).strip()
        if cp and cp.lower() not in ("null", "none"):
            counterparty = cp[:40]

    balance_val = balance[3] if balance else None
    if balance_val is None and kie_data and kie_data.get("balance_after"):
        try:
            balance_val = Decimal(str(kie_data["balance_after"]).replace(",", "").strip())
        except Exception:
            pass

    occurred_date = _occurred(text, msg)
    if kie_data and kie_data.get("occurred_on"):
        raw_date = str(kie_data["occurred_on"]).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            try:
                datetime.strptime(raw_date, "%Y-%m-%d")
                occurred_date = raw_date
            except ValueError:
                pass

    verified = (bank_domain in (trusted or [])) or verify_sender(msg, bank_domain, provider_stamps)
    alert = Alert(
        id=message_id(msg, raw),
        bank=bank.name,
        bank_domain=bank_domain,
        account_tail=tail_val if tail_val else "primary",
        currency=currency,
        direction=direction or "IN",
        amount=amount,
        balance_after=balance_val,
        occurred_on=occurred_date,
        counterparty=counterparty,
        verified=verified,
    )
    if is_unlisted and bank_domain not in (trusted or []):
        return Parsed("review", alert, review="unlisted_bank")
    if not tail_val:
        return Parsed("review", alert, review="no_account")
    if direction is None:
        return Parsed("review", alert, review="no_direction")
    if not verified:
        return Parsed("review", alert, review="unverified_sender")
    return Parsed("transaction", alert)
