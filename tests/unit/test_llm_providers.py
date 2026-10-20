"""Comprehensive unit tests for all LLM providers in services/agent/llm_bridge.py."""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from services.agent.llm_bridge import (
    _query_cloud_provider,
    _resolve_endpoint,
    fetch_remote_models,
    test_llm_connection as execute_test_llm_connection,
)
from services.agent.name_masking import NameMasker
from services.agent.schema import FetchModelsRequest, LLMConfig, TestConnectionRequest

TestConnectionRequest.__test__ = False


# 1. Endpoint Resolution Tests
def test_resolve_endpoint_gemini():
    # Default URL
    url, model = _resolve_endpoint("gemini", None, "gemini-2.0-flash")
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    assert model == "gemini-2.0-flash"

    # Base URL missing /v1beta
    url2, _ = _resolve_endpoint("gemini", "https://generativelanguage.googleapis.com", "gemini-1.5-pro")
    assert url2 == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"


def test_resolve_endpoint_anthropic():
    # Default
    url, model = _resolve_endpoint("anthropic", None, "claude-3-5-sonnet-20241022")
    assert url == "https://api.anthropic.com/v1/messages"
    assert model == "claude-3-5-sonnet-20241022"

    # With base without /messages
    url2, _ = _resolve_endpoint("anthropic", "https://api.anthropic.com", "claude-3-5-haiku-20241022")
    assert url2 == "https://api.anthropic.com/v1/messages"


def test_resolve_endpoint_openai_deepseek_groq():
    url_oa, _ = _resolve_endpoint("openai", None, "gpt-4o-mini")
    assert url_oa == "https://api.openai.com/v1/chat/completions"

    url_ds, _ = _resolve_endpoint("deepseek", None, "deepseek-chat")
    assert url_ds == "https://api.deepseek.com/v1/chat/completions"

    url_groq, _ = _resolve_endpoint("groq", None, "llama-3.3-70b-versatile")
    assert url_groq == "https://api.groq.com/openai/v1/chat/completions"


def test_resolve_endpoint_custom_and_ollama(monkeypatch):
    url_ol, _ = _resolve_endpoint("ollama", "http://localhost:11434", "llama3.2")
    assert url_ol == "http://localhost:11434/v1/chat/completions"

    url_cu, _ = _resolve_endpoint("custom", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct")
    assert url_cu == "https://openrouter.ai/api/v1/chat/completions"

    monkeypatch.setenv("LLM_ALLOW_LOOPBACK_ENDPOINTS", "1")
    url_lm, _ = _resolve_endpoint("custom", "http://localhost:1234", "mistral-7b")
    assert url_lm == "http://localhost:1234/v1/chat/completions"


# 2. Connection Test Probe Tests
def test_connection_cloud_requires_api_key():
    for p in ["gemini", "anthropic", "openai", "deepseek", "groq"]:
        res = execute_test_llm_connection(TestConnectionRequest(provider=p))
        assert res.success is False
        assert "API key is required" in res.message


def test_connection_custom_requires_base_url():
    res = execute_test_llm_connection(TestConnectionRequest(provider="custom"))
    assert res.success is False
    assert "Base URL is required" in res.message


def test_connection_probes_success():
    mock_200 = MagicMock()
    mock_200.status_code = 200

    with patch.object(httpx.Client, "post", return_value=mock_200):
        # Gemini
        res_g = execute_test_llm_connection(TestConnectionRequest(provider="gemini", api_key="k", model_name="gemini-2.0-flash"))
        assert res_g.success is True

        # Anthropic
        res_a = execute_test_llm_connection(TestConnectionRequest(provider="anthropic", api_key="k", model_name="claude-3-5-sonnet-20241022"))
        assert res_a.success is True

        # OpenAI, DeepSeek, Groq, Custom
        for p in ["openai", "deepseek", "groq", "custom"]:
            res = execute_test_llm_connection(TestConnectionRequest(provider=p, api_key="k", base_url="https://example.com/v1" if p == "custom" else None))
            assert res.success is True


# 3. Payload and Response Parsing Tests
def test_query_cloud_provider_gemini_parsing():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Gemini Financial Response"}]}}]
    }
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        ans = _query_cloud_provider(
            "gemini",
            "What is our cash runway?",
            "System prompt",
            LLMConfig(provider="gemini", api_key="fake-key", model_name="gemini-2.0-flash"),
            [],
            NameMasker(),
        )
        assert ans == "Gemini Financial Response"


def test_query_cloud_provider_anthropic_parsing():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": "Claude Financial Analysis"}]
    }
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        ans = _query_cloud_provider(
            "anthropic",
            "What is our cash runway?",
            "System prompt",
            LLMConfig(provider="anthropic", api_key="fake-key", model_name="claude-3-5-sonnet-20241022"),
            [],
            NameMasker(),
        )
        assert ans == "Claude Financial Analysis"


def test_query_cloud_provider_openai_and_custom_parsing():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "OpenAI / Custom Response"}}]
    }
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        ans = _query_cloud_provider(
            "custom",
            "What is our cash runway?",
            "System prompt",
            LLMConfig(provider="custom", api_key="fake-key", base_url="https://custom.test/v1", model_name="mistral-7b"),
            [],
            NameMasker(),
        )
        assert ans == "OpenAI / Custom Response"


def test_query_cloud_provider_reasoning_models_parsing():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # DeepSeek-R1 / o1 style where content might be in reasoning_content
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "Chain-of-thought conclusion."}}]
    }
    with patch.object(httpx.Client, "post", return_value=mock_resp):
        ans = _query_cloud_provider(
            "deepseek",
            "What is our cash runway?",
            "System prompt",
            LLMConfig(provider="deepseek", api_key="fake-key", model_name="deepseek-reasoner"),
            [],
            NameMasker(),
        )
        assert ans == "Chain-of-thought conclusion."
