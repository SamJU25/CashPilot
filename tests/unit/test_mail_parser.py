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



def test_received_payment_direction_inflow():
    msg, raw = mail(
        "Stripe <notifications@stripe.com>",
        "Payment received",
        "You received a payment of $850.00 from Acme Holdings on your account ending in 7721.",
        ["mx.google.com; dkim=pass header.d=stripe.com"],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert (p.alert.direction, p.alert.amount, p.alert.account_tail) == ("IN", Decimal("850.00"), "7721")


def test_explicit_signed_amounts_and_cr_dr():
    # Credit token CR
    msg1, raw1 = mail(
        "Citi <alerts@citi.com>",
        "Account notice",
        "Account ending in 4432: $250.00 CR from Vendor Refund.",
        ["mx.google.com; dkim=pass header.d=citi.com"],
    )
    p1 = parse_alert(msg1, raw1, True)
    assert p1.kind == "transaction"
    assert (p1.alert.direction, p1.alert.amount) == ("IN", Decimal("250.00"))

    # Debit token DR
    msg2, raw2 = mail(
        "Citi <alerts@citi.com>",
        "Account notice",
        "Account ending in 4432: $120.00 DR for Office Supplies.",
        ["mx.google.com; dkim=pass header.d=citi.com"],
    )
    p2 = parse_alert(msg2, raw2, True)
    assert p2.kind == "transaction"
    assert (p2.alert.direction, p2.alert.amount) == ("OUT", Decimal("120.00"))


def test_various_account_tail_patterns():
    # Card with bullet format: card ••9012
    msg, raw = mail(
        "Barclays <alerts@barclays.co.uk>",
        "Payment sent",
        "You paid £45.00 to TFL with card ••9012.",
        ["mx.google.com; dkim=pass header.d=barclays.co.uk"],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert p.alert.account_tail == "9012"
    assert p.alert.direction == "OUT"


def test_pdf_attachment_parsing_in_email():
    from tests.unit.test_pdf_parser import _create_synthetic_bank_pdf
    pdf_bytes = _create_synthetic_bank_pdf(["Debit Notice: You paid $340.00 to Dell on account ending in 1188."])
    
    msg = EmailMessage()
    msg["Authentication-Results"] = "mx.google.com; dkim=pass header.d=chase.com"
    msg["From"] = "Chase <no.reply.alerts@chase.com>"
    msg["Subject"] = "Transaction Notice"
    msg["Date"] = "Thu, 22 Oct 2026 10:31:00 +0800"
    msg["Message-ID"] = "<pdf_test@chase.com>"
    msg.set_content("Please find your attached debit notice.")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="debit_advice.pdf")
    raw = msg.as_bytes()
    
    p = parse_alert(message_from_bytes(raw), raw, True)
    assert p.kind == "transaction"
    assert (p.alert.direction, p.alert.amount, p.alert.account_tail) == ("OUT", Decimal("340.00"), "1188")


def test_llm_kie_resolves_ambiguous_direction(monkeypatch):
    from services.agent.schema import LLMConfig
    cfg = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.0-flash")

    # Email with no direction keywords in regex
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Account activity notification",
        "An activity of $450.00 occurred on your account ending in 1234 on 2026-10-22.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )

    # 1. Without LLM config -> needs review due to no direction
    p_offline = parse_alert(msg, raw, True, llm_config=None)
    assert p_offline.kind == "review"
    assert p_offline.review == "no_direction"

    # 2. With LLM config and mock returning direction OUT
    def mock_query(prompt, system_instruction, config, history=None):
        return '{"is_bank_alert": true, "direction": "OUT", "account_tail": "1234", "amount": "450.00", "currency": "USD"}'

    monkeypatch.setattr("services.agent.llm_bridge.query_external_llm", mock_query)
    p_kie = parse_alert(msg, raw, True, llm_config=cfg)
    assert p_kie.kind == "transaction"
    assert p_kie.alert.direction == "OUT"
    assert p_kie.alert.amount == Decimal("450.00")
    assert p_kie.alert.account_tail == "1234"


def test_llm_kie_resolves_missing_account_tail(monkeypatch):
    from services.agent.schema import LLMConfig
    cfg = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.0-flash")

    # Email with obscure phrasing for account tail
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Direct deposit received",
        "Direct deposit of $1,500.00 posted to payroll bucket primary-ref-7788.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )

    # 1. Without LLM config -> review no_account
    p_offline = parse_alert(msg, raw, True, llm_config=None)
    assert p_offline.kind == "review"
    assert p_offline.review == "no_account"

    # 2. With LLM config resolving account tail
    def mock_query(prompt, system_instruction, config, history=None):
        return '{"is_bank_alert": true, "direction": "IN", "account_tail": "7788", "amount": "1500.00", "currency": "USD"}'

    monkeypatch.setattr("services.agent.llm_bridge.query_external_llm", mock_query)
    p_kie = parse_alert(msg, raw, True, llm_config=cfg)
    assert p_kie.kind == "transaction"
    assert p_kie.alert.account_tail == "7788"
    assert p_kie.alert.direction == "IN"
    assert p_kie.alert.amount == Decimal("1500.00")


def test_llm_kie_unlisted_bank_triage(monkeypatch):
    from services.agent.schema import LLMConfig
    cfg = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.0-flash")

    # Unlisted bank with ambiguous phrasing
    msg, raw = mail(
        "Regional Credit Union <alerts@myregionalcu.org>",
        "Notification",
        "Activity recorded: $250.00 on record 4321.",
        ["mx.google.com; dkim=pass header.d=myregionalcu.org"],
    )

    # Without LLM -> ignored as sender_not_trusted
    p_offline = parse_alert(msg, raw, True, llm_config=None)
    assert p_offline.kind == "ignored"
    assert p_offline.reason == "sender_not_trusted"

    # With LLM resolving direction and tail -> rescued to human review queue as unlisted_bank
    def mock_query(prompt, system_instruction, config, history=None):
        return '{"is_bank_alert": true, "direction": "OUT", "account_tail": "4321", "amount": "250.00", "currency": "USD"}'

    monkeypatch.setattr("services.agent.llm_bridge.query_external_llm", mock_query)
    p_kie = parse_alert(msg, raw, True, llm_config=cfg)
    assert p_kie.kind == "review"
    assert p_kie.review == "unlisted_bank"
    assert p_kie.alert.account_tail == "4321"
    assert p_kie.alert.direction == "OUT"


def test_llm_kie_graceful_fallback_on_failure(monkeypatch):
    from services.agent.schema import LLMConfig
    cfg = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.0-flash")

    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Notification",
        "An activity of $450.00 occurred on your account ending in 1234 on 2026-10-22.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )

    # When query_external_llm raises an exception
    def mock_query_error(prompt, system_instruction, config, history=None):
        raise ConnectionError("API rate limit exceeded")

    monkeypatch.setattr("services.agent.llm_bridge.query_external_llm", mock_query_error)
    p = parse_alert(msg, raw, True, llm_config=cfg)
    # Safely falls back to regex review object without crashing
    assert p.kind == "review"
    assert p.review == "no_direction"


def test_llm_kie_resolves_missing_amount(monkeypatch):
    from services.agent.schema import LLMConfig
    cfg = LLMConfig(provider="gemini", api_key="test-key", model_name="gemini-2.0-flash")

    # Email with unusual tabular structure where regex missed amount
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Transaction update",
        "Debit notice: your account ending in 9988 was debited. Amount in words: Five Hundred USD.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )

    def mock_query(prompt, system_instruction, config, history=None):
        return '{"is_bank_alert": true, "direction": "OUT", "account_tail": "9988", "amount": "500.00", "currency": "USD"}'

    monkeypatch.setattr("services.agent.llm_bridge.query_external_llm", mock_query)
    p = parse_alert(msg, raw, True, llm_config=cfg)
    assert p.kind == "transaction"
    assert p.alert.amount == Decimal("500.00")
    assert p.alert.direction == "OUT"
    assert p.alert.account_tail == "9988"


def test_mime_encoded_subject_decoding():
    # RFC 2047 encoded subject: "=?UTF-8?B?5pS25Yiw5Lqk5piT6YCa55+l?=" -> "收到交易通知"
    raw_bytes = (
        b"From: notice@mail.icbc.com.cn\r\n"
        b"Subject: =?UTF-8?B?5pS25Yiw5Lqk5piT6YCa55+l?=\r\n"
        b"Authentication-Results: " + GMAIL_PASS.encode() + b"\r\n"
        b"Date: Thu, 22 Oct 2026 10:31:00 +0800\r\n\r\n"
        b"\xe6\x82\xa8\xe5\xb0\xbe\xe5\x8f\xb71234\xe7\x9a\x84\xe8\xb4\xa6\xe6\x88\xb7\xe4\xba\x8e2026\xe5\xb9\xb410\xe6\x9c\x8822\xe6\x97\xa5\xe6\x94\xb6\xe5\x85\xa5\xe4\xba\xba\xe6\xb0\x91\xe5\xb8\x811,200.00\xe5\x85\x83\xe3\x80\x82"
    )
    msg = message_from_bytes(raw_bytes)
    p = parse_alert(msg, raw_bytes, provider_stamps=True)
    assert p.kind == "transaction"
    assert p.alert.amount == Decimal("1200.00")
    assert p.alert.direction == "IN"
    assert p.alert.account_tail == "1234"


def test_english_textual_date_parsing():
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Payment Notice",
        "A payment of $85.00 was debited from your card ending in 4433 on October 24, 2026.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert p.alert.occurred_on == "2026-10-24"
    assert p.alert.amount == Decimal("85.00")
    assert p.alert.direction == "OUT"
    assert p.alert.account_tail == "4433"


def test_outflow_counterparty_extraction():
    msg, raw = mail(
        "Chase <no.reply.alerts@chase.com>",
        "Debit notification",
        "You sent $42.50 to Starbucks Coffee on 2026-10-24 from account ending in 5566.",
        ["mx.google.com; dkim=pass header.d=chase.com"],
    )
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert p.alert.counterparty == "Starbucks Coffee"


def test_gb18030_chinese_payload_decoding():
    # Simulates a Chinese bank sending GB2312/GB18030 encoded body with no charset header
    body_gb = "您尾号8888的账户于2026年10月24日转入人民币3,000.00元。".encode("gb18030")
    raw_bytes = (
        b"From: notice@mail.icbc.com.cn\r\n"
        b"Subject: ICBC Alert\r\n"
        b"Content-Type: text/plain\r\n"
        b"Authentication-Results: " + GMAIL_PASS.encode() + b"\r\n\r\n" + body_gb
    )
    msg = message_from_bytes(raw_bytes)
    p = parse_alert(msg, raw_bytes, True)
    assert p.kind == "transaction"
    assert p.alert.amount == Decimal("3000.00")
    assert p.alert.direction == "IN"
    assert p.alert.account_tail == "8888"


def test_csv_attachment_parsing():
    m = EmailMessage()
    m["Authentication-Results"] = "mx.google.com; dkim=pass header.d=chase.com; dmarc=pass header.from=chase.com"
    m["From"] = "Chase <no.reply.alerts@chase.com>"
    m["Subject"] = "Daily Transaction Summary"
    m["Date"] = "Thu, 24 Oct 2026 10:00:00 +0000"
    m["Message-ID"] = "<csv1@chase.com>"
    m.set_content("Please find your daily transaction report attached.")
    csv_payload = b"Date,Description,Amount,Account\n2026-10-24,Vendor Payment,-$450.00,Ending in 7788\n"
    m.add_attachment(csv_payload, maintype="text", subtype="csv", filename="report_20261024.csv")

    raw = m.as_bytes()
    msg = message_from_bytes(raw)
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert p.alert.amount == Decimal("450.00")
    assert p.alert.direction == "OUT"
    assert p.alert.account_tail == "7788"
    assert p.alert.occurred_on == "2026-10-24"


def test_txt_attachment_parsing():
    m = EmailMessage()
    m["Authentication-Results"] = GMAIL_PASS
    m["From"] = "工商银行 <notice@mail.icbc.com.cn>"
    m["Subject"] = "电子对账通知"
    m["Date"] = "Thu, 24 Oct 2026 10:00:00 +0800"
    m["Message-ID"] = "<txt1@icbc.com.cn>"
    m.set_content("对账清单见附件。")
    txt_payload = "账户尾号9911于2026年10月24日存入人民币15,000.00元，可用余额人民币20,000.00元。".encode("utf-8")
    m.add_attachment(txt_payload, maintype="text", subtype="plain", filename="notice.txt")

    raw = m.as_bytes()
    msg = message_from_bytes(raw)
    p = parse_alert(msg, raw, True)
    assert p.kind == "transaction"
    assert p.alert.amount == Decimal("15000.00")
    assert p.alert.balance_after == Decimal("20000.00")
    assert p.alert.direction == "IN"
    assert p.alert.account_tail == "9911"



