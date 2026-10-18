"""Tests for the outbound LLM endpoint guard (SSRF defence)."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.agent.url_guard import BlockedEndpointError, validate_llm_endpoint

client = TestClient(app)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "ftp://example.com/model",
        "https://user:pass@api.example.com/v1",
        "",
    ],
)
def test_dangerous_endpoints_are_rejected(url):
    with pytest.raises(BlockedEndpointError):
        validate_llm_endpoint(url)


def test_loopback_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", raising=False)
    with pytest.raises(BlockedEndpointError):
        validate_llm_endpoint("http://127.0.0.1:1234/v1")

    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "1")
    assert validate_llm_endpoint("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"


def test_private_ranges_require_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("LLM_ALLOW_PRIVATE_ENDPOINTS", raising=False)
    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "1")
    with pytest.raises(BlockedEndpointError):
        validate_llm_endpoint("http://10.0.0.7:8000/v1")

    monkeypatch.setenv("LLM_ALLOW_PRIVATE_ENDPOINTS", "1")
    assert validate_llm_endpoint("http://10.0.0.7:8000/v1")


def test_metadata_endpoint_stays_blocked_even_with_private_opt_in(monkeypatch):
    monkeypatch.setenv("LLM_ALLOW_PRIVATE_ENDPOINTS", "1")
    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "1")
    with pytest.raises(BlockedEndpointError):
        validate_llm_endpoint("http://169.254.169.254/latest/meta-data/")


def test_public_endpoint_is_allowed(monkeypatch):
    monkeypatch.delenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", raising=False)
    assert validate_llm_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_test_connection_blocks_internal_targets(monkeypatch):
    monkeypatch.setenv("LLM_ALLOW_PRIVATE_ENDPOINTS", "0")
    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "0")

    response = client.post(
        "/api/v1/agent/test-connection",
        json={
            "provider": "custom",
            "base_url": "http://169.254.169.254/latest",
            "api_key": "probe",
            "model_name": "probe",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "blocked" in body["message"].lower()


def test_fetch_models_blocks_internal_targets(monkeypatch):
    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "0")
    response = client.post(
        "/api/v1/agent/fetch-models",
        json={"provider": "custom", "base_url": "http://127.0.0.1:9", "api_key": "probe"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "blocked" in response.json()["message"].lower()
