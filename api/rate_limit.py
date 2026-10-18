"""
Token-bucket rate limiting for the public API.

Kept as a pure ASGI middleware (not BaseHTTPMiddleware) so it adds no body-wrapping overhead
and works for the JSON routes only. Health probes are exempt so container healthchecks never
consume a tenant's budget.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable

DEFAULT_LIMIT_PER_MINUTE = 60
EXEMPT_PATHS = frozenset({"/health", "/api/v1/health", "/"})


def _configured_limit() -> int:
    raw = os.getenv("RATE_LIMIT_PER_MINUTE", str(DEFAULT_LIMIT_PER_MINUTE)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_LIMIT_PER_MINUTE


def _trusted_proxy_hops() -> int:
    """Number of reverse proxies that append to X-Forwarded-For (0 disables the header)."""
    raw = os.getenv("TRUSTED_PROXY_HOPS", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _forwarded_client(scope: dict, hops: int) -> str | None:
    """Returns the client IP from X-Forwarded-For, trusting only the rightmost `hops` entries.

    Each trusted proxy appends the address it received the request from, so with N trusted
    proxies the client is the Nth entry from the right. A caller can send arbitrary leftmost
    values, which are ignored.
    """
    if hops <= 0:
        return None
    raw = None
    for name, value in scope.get("headers") or []:
        if name.lower() == b"x-forwarded-for":
            raw = value.decode("latin-1")
            break
    if not raw:
        return None
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        return None
    index = max(0, len(parts) - hops)
    return parts[index]


class TokenBucketRateLimiter:
    """Per-client-IP token bucket. A limit of 0 disables limiting (used by the test suite)."""

    def __init__(
        self,
        app: Callable[..., Any],
        limit_per_minute: int | None = None,
        trusted_proxy_hops: int | None = None,
    ) -> None:
        self.app = app
        self.limit_per_minute = _configured_limit() if limit_per_minute is None else max(0, limit_per_minute)
        self.trusted_proxy_hops = (
            _trusted_proxy_hops() if trusted_proxy_hops is None else max(0, trusted_proxy_hops)
        )
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _consume(self, client_key: str) -> bool:
        limit = self.limit_per_minute
        if limit <= 0:
            return True
        now = time.monotonic()
        refill_rate = limit / 60.0
        with self._lock:
            if len(self._buckets) > 2048:
                # Drop buckets that have been full again for a while; they carry no state.
                idle_cutoff = now - 600.0
                for stale_key in [k for k, (_, seen) in self._buckets.items() if seen < idle_cutoff]:
                    self._buckets.pop(stale_key, None)
                if len(self._buckets) > 2048:
                    overflow = len(self._buckets) - 2048
                    oldest_keys = sorted(self._buckets.keys(), key=lambda k: self._buckets[k][1])[:overflow]
                    for ok in oldest_keys:
                        self._buckets.pop(ok, None)
            tokens, last_seen = self._buckets.get(client_key, (float(limit), now))
            tokens = min(float(limit), tokens + (now - last_seen) * refill_rate)
            if tokens < 1.0:
                self._buckets[client_key] = (tokens, now)
                return False
            self._buckets[client_key] = (tokens - 1.0, now)
            return True

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or self.limit_per_minute <= 0:
            await self.app(scope, receive, send)
            return

        if scope.get("path") in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        client_key = _forwarded_client(scope, self.trusted_proxy_hops)
        if not client_key:
            client = scope.get("client") or ("unknown", 0)
            client_key = str(client[0])
        if self._consume(client_key):
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {"error": {"code": "RATE_LIMITED", "message": "Too many requests: retry after 60 seconds."}}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"retry-after", b"60"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
