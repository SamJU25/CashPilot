"""Finds a mailbox's IMAP settings from its address, the way Thunderbird does.

Order: the provider's own autoconfig file, Mozilla's ISP database (ISPDB), the ISPDB entry for the
domain's mail host (MX, which covers company domains on Google Workspace or Microsoft 365), then a
guess at imap.<domain> / mail.<domain>. Only HTTPS sources are used: a config served over plain HTTP
could be swapped in transit to point the password at someone else's server. Only the domain leaves
this computer during discovery, never the full address or the password.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Callable, Optional

import httpx

ISPDB = "https://autoconfig.thunderbird.net/v1.1/{domain}"
DOH = "https://cloudflare-dns.com/dns-query"
MAX_BYTES = 64_000
TIMEOUT_S = 6.0
_DOMAIN = re.compile(r"^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,6}$")


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    username: str
    source: str  # provider | ispdb | mx | guess
    name: str  # what to call the provider in the app
    # Only OAuth2 is offered: an app password will not work and CashPilot cannot sign in yet.
    oauth_only: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


# What CashPilot knows about a mail host beyond its settings.
def stamps_auth_results(host: str) -> bool:
    """Whether this host writes its own sender-check header on arriving mail (see parser.verify_sender)."""
    return (
        host in ("imap.gmail.com", "outlook.office365.com", "imap-mail.outlook.com", "imap.fastmail.com", "imap.mail.yahoo.com", "imap.mail.me.com", "imap.zoho.com")
        or host.endswith((".gmail.com", ".office365.com", ".outlook.com", ".fastmail.com", ".yahoo.com", ".icloud.com"))
    )


def secret_kind(host: str) -> str:
    if host.endswith((".qq.com", ".163.com", ".126.com", ".yeah.net", ".sina.com", ".aliyun.com")):
        return "auth_code"
    if host in ("imap.gmail.com", "imap.mail.me.com", "imap.mail.yahoo.com"):
        return "app_password"
    return "password"


def needs_id_command(host: str) -> bool:
    """NetEase refuses SELECT from clients that have not identified themselves ("Unsafe Login")."""
    return host.endswith((".163.com", ".126.com", ".yeah.net"))


def _parse(xml: str, address: str, source: str) -> Optional[Settings]:
    # Refuse entity tricks outright; a real config file never needs a DTD.
    if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    provider = root.find("emailProvider")
    if provider is None:
        return None
    name = (provider.findtext("displayShortName") or provider.findtext("displayName") or "").strip()
    local, _, domain = address.partition("@")
    for server in provider.findall("incomingServer[@type='imap']"):
        # TLS from the first byte only; STARTTLS and plain connections are not used.
        if (server.findtext("socketType") or "").upper() != "SSL":
            continue
        host = (server.findtext("hostname") or "").strip().lower().replace("%emaildomain%", domain)
        try:
            port = int(server.findtext("port") or 993)
            if port != 993:
                continue
        except ValueError:
            continue
        auths = {(a.text or "").strip() for a in server.findall("authentication")}
        username = (server.findtext("username") or "%EMAILADDRESS%").replace("%EMAILADDRESS%", address).replace("%EMAILLOCALPART%", local).replace("%EMAILDOMAIN%", domain)
        if not _DOMAIN.match(host):
            continue
        password_ok = bool(auths & {"password-cleartext", "plain", "password-encrypted", "secure"}) or not auths
        return Settings(host, port, username, source, name or host, oauth_only=not password_ok)
    return None


def _get(client: httpx.Client, url: str, check_host: bool = False, **params) -> Optional[str]:
    # shortcut: the check and httpx resolve separately (rebinding window); fine for a read-only GET of a small XML file.
    if check_host and not public_ips(httpx.URL(url).host):
        return None
    try:
        r = client.get(url, params=params or None)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) > MAX_BYTES:
        return None
    return r.text


def _mx_hosts(client: httpx.Client, domain: str) -> list[str]:
    try:
        r = client.get(DOH, params={"name": domain, "type": "MX"}, headers={"accept": "application/dns-json"})
        answers = r.json().get("Answer", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return []
    records = [str(a.get("data", "")).split() for a in answers]
    records = [p for p in records if len(p) == 2 and p[0].isdigit()]
    return [host.rstrip(".").lower() for _, host in sorted(records, key=lambda p: int(p[0]))]


def public_ips(host: str) -> list[str]:
    """The host's addresses when every one is on the public internet, else []. Mail settings come from
    the owner or from a domain's own DNS, so a name pointing at loopback, a private network, link-local
    or cloud metadata ranges must not let CashPilot probe them."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    ips = list(dict.fromkeys(i[4][0] for i in infos))
    return ips if ips and all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in ips) else []


def _tls_answers(host: str, port: int = 993) -> bool:
    """A mail server is there and its certificate is valid for that name."""
    ips = public_ips(host)
    if not ips:
        return False
    try:
        with socket.create_connection((ips[0], port), timeout=3) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                return True
    except (OSError, ssl.SSLError):
        return False


def discover(address: str, client: Optional[httpx.Client] = None, probe: Callable[[str, int], bool] = _tls_answers) -> Optional[Settings]:
    domain = address.rpartition("@")[2].lower()
    if not _DOMAIN.match(domain):
        return None
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)
    try:
        for url, extra in (
            (f"https://autoconfig.{domain}/mail/config-v1.1.xml", {"emailaddress": address}),
            (f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml", {}),
        ):
            if (xml := _get(client, url, check_host=True, **extra)) and (s := _parse(xml, address, "provider")):
                return s
        if (xml := _get(client, ISPDB.format(domain=domain))) and (s := _parse(xml, address, "ispdb")):
            return s
        for mx in _mx_hosts(client, domain)[:2]:
            labels = mx.split(".")
            # mx1.hoster.com → hoster.com; mx.hoster.com.cn → hoster.com.cn
            for base in dict.fromkeys([".".join(labels[-2:]), ".".join(labels[-3:])]):
                if base != domain and _DOMAIN.match(base) and (xml := _get(client, ISPDB.format(domain=base))) and (s := _parse(xml, address, "mx")):
                    return s
        for host in (f"imap.{domain}", f"mail.{domain}"):
            if probe(host, 993):
                return Settings(host, 993, address, "guess", domain)
        return None
    finally:
        if own:
            client.close()
