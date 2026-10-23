"""Finding IMAP settings from an address, against a fake network. The XML mirrors the shape
autoconfig.thunderbird.net served for these domains on 2026-10-22."""

import httpx

from services.mail.discover import discover

GMAIL = """<clientConfig version="1.1"><emailProvider id="googlemail.com">
<domain>gmail.com</domain><displayShortName>GMail</displayShortName>
<incomingServer type="imap"><hostname>imap.gmail.com</hostname><port>993</port><socketType>SSL</socketType>
<username>%EMAILADDRESS%</username><authentication>OAuth2</authentication><authentication>password-cleartext</authentication></incomingServer>
</emailProvider></clientConfig>"""

OUTLOOK = """<clientConfig version="1.1"><emailProvider id="outlook.com"><displayShortName>Outlook</displayShortName>
<incomingServer type="imap"><hostname>outlook.office365.com</hostname><port>993</port><socketType>SSL</socketType>
<authentication>OAuth2</authentication><username>%EMAILADDRESS%</username></incomingServer></emailProvider></clientConfig>"""

ICLOUD = """<clientConfig version="1.1"><emailProvider id="icloud.com"><displayShortName>iCloud</displayShortName>
<incomingServer type="imap"><hostname>imap.mail.me.com</hostname><port>993</port><socketType>SSL</socketType>
<username>%EMAILLOCALPART%</username><authentication>password-cleartext</authentication></incomingServer></emailProvider></clientConfig>"""


def network(routes: dict[str, str], mx: dict[str, list[str]] | None = None) -> tuple[httpx.Client, list[str]]:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        if req.url.host == "cloudflare-dns.com":
            hosts = (mx or {}).get(req.url.params["name"], [])
            return httpx.Response(200, json={"Answer": [{"data": f"{10 * (i + 1)} {h}."} for i, h in enumerate(hosts)]})
        key = f"{req.url.host}{req.url.path}"
        return httpx.Response(200, text=routes[key]) if key in routes else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def no_probe(host: str, port: int) -> bool:
    return False


def test_known_provider_comes_from_ispdb_and_only_the_domain_is_sent():
    client, seen = network({"autoconfig.thunderbird.net/v1.1/gmail.com": GMAIL})
    s = discover("me.alerts@gmail.com", client, no_probe)
    assert (s.host, s.port, s.username, s.source, s.oauth_only) == ("imap.gmail.com", 993, "me.alerts@gmail.com", "ispdb", False)
    assert not any("me.alerts" in u for u in seen if "thunderbird.net" in u)


def test_oauth_only_provider_is_flagged():
    client, _ = network({"autoconfig.thunderbird.net/v1.1/outlook.com": OUTLOOK})
    assert discover("biz@outlook.com", client, no_probe).oauth_only is True


def test_local_part_username():
    client, _ = network({"autoconfig.thunderbird.net/v1.1/icloud.com": ICLOUD})
    assert discover("shop.alerts@icloud.com", client, no_probe).username == "shop.alerts"


def test_company_domain_found_through_its_mail_host():
    client, _ = network({"autoconfig.thunderbird.net/v1.1/google.com": GMAIL}, mx={"acme.example": ["aspmx.l.google.com"]})
    s = discover("alerts@acme.example", client, no_probe)
    assert (s.host, s.source) == ("imap.gmail.com", "mx")


def test_providers_own_config_wins(monkeypatch):
    monkeypatch.setattr("services.mail.discover.public_ips", lambda host: ["93.184.216.34"])
    own = GMAIL.replace("imap.gmail.com", "imap.acme.example")
    client, _ = network({"autoconfig.acme.example/mail/config-v1.1.xml": own, "autoconfig.thunderbird.net/v1.1/acme.example": GMAIL})
    assert discover("alerts@acme.example", client, no_probe).host == "imap.acme.example"


def test_providers_own_config_on_a_private_address_is_skipped(monkeypatch):
    monkeypatch.setattr("services.mail.discover.public_ips", lambda host: [])
    own = GMAIL.replace("imap.gmail.com", "imap.acme.example")
    client, seen = network({"autoconfig.acme.example/mail/config-v1.1.xml": own, "autoconfig.thunderbird.net/v1.1/acme.example": GMAIL})
    assert discover("alerts@acme.example", client, no_probe).host == "imap.gmail.com"
    assert not any("autoconfig.acme.example" in u for u in seen)


def test_guess_then_nothing():
    client, _ = network({})
    s = discover("alerts@tiny.example", client, lambda h, p: h == "mail.tiny.example")
    assert (s.host, s.source) == ("mail.tiny.example", "guess")
    assert discover("alerts@tiny.example", client, no_probe) is None


def test_config_with_entities_or_plain_imap_is_refused():
    bomb = '<!DOCTYPE x [<!ENTITY a "aaaa">]>' + GMAIL
    client, _ = network({"autoconfig.thunderbird.net/v1.1/bad.example": bomb})
    assert discover("a@bad.example", client, no_probe) is None
    plain = GMAIL.replace("<socketType>SSL</socketType>", "<socketType>plain</socketType>")
    client, _ = network({"autoconfig.thunderbird.net/v1.1/bad.example": plain})
    assert discover("a@bad.example", client, no_probe) is None


def test_private_and_loopback_hosts_are_never_contacted():
    from services.mail.discover import public_ips
    from services.mail.sync import MailError, open_mailbox

    assert public_ips("localhost") == []
    assert public_ips("127.0.0.1") == [] and public_ips("10.0.0.5") == [] and public_ips("169.254.169.254") == []
    for host, port in (("localhost", 993), ("127.0.0.1", 993), ("imap.gmail.com", 25)):
        try:
            open_mailbox(host, port, "u", "p")
        except MailError as e:
            assert e.code == "unreachable"  # one answer for every failure: no port-scan signal
        else:
            raise AssertionError(f"{host}:{port} was contacted")
