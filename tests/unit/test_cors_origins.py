"""Without ALLOWED_ORIGINS, any local dev port may call the API; other sites may not."""

import os

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.mark.skipif(bool(os.getenv("ALLOWED_ORIGINS")), reason="explicit origin list configured")
@pytest.mark.parametrize("origin,allowed", [
    ("http://localhost:3001", True),
    ("http://127.0.0.1:3000", True),
    ("https://evil.example", False),
    ("http://localhost.evil.example", False),
])
def test_preflight_origin(origin, allowed):
    res = client.options("/api/v1/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert (res.headers.get("access-control-allow-origin") == origin) is allowed
