"""Unit tests for the Ollama integration in services/agent/llm_bridge.py."""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from services.agent.llm_bridge import (
    _resolve_endpoint,
    fetch_remote_models,
    test_llm_connection as execute_test_llm_connection,
)
from services.agent.schema import FetchModelsRequest, TestConnectionRequest

TestConnectionRequest.__test__ = False


def test_ollama_resolve_endpoint_default():
    url, model = _resolve_endpoint("ollama", None, None)
    assert url == "http://localhost:11434/v1/chat/completions"
    assert model == "llama3.2"


def test_ollama_resolve_endpoint_custom_base():
    url, model = _resolve_endpoint("ollama", "http://localhost:11434", "qwen2.5")
    assert url == "http://localhost:11434/v1/chat/completions"
    assert model == "qwen2.5"


def test_ollama_test_connection_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        res = execute_test_llm_connection(TestConnectionRequest(provider="ollama", model_name="llama3.2"))
        assert res.success is True
        assert res.provider == "ollama"
        assert res.model_name == "llama3.2"
        assert "verified successfully" in res.message


def test_ollama_test_connection_model_not_found_404():
    mock_404 = MagicMock()
    mock_404.status_code = 404
    with patch.object(httpx.Client, "post", return_value=mock_404):
        res = execute_test_llm_connection(TestConnectionRequest(provider="ollama", model_name="missing-model"))
        assert res.success is False
        assert res.provider == "ollama"
        assert "not found in Ollama" in res.message
        assert "ollama pull missing-model" in res.message


def test_ollama_test_connection_unreachable():
    with patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("Connection refused")):
        res = execute_test_llm_connection(TestConnectionRequest(provider="ollama", model_name="llama3.2"))
        assert res.success is False
        assert "Unable to reach Ollama" in res.message


def test_ollama_fetch_remote_models_via_api_tags():
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {
        "models": [
            {"name": "llama3.2:latest", "model": "llama3.2:latest"},
            {"name": "qwen2.5:3b", "model": "qwen2.5:3b"},
        ]
    }
    with patch.object(httpx.Client, "get", return_value=mock_tags):
        res = fetch_remote_models(FetchModelsRequest(provider="ollama"))
        assert res.success is True
        assert len(res.models) == 2
        assert res.models[0].id == "llama3.2:latest"
        assert res.models[1].id == "qwen2.5:3b"
