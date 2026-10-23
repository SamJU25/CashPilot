"""The bank sender domains CashPilot trusts by default.

A bank not listed here can still be used: the owner adds its sender domain on the Bank emails page.
"""

from __future__ import annotations

from typing import NamedTuple


class Bank(NamedTuple):
    name: str
    currency: str  # used when an alert shows only a symbol such as ¥ or $


# Sender domains, matched on the domain or any subdomain of it.
BANKS: dict[str, Bank] = {
    "icbc.com.cn": Bank("ICBC", "CNY"),
    "ccb.com": Bank("China Construction Bank", "CNY"),
    "abchina.com": Bank("Agricultural Bank of China", "CNY"),
    "boc.cn": Bank("Bank of China", "CNY"),
    "bankcomm.com": Bank("Bank of Communications", "CNY"),
    "cmbchina.com": Bank("China Merchants Bank", "CNY"),
    "webank.com": Bank("WeBank", "CNY"),
    "hsbc.com.hk": Bank("HSBC Hong Kong", "HKD"),
    "hsbc.co.uk": Bank("HSBC UK", "GBP"),
    "barclays.co.uk": Bank("Barclays", "GBP"),
    "chase.com": Bank("Chase", "USD"),
    "bankofamerica.com": Bank("Bank of America", "USD"),
    "wellsfargo.com": Bank("Wells Fargo", "USD"),
    "citi.com": Bank("Citi", "USD"),
    "citibank.com": Bank("Citibank", "USD"),
    "capitalone.com": Bank("Capital One", "USD"),
    "svb.com": Bank("Silicon Valley Bank", "USD"),
    "mercury.com": Bank("Mercury", "USD"),
    "brex.com": Bank("Brex", "USD"),
    "wise.com": Bank("Wise", "USD"),
    "revolut.com": Bank("Revolut", "GBP"),
    "stripe.com": Bank("Stripe", "USD"),
    "paypal.com": Bank("PayPal", "USD"),
    "monzo.com": Bank("Monzo", "GBP"),
    "starlingbank.com": Bank("Starling Bank", "GBP"),
    "sc.com": Bank("Standard Chartered", "HKD"),
    "bnpparibas.com": Bank("BNP Paribas", "EUR"),
    "santander.co.uk": Bank("Santander UK", "GBP"),
    "santander.com": Bank("Santander", "EUR"),
    "db.com": Bank("Deutsche Bank", "EUR"),
    "ubs.com": Bank("UBS", "CHF"),
    "dbs.com": Bank("DBS", "SGD"),
}


def bank_for(domain: str, extra: dict[str, Bank] | None = None) -> tuple[str, Bank] | None:
    """The trusted bank a sender domain belongs to, or None. `extra` holds the owner's own additions."""
    domain = domain.lower().strip(".")
    for known, bank in {**BANKS, **(extra or {})}.items():
        if domain == known or domain.endswith("." + known):
            return known, bank
    return None


def infer_bank_info(domain: str, default_currency: str = "USD") -> Bank:
    """Derives a clean human-readable bank name from an unlisted domain."""
    labels = domain.lower().strip(".").split(".")
    core = labels[-3] if len(labels) >= 3 and labels[-2] in ("co", "com", "net", "org") else labels[-2] if len(labels) >= 2 else labels[0]
    name = " ".join(part.capitalize() for part in core.replace("-", " ").replace("_", " ").split())
    return Bank(name=name, currency=default_currency)
