"""
Outbound endpoint validation for client-supplied LLM base URLs.

The AI provider settings let a caller point the backend at any OpenAI-compatible endpoint.
Without a guard that turns the server into an SSRF proxy: it can be aimed at loopback services,
RFC 1918 hosts, or cloud metadata endpoints, and the response body can be reflected back.

Policy (all overridable through environment variables so self-hosted local models still work):

- Only http/https URLs with a hostname are allowed.
- URLs with embedded credentials are rejected.
- Link-local addresses (including 169.254.169.254 metadata), multicast, reserved and
  unspecified addresses are always rejected.
- Loopback and private-range hosts are rejected unless explicitly opted in with
  LLM_ALLOW_LOOPBACK_ENDPOINTS=1 / LLM_ALLOW_PRIVATE_ENDPOINTS=1.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable
from urllib.parse import urlsplit

BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "instance-data",
        "instance-data.ec2.internal",
    }
)


class BlockedEndpointError(ValueError):
    """Raised when a client-supplied endpoint fails the outbound connection policy."""


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ip_is_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_loopback: bool,
    allow_private: bool,
) -> bool:
    if ip.is_loopback:
        return not allow_loopback
    if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.is_private:
        return not allow_private
    return False


def _resolve_addresses(hostname: str, port: int) -> Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        # Unresolvable hosts cannot reach anything; the HTTP client will fail on its own.
        return []
    addresses = []
    for info in infos:
        sockaddr = info[4]
        try:
            addresses.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    return addresses


def validate_llm_endpoint(
    url: str,
    *,
    allow_loopback: bool | None = None,
    allow_private: bool | None = None,
) -> str:
    """Returns the URL unchanged when it passes the policy, otherwise raises BlockedEndpointError."""
    raw = (url or "").strip()
    if not raw:
        raise BlockedEndpointError("Endpoint URL is empty")

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise BlockedEndpointError(f"Unsupported URL scheme '{parsed.scheme or '(none)'}': use http or https")
    if not parsed.hostname:
        raise BlockedEndpointError("Endpoint URL must include a hostname")
    if parsed.username or parsed.password:
        raise BlockedEndpointError("Endpoint URL must not embed credentials")

    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTNAMES:
        raise BlockedEndpointError(f"Endpoint host '{hostname}' is blocked by the outbound connection policy")

    resolved_loopback = _env_flag("LLM_ALLOW_LOOPBACK_ENDPOINTS") if allow_loopback is None else allow_loopback
    resolved_private = _env_flag("LLM_ALLOW_PRIVATE_ENDPOINTS") if allow_private is None else allow_private

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    for address in _resolve_addresses(hostname, port):
        if _ip_is_blocked(address, allow_loopback=resolved_loopback, allow_private=resolved_private):
            raise BlockedEndpointError(
                f"Endpoint host '{hostname}' resolves to blocked address {address}. "
                "Set LLM_ALLOW_LOOPBACK_ENDPOINTS=1 or LLM_ALLOW_PRIVATE_ENDPOINTS=1 for a trusted self-hosted model."
            )

    return raw
