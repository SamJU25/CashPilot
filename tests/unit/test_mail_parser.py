"""Bank alert parsing. The emails here are synthetic, written in the common alert shapes; real bank
samples should be added as fixtures when owners share them."""

from decimal import Decimal
from email import message_from_bytes
from email.message import EmailMessage

from services.mail.banks import Bank
from services.mail.parser import parse_alert, verify_sender


def mail(sender: str, subject: str, body: str, auth: list[str] | None = None, html: bool = False, msg_id: str = "<a1@bank>") -> tuple:
    m = EmailMessage()
    for h in auth or []:
        m["Authentication-Results"] = h
    m["From"] = sender
    m["Subject"] = subject
    m["Date"] = "Thu, 22 Oct 2026 10:31:00 +0800"
    m["Message-ID"] = msg_id
    m.set_content(body, subtype="html" if html else "plain")
    raw = m.as_bytes()
    return message_from_bytes(raw), raw


GMAIL_PASS = "mx.google.com; dkim=pass header.i=@icbc.com.cn header.s=s1 header.b=abc; spf=pass smtp.mailfrom=icbc.com.cn; dmarc=pass (p=REJECT) header.from=icbc.com.cn"


def test_chinese_outflow_with_balance():
    msg, raw = mail(
        "工商银行 <notice@mail.icbc.com.cn>",
        "账户变动提醒",
        "您尾号1234的账户于2026年10月22日10:31支出(消费)人民币2,580.00元，对方户名：上海某某科技有限公司，可用余额人民币45,320.17元。",
        [GMAIL_PASS],
    )
    p = parse_alert(msg, raw, provider_stamps=True)
    assert p.kind == "transaction"
    a = p.alert
    assert (a.bank, a.account_tail, a.direction, a.currency) == ("ICBC", "1234", "OUT", "CNY")
    assert a.amount == Decimal("2580.00") and a.balance_after == Decimal("45320.17")
    assert a.occurred_on == "2026-10-22"
    assert a.counterparty.startswith("上海某某科技")


def test_english_credit_html():
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "You received a deposit",
        "<p>A deposit of <b>$1,200.50</b> was credited to your account ending in 9876 on 2026-10-21.</p><p>Available balance: $8,004.10</p>",
        ["mx.google.com; dkim=pass header.d=chase.com; dmarc=pass header.from=chase.com"],
        html=True,
    )
    p = parse_alert(msg, raw, provider_stamps=True)
    assert p.kind == "transaction"
    assert (p.alert.direction, p.alert.amount, p.alert.balance_after, p.alert.account_tail) == ("IN", Decimal("1200.50"), Decimal("8004.10"), "9876")


def test_login_codes_are_dropped():
    msg, raw = mail("notice@icbc.com.cn", "验证码", "您的验证码为 482913，金额 ¥100.00，尾号1234。", [GMAIL_PASS])
    assert parse_alert(msg, raw, True).reason == "login_code"


def test_untrusted_sender_without_account_is_ignored():
    msg, raw = mail("alerts@icbc-security.com", "账户变动", "转入人民币50,000.00元", [GMAIL_PASS])
    assert parse_alert(msg, raw, True).kind == "ignored"


def test_unlisted_bank_with_transaction_goes_to_review():
    msg, raw = mail("alerts@icbc-security.com", "账户变动", "尾号1234 转入人民币50,000.00元", [GMAIL_PASS])
    parsed = parse_alert(msg, raw, True)
    assert parsed.kind == "review"
    assert parsed.review == "unlisted_bank"
    assert parsed.alert.bank == "Icbc Security" 


def test_forged_auth_header_below_the_providers_is_not_trusted():
    msg, raw = mail(
        "notice@icbc.com.cn",
        "账户变动",
        "尾号1234 转入人民币50,000.00元",
        ["mx.google.com; dkim=fail header.d=icbc.com.cn; dmarc=fail header.from=icbc.com.cn", GMAIL_PASS],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "review" and p.review == "unverified_sender"


def test_provider_without_stamp_sends_to_review():
    msg, raw = mail("notice@icbc.com.cn", "账户变动", "尾号1234 转入人民币500.00元", [GMAIL_PASS])
    assert verify_sender(msg, "icbc.com.cn", provider_stamps=False) is False
    assert parse_alert(msg, raw, provider_stamps=False).review == "unverified_sender"


def test_missing_account_goes_to_review():
    msg, raw = mail("notice@icbc.com.cn", "账户变动", "您的账户转入人民币500.00元", [GMAIL_PASS])
    assert parse_alert(msg, raw, True).review == "no_account"


def test_owner_added_bank_and_symbol_currency():
    msg, raw = mail(
        "alerts@mybank.example",
        "Card spend",
        "Your card xxxx4321 was debited £42.10 at CORNER CAFE. Avl bal £310.00",
        ["mx.google.com; dkim=pass header.d=mybank.example"],
    )
    p = parse_alert(msg, raw, True, extra_banks={"mybank.example": Bank("My Bank", "GBP")})
    assert p.kind == "transaction"
    assert (p.alert.currency, p.alert.direction, p.alert.amount, p.alert.counterparty) == ("GBP", "OUT", Decimal("42.10"), "CORNER CAFE")


def test_same_email_has_same_id():
    a = parse_alert(*mail("notice@icbc.com.cn", "x", "尾号1234 转入人民币5.00元", [GMAIL_PASS]), True)
    b = parse_alert(*mail("notice@icbc.com.cn", "x", "尾号1234 转入人民币5.00元", [GMAIL_PASS]), True)
    assert a.alert.id == b.alert.id


def test_party_stops_before_the_date():
    msg, raw = mail("alerts@chase.com", "Card", "Your card xxxx7781 was debited $64.20 at CORNER CAFE on 2026-10-22. Avl bal $812.33", ["mx.google.com; dkim=pass header.d=chase.com"])
    assert parse_alert(msg, raw, True).alert.counterparty == "CORNER CAFE"
    msg, raw = mail("alerts@chase.com", "Deposit", "A deposit of $4,250.00 from NORTHWIND LLC was credited to your account ending in 4417 on 2026-10-19.", ["mx.google.com; dkim=pass header.d=chase.com"])
    assert parse_alert(msg, raw, True).alert.counterparty == "NORTHWIND LLC"


def test_mercury_deposit_alert():
    msg, raw = mail(
        "Mercury Alerts <notifications@mercury.com>",
        "You received a deposit of $5,000.00",
        "A deposit of $5,000.00 from ACME CORP was credited to your Mercury checking account ending in 5521. Available balance: $28,450.00.",
        ["mx.google.com; dkim=pass header.d=mercury.com"],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert (p.alert.bank, p.alert.account_tail, p.alert.direction, p.alert.currency) == ("Mercury", "5521", "IN", "USD")
    assert p.alert.amount == Decimal("5000.00") and p.alert.balance_after == Decimal("28450.00")


def test_trusted_domain_bypasses_unverified_sender():
    msg, raw = mail("notice@custombank.com", "账户变动", "尾号9988 转入人民币1,200.00元", auth=[])
    # Without trusted domain and without provider stamp -> review as unverified_sender
    p1 = parse_alert(msg, raw, provider_stamps=False, extra_banks={"custombank.com": Bank("Custom Bank", "CNY")})
    assert p1.kind == "review" and p1.review == "unverified_sender"
    # With trusted domain -> verified as transaction
    p2 = parse_alert(
        msg,
        raw,
        provider_stamps=False,
        extra_banks={"custombank.com": Bank("Custom Bank", "CNY")},
        trusted=["custombank.com"],
    )
    assert p2.kind == "transaction"
    assert p2.alert.verified is True

def test_dynamic_currency_resolution_chf_and_aed():
    msg, raw = mail(
        "UBS Alerts <alerts@ubs.com>",
        "Account debit notification",
        "Your account ending in 7722 was debited CHF 3,450.00 at Zurich Tech. Available balance: CHF 12,000.00.",
        ["mx.google.com; dkim=pass header.d=ubs.com"],
    )
    p = parse_alert(msg, raw, True, default_currency="CHF")
    assert p.kind == "transaction"
    assert (p.alert.currency, p.alert.direction, p.alert.amount, p.alert.balance_after) == ("CHF", "OUT", Decimal("3450.00"), Decimal("12000.00"))

    msg2, raw2 = mail(
        "Emirates NBD <alerts@emiratesnbd.com>",
        "Credit Alert",
        "A deposit of 5,000.00 AED was credited to your account ending in 8844. Avl bal: 25,000.00 AED.",
        ["mx.google.com; dkim=pass header.d=emiratesnbd.com"],
    )
    p2 = parse_alert(msg2, raw2, True, default_currency="AED")
    assert p2.kind == "review" and p2.review == "unlisted_bank"
    assert (p2.alert.currency, p2.alert.direction, p2.alert.amount) == ("AED", "IN", Decimal("5000.00"))


def test_dynamic_currency_symbols():
    # Brazilian Real R$
    msg, raw = mail("Nubank <alerts@nubank.com.br>", "Card Transaction", "Spent R$ 450.50 on card ending in 3311.", ["mx.google.com; dkim=pass header.d=nubank.com.br"])
    p = parse_alert(msg, raw, True, default_currency="BRL")
    assert p.kind == "review" and p.review == "unlisted_bank"
    assert p.alert.currency == "BRL" and p.alert.amount == Decimal("450.50")

    # Indian Rupee Rs
    msg2, raw2 = mail("HDFC Bank <alerts@hdfcbank.com>", "Txn Alert", "Rs 15,200.00 credited to account ending in 4499.", ["mx.google.com; dkim=pass header.d=hdfcbank.com"])
    p2 = parse_alert(msg2, raw2, True, default_currency="INR")
    assert p2.kind == "review" and p2.review == "unlisted_bank"
    assert p2.alert.currency == "INR" and p2.alert.amount == Decimal("15200.00")

