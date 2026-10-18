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


class TokenBucketRateLimiter:
    """Per-client-IP token bucket. A limit of 0 disables limiting (used by the test suite)."""

    def __init__(self, app: Callable[..., Any], limit_per_minute: int | None = None) -> None:
        self.app = app
        self.limit_per_minute = _configured_limit() if limit_per_minute is None else max(0, limit_per_minute)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _consume(self, client_key: str) -> bool:
        limit = self.limit_per_minute
        if limit <= 0:
            return True
        now = time.monotonic()
        refill_rate = limit / 60.0
        with self._lock:
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
