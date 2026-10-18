"""Tests for the per-IP token-bucket rate limiter middleware."""

from fastapi.testclient import TestClient

from api.rate_limit import TokenBucketRateLimiter


async def _echo_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


def test_requests_beyond_the_bucket_are_throttled():
    client = TestClient(TokenBucketRateLimiter(_echo_app, limit_per_minute=2))

    assert client.get("/api/v1/private").status_code == 200
    assert client.get("/api/v1/private").status_code == 200
    throttled = client.get("/api/v1/private")
    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "RATE_LIMITED"
    assert throttled.headers["retry-after"] == "60"


def test_health_probes_are_exempt():
    client = TestClient(TokenBucketRateLimiter(_echo_app, limit_per_minute=1))
    for _ in range(4):
        assert client.get("/api/v1/health").status_code == 200


def test_zero_limit_disables_limiting():
    client = TestClient(TokenBucketRateLimiter(_echo_app, limit_per_minute=0))
    for _ in range(10):
        assert client.get("/api/v1/private").status_code == 200


def test_forwarded_for_distinguishes_clients_behind_a_trusted_proxy():
    client = TestClient(
        TokenBucketRateLimiter(_echo_app, limit_per_minute=1, trusted_proxy_hops=1)
    )

    assert client.get("/api/v1/private", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 200
    assert client.get("/api/v1/private", headers={"X-Forwarded-For": "203.0.113.6"}).status_code == 200
    assert client.get("/api/v1/private", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 429


def test_spoofed_leftmost_forwarded_values_share_one_bucket():
    client = TestClient(
        TokenBucketRateLimiter(_echo_app, limit_per_minute=1, trusted_proxy_hops=1)
    )

    assert client.get(
        "/api/v1/private", headers={"X-Forwarded-For": "198.51.100.1, 203.0.113.9"}
    ).status_code == 200
    # Only the rightmost non-proxy entry is trusted; the leftmost value is caller-controlled.
    assert client.get(
        "/api/v1/private", headers={"X-Forwarded-For": "198.51.100.2, 203.0.113.9"}
    ).status_code == 429


def test_forwarded_for_is_ignored_without_trusted_hops():
    client = TestClient(
        TokenBucketRateLimiter(_echo_app, limit_per_minute=1, trusted_proxy_hops=0)
    )

    assert client.get("/api/v1/private", headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 200
    assert client.get("/api/v1/private", headers={"X-Forwarded-For": "203.0.113.6"}).status_code == 429
