"""Universal LLM Bridge for the Autonomous SME Finance Copilot.

Supports:
1. Native Gemini API (Google AI)
2. Native Anthropic Messages API
3. Native OpenAI Chat Completions API
4. DeepSeek and Groq (OpenAI-compatible)
5. Custom OpenAI-compatible endpoints (Base URL + Key + Model)
6. Offline Local Deterministic fallback (0 external keys)
7. Pre-flight PII redaction and deterministic calculation grounding
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from services.agent.schema import (
    FetchModelsRequest,
    FetchModelsResponse,
    LLMConfig,
    ModelItem,
    TestConnectionRequest,
    TestConnectionResponse,
)
from services.agent.name_masking import NameMasker
from services.agent.url_guard import BlockedEndpointError, validate_llm_endpoint

# Pre-compiled PII Sanitization Patterns
RE_ACCOUNT = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{9,18}\b")
RE_TAX_ID = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{2}-\d{7}\b")  # SSN and SME EIN
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
RE_PHONE = re.compile(r"(?:\+?1[-.\s]*)?(?:\(\d{3}\)|\b\d{3}\b)[-.\s]*\d{3}[-.\s]*\d{4}\b")
RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b")
RE_API_KEY = re.compile(
    r"\b(?:sk-ant-[a-zA-Z0-9_\-]{20,}|sk-[a-zA-Z0-9_\-]{20,}|AIzaSy[a-zA-Z0-9_\-]{30,}|gsk_[a-zA-Z0-9_\-]{20,})\b"
    r"|(?:api[_-]?key|secret[_-]?token|bearer[_-]?token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
    re.IGNORECASE,
)


def mask_pii(text: str) -> str:
    """Sanitizes sensitive identifiers before external transmission."""
    if not text:
        return text
    scrubbed = RE_ACCOUNT.sub("[REDACTED_ACCOUNT]", text)
    scrubbed = RE_TAX_ID.sub("[REDACTED_TAX_ID]", scrubbed)
    scrubbed = RE_EMAIL.sub("[REDACTED_EMAIL]", scrubbed)
    scrubbed = RE_PHONE.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = RE_IBAN.sub("[REDACTED_IBAN]", scrubbed)
    scrubbed = RE_API_KEY.sub("[REDACTED_API_KEY]", scrubbed)
    return scrubbed


def _extract_history_turn(h: Any) -> tuple[str, str]:
    """Safely extracts role and text from either Pydantic model or dictionary turn."""
    if isinstance(h, dict):
        return h.get("role", "user"), h.get("text", "")
    return getattr(h, "role", "user"), getattr(h, "text", "")



def _get_local_default_model_id() -> str:
    try:
        from services.agent.local_transformers import get_default_model_id
        return get_default_model_id()
    except Exception:
        return "default"


def _get_local_default_model_name() -> str:
    try:
        from services.agent.local_transformers import get_default_model_name
        return f"{get_default_model_name()} (Local Flagship)"
    except Exception:
        return "Local Flagship Model"


PROVIDER_DEFAULTS = {
    "offline": {
        "model": _get_local_default_model_id(),
        "url": "local",
    },
    "local": {
        "model": _get_local_default_model_id(),
        "url": "local",
    },
    "local_native": {
        "model": _get_local_default_model_id(),
        "url": "local",
    },
    "gemini": {
        "model": "gemini-2.0-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta",
    },
    "anthropic": {
        "model": "claude-3-5-sonnet-20241022",
        "url": "https://api.anthropic.com/v1/messages",
    },
    "openai": {
        "model": "gpt-4o-mini",
        "url": "https://api.openai.com/v1/chat/completions",
    },
    "deepseek": {
        "model": "deepseek-chat",
        "url": "https://api.deepseek.com/v1/chat/completions",
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
    "ollama": {
        "model": "llama3.2",
        "url": "http://localhost:11434/v1/chat/completions",
    },
}


def _resolve_endpoint(provider: str, base_url: Optional[str], model: Optional[str]) -> Tuple[str, str]:
    """Resolves target endpoint URL and model identifier for a given provider."""
    p_lower = (provider or "offline").lower()

    defaults = PROVIDER_DEFAULTS.get(p_lower, {})
    model_name = model or defaults.get("model", "custom-model")
    target_check = (base_url or defaults.get("url", "")).lower()

    allow_loopback = None
    if p_lower == "ollama" or ("11434" in target_check and ("localhost" in target_check or "127.0.0.1" in target_check)):
        allow_loopback = True

    # Caller-supplied endpoints are untrusted: validate before any outbound request.
    if base_url and base_url.strip():
        validate_llm_endpoint(base_url, allow_loopback=allow_loopback)

    if p_lower == "custom":
        raw_url = (base_url or "").rstrip("/")
        if not raw_url.endswith("/chat/completions"):
            if not raw_url.endswith("/v1"):
                raw_url = f"{raw_url}/v1/chat/completions"
            else:
                raw_url = f"{raw_url}/chat/completions"
        return raw_url, model_name

    if p_lower == "ollama":
        raw_url = (base_url or defaults.get("url", "http://localhost:11434/v1/chat/completions")).rstrip("/")
        if not raw_url.endswith("/chat/completions"):
            if not raw_url.endswith("/v1"):
                raw_url = f"{raw_url}/v1/chat/completions"
            else:
                raw_url = f"{raw_url}/chat/completions"
        return raw_url, model_name

    if p_lower == "gemini":
        base = (base_url or defaults.get("url", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")
        if not (base.endswith("/v1beta") or base.endswith("/v1")):
            base = f"{base}/v1beta"
        return f"{base}/models/{model_name}:generateContent", model_name

    if p_lower in ["openai", "deepseek", "groq"]:
        if base_url:
            raw_url = base_url.rstrip("/")
            if not raw_url.endswith("/chat/completions"):
                if not raw_url.endswith("/v1"):
                    raw_url = f"{raw_url}/v1/chat/completions"
                else:
                    raw_url = f"{raw_url}/chat/completions"
            return raw_url, model_name
        return defaults.get("url", ""), model_name

    if p_lower == "anthropic":
        base = (base_url or defaults.get("url", "https://api.anthropic.com/v1/messages")).rstrip("/")
        if not base.endswith("/messages"):
            if not base.endswith("/v1"):
                base = f"{base}/v1/messages"
            else:
                base = f"{base}/messages"
        return base, model_name

    if p_lower in ["offline", "local", "local_native"]:
        from services.agent.local_transformers import resolve_canonical_model_name, get_default_model_id
        return "local", resolve_canonical_model_name(model or get_default_model_id())

    from services.agent.local_transformers import get_default_model_id
    return "local", get_default_model_id()


def test_llm_connection(req: TestConnectionRequest) -> TestConnectionResponse:
    """Sends a lightweight verification probe to the target LLM provider."""
    provider = (req.provider or "offline").lower()

    if provider in ["local", "local_native", "offline"]:
        from services.agent.local_transformers import (
            LocalTransformersEngine,
            get_default_model_id,
            resolve_canonical_model_name,
        )
        engine = LocalTransformersEngine.get_instance()
        target_model = resolve_canonical_model_name(req.model_name or get_default_model_id())

        def local_result(success: bool, message: str) -> TestConnectionResponse:
            return TestConnectionResponse(success=success, message=message, provider=provider, model_name=target_model, latency_ms=0)

        if engine.is_available(target_model):
            # A file on disk is not enough: without the runtime every reply falls back to templates.
            if not llama_cpp_installed():
                return local_result(False, "The model is installed, but the llama.cpp runtime is not. Run 'pip install llama-cpp-python', then restart the backend.")
            return local_result(True, f"Local AI model ready: '{target_model}' is installed and runs offline with llama.cpp.")

        from services.agent.local_transformers import SUPPORTED_LOCAL_MODELS
        # Hidden entries are legacy transformers weights in the HF cache that llama.cpp cannot load.
        if not any(engine.is_available(m) for m, meta in SUPPORTED_LOCAL_MODELS.items() if not meta.get("hidden")):
            return local_result(False, "No local model is installed yet. Use Browse models to download one from Hugging Face, or import a .gguf file.")
        return local_result(False, f"'{target_model}' is not in the models folder. Select one of the installed models above, or download it with Browse models.")

    api_key = (req.api_key or "").strip()
    base_url = (req.base_url or "").strip()

    # Validate mandatory fields
    if provider in ["gemini", "anthropic", "openai", "deepseek", "groq"] and not api_key:
        return TestConnectionResponse(
            success=False,
            message=f"API key is required for provider '{provider}'.",
            provider=provider,
            latency_ms=None,
        )

    if provider == "custom" and not base_url:
        return TestConnectionResponse(
            success=False,
            message="Base URL is required for custom OpenAI-compatible endpoint.",
            provider=provider,
            latency_ms=None,
        )

    try:
        endpoint, model = _resolve_endpoint(provider, base_url, req.model_name)
    except BlockedEndpointError as exc:
        return TestConnectionResponse(
            success=False,
            message=f"Endpoint blocked by the outbound connection policy: {exc}",
            provider=provider,
            model_name=req.model_name or "custom-model",
            latency_ms=None,
        )
    probe_prompt = "Hello. Respond with the single word 'READY'."
    start_time = time.perf_counter()

    try:
        with httpx.Client(timeout=6.0) as client:
            if provider == "gemini":
                url = f"{endpoint}?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": probe_prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 10},
                }
                res = client.post(url, json=payload)

            elif provider == "anthropic":
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": probe_prompt}],
                }
                res = client.post(endpoint, headers=headers, json=payload)

            else:  # OpenAI, DeepSeek, Groq, Custom
                headers = {"content-type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": probe_prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1,
                }
                res = client.post(endpoint, headers=headers, json=payload)

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if res.status_code == 200:
                return TestConnectionResponse(
                    success=True,
                    message=f"Connection verified successfully with {provider} ({model}).",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            elif res.status_code == 401:
                return TestConnectionResponse(
                    success=False,
                    message=f"Authentication failed (HTTP 401): Check your API key for {provider}.",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            elif res.status_code == 404:
                msg = f"Endpoint or model not found (HTTP 404): Check model name '{model}' or Base URL."
                if provider == "ollama":
                    msg = f"Model '{model}' not found in Ollama (HTTP 404). Run 'ollama pull {model}' in terminal first."
                return TestConnectionResponse(
                    success=False,
                    message=msg,
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )
            else:
                # Never reflect the upstream body: it can leak internal service responses back
                # to whoever supplied the endpoint URL.
                return TestConnectionResponse(
                    success=False,
                    message=f"Provider returned error HTTP {res.status_code}.",
                    provider=provider,
                    model_name=model,
                    latency_ms=latency_ms,
                )

    except httpx.ConnectError:
        msg = f"Unable to connect to host at '{endpoint}'. Verify your network or local server status."
        if provider == "ollama":
            msg = "Unable to reach Ollama at http://localhost:11434. Ensure the Ollama daemon is running ('ollama serve' in terminal)."
        return TestConnectionResponse(
            success=False,
            message=msg,
            provider=provider,
            model_name=model,
        )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            success=False,
            message="Connection timed out after 6 seconds.",
            provider=provider,
            model_name=model,
        )
    except Exception as exc:
        return TestConnectionResponse(
            success=False,
            message=f"Connection probe failed: {str(exc)}",
            provider=provider,
            model_name=model,
        )


def query_external_llm(
    prompt: str,
    system_instruction: str,
    config: Optional[LLMConfig],
    history: Optional[List[Any]] = None,
) -> Optional[str]:
    """Queries configured external or local LLM with PII redaction, multi-turn history, and graceful fallback."""
    if not config or (config.provider or "offline").lower() == "offline":
        return None

    provider = config.provider.lower()
    sanitized_prompt = mask_pii(prompt)

    if provider in ["local", "local_native"]:
        from services.agent.local_transformers import LocalTransformersEngine
        engine = LocalTransformersEngine.get_instance()
        return engine.generate(
            prompt=sanitized_prompt,
            system_instruction=system_instruction,
            history=history,
            max_new_tokens=800,
            temperature=0.1,
            model_name=config.model_name,
        )

    # Text is about to leave the machine: names become [PARTY_n] and come back in the reply.
    masker = NameMasker()
    for text in (system_instruction, prompt, *(_extract_history_turn(h)[1] for h in (history or [])[-6:])):
        masker.collect(text)
    system_instruction = masker.mask(system_instruction)
    sanitized_prompt = masker.mask(sanitized_prompt)
    reply = _query_cloud_provider(provider, sanitized_prompt, system_instruction, config, history, masker)
    return masker.unmask(reply)


def _query_cloud_provider(
    provider: str,
    sanitized_prompt: str,
    system_instruction: str,
    config: LLMConfig,
    history: Optional[List[Any]],
    masker: NameMasker,
) -> Optional[str]:
    def scrub(txt: str) -> str:
        return masker.mask(mask_pii(txt))

    api_key = (config.api_key or "").strip() if config.api_key else None
    base_url = (config.base_url or "").strip() if config.base_url else None
    try:
        endpoint, model = _resolve_endpoint(provider, base_url, config.model_name)
    except BlockedEndpointError:
        return None

    try:
        with httpx.Client(timeout=10.0) as client:
            if provider == "gemini":
                if not api_key:
                    return None
                url = f"{endpoint}?key={api_key}"
                history_text = ""
                if history:
                    h_parts = []
                    for h in history[-6:]:
                        r, txt = _extract_history_turn(h)
                        role_str = "Assistant" if r == "agent" else "User"
                        if txt:
                            h_parts.append(f"{role_str}: {scrub(txt)}")
                    if h_parts:
                        history_text = "Conversation History:\n" + "\n".join(h_parts) + "\n\n"

                payload = {
                    "contents": [{"parts": [{"text": f"System Directive: {system_instruction}\n\n{history_text}Current User Context:\n{sanitized_prompt}"}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
                }
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and isinstance(parts[0], dict) and "text" in parts[0]:
                            return parts[0]["text"].strip()

            elif provider == "anthropic":
                if not api_key:
                    return None
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                anthropic_msgs = []
                if history:
                    for h in history[-6:]:
                        r, txt = _extract_history_turn(h)
                        h_role = "assistant" if r == "agent" else "user"
                        if txt:
                            anthropic_msgs.append({"role": h_role, "content": scrub(txt)})
                anthropic_msgs.append({"role": "user", "content": sanitized_prompt})

                payload = {
                    "model": model,
                    "max_tokens": 800,
                    "system": system_instruction,
                    "messages": anthropic_msgs,
                    "temperature": 0.2,
                }
                res = client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    content_blocks = data.get("content", [])
                    texts = [b.get("text", "") for b in content_blocks if isinstance(b, dict) and b.get("type") == "text"]
                    if texts:
                        return "".join(texts).strip()
                    if content_blocks and isinstance(content_blocks[0], dict) and "text" in content_blocks[0]:
                        return content_blocks[0]["text"].strip()

            else:  # OpenAI, DeepSeek, Groq, Custom, Ollama
                headers = {"content-type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                openai_msgs = [{"role": "system", "content": system_instruction}]
                if history:
                    for h in history[-6:]:
                        r, txt = _extract_history_turn(h)
                        h_role = "assistant" if r == "agent" else "user"
                        if txt:
                            openai_msgs.append({"role": h_role, "content": scrub(txt)})
                openai_msgs.append({"role": "user", "content": sanitized_prompt})

                payload = {
                    "model": model,
                    "messages": openai_msgs,
                    "max_tokens": 800,
                    "temperature": 0.2,
                }
                res = client.post(endpoint, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content") or msg.get("reasoning_content") or ""
                        if content:
                            return str(content).strip()

    except Exception:
        # Fallback cleanly to deterministic template response
        return None

    return None


FALLBACK_CATALOG: dict[str, list[ModelItem]] = {
    "offline": [
        ModelItem(id=_get_local_default_model_id(), name=_get_local_default_model_name()),
    ],
    "local": [
        ModelItem(id=_get_local_default_model_id(), name=_get_local_default_model_name()),
    ],
    "local_native": [
        ModelItem(id=_get_local_default_model_id(), name=_get_local_default_model_name()),
    ],
    "gemini": [
        ModelItem(id="gemini-2.0-flash", name="Gemini 2.0 Flash (Recommended)"),
        ModelItem(id="gemini-1.5-pro", name="Gemini 1.5 Pro"),
        ModelItem(id="gemini-1.5-flash", name="Gemini 1.5 Flash"),
    ],
    "anthropic": [
        ModelItem(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet (Recommended)"),
        ModelItem(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku"),
        ModelItem(id="claude-3-opus-20240229", name="Claude 3 Opus"),
    ],
    "openai": [
        ModelItem(id="gpt-4o-mini", name="GPT-4o Mini (Recommended)"),
        ModelItem(id="gpt-4o", name="GPT-4o"),
        ModelItem(id="o3-mini", name="o3-mini (Reasoning)"),
    ],
    "deepseek": [
        ModelItem(id="deepseek-chat", name="DeepSeek-V3 (deepseek-chat)"),
        ModelItem(id="deepseek-reasoner", name="DeepSeek-R1 (deepseek-reasoner)"),
    ],
    "groq": [
        ModelItem(id="llama-3.3-70b-versatile", name="Llama 3.3 70B Versatile"),
        ModelItem(id="mixtral-8x7b-32768", name="Mixtral 8x7B"),
        ModelItem(id="llama-3.1-8b-instant", name="Llama 3.1 8B Instant"),
    ],
    "custom": [
        ModelItem(id="custom-model", name="Custom Model"),
    ],
    "ollama": [
        ModelItem(id="llama3.2", name="Llama 3.2"),
        ModelItem(id="qwen2.5", name="Qwen 2.5"),
        ModelItem(id="mistral", name="Mistral 7B"),
    ],
}


def get_system_specs() -> dict:
    """Host RAM and GPU for the hardware tier labels; see services.agent.hardware for the live probe."""
    from services.agent.hardware import probe_hardware

    hw = probe_hardware()
    return {
        # The tier labels need a number; 8 GB is the common laptop floor when RAM cannot be read.
        "ram_gb": hw["ram_total_gb"] or 8.0,
        "has_cuda": hw["vram_total_gb"] is not None,
        "gpu_name": hw["gpu_name"] or "",
        "vram_gb": hw["vram_total_gb"] or 0.0,
    }


def llama_cpp_installed() -> bool:
    import importlib.util

    return importlib.util.find_spec("llama_cpp") is not None


def get_fallback_catalog(provider: str) -> list[ModelItem]:
    """Returns fallback model catalog with dynamically resolved local model metadata."""
    p = (provider or "").lower()
    if p in ("offline", "local", "local_native"):
        return [
            ModelItem(
                id=_get_local_default_model_id(),
                name=_get_local_default_model_name(),
            )
        ]
    return FALLBACK_CATALOG.get(p, [ModelItem(id="custom-model", name="Custom Model")])


def fetch_remote_models(req: FetchModelsRequest) -> FetchModelsResponse:
    """Dynamically queries the target provider's live models endpoint to discover models."""
    provider = (req.provider or "offline").lower()
    fallbacks = get_fallback_catalog(provider)

    if provider in ["local", "local_native", "offline"]:
        from services.agent.local_transformers import LocalTransformersEngine, SUPPORTED_LOCAL_MODELS
        engine = LocalTransformersEngine.get_instance()
        specs = get_system_specs()
        models = []
        seen_paths: set[str] = set()
        for m_id, m_meta in SUPPORTED_LOCAL_MODELS.items():
            if m_meta.get("hidden"):
                continue
            installed = engine.is_available(m_id)
            if installed:
                # A manifest entry and the scanned file can name the same weights; list them once.
                path = os.path.normcase(os.path.abspath(str(engine.get_model_path(m_id) or m_id)))
                if path in seen_paths:
                    continue
                seen_paths.add(path)
            size_gb = m_meta.get("size_gb")
            if size_gb and size_gb <= 1.0:
                tier = "Fast / Low RAM"
            elif specs["has_cuda"] or specs["ram_gb"] >= 8.0:
                tier = "Recommended"
            else:
                tier = "Requires 4GB+ Free RAM"
            models.append(
                ModelItem(
                    id=m_id,
                    name=m_meta["name"],
                    tool_calling=m_meta.get("tool_calling"),
                    size_gb=size_gb,
                    tier=tier,
                    installed=installed,
                    repo_id=m_meta.get("repo_id"),
                    quant=m_meta.get("quant"),
                )
            )
        ready_count = sum(1 for m in models if m.installed)
        hw_desc = f"{specs['ram_gb']} GB RAM" + (f", {specs['gpu_name']}" if specs["has_cuda"] else "")
        msg = f"Device: {hw_desc}. {ready_count} of {len(models)} local models installed on disk."
        if ready_count == 0:
            msg += " Use Browse models in Settings to download one."
        return FetchModelsResponse(
            success=True,
            provider=provider,
            models=models,
            message=msg,
        )

    api_key = (req.api_key or "").strip()
    base_url = (req.base_url or "").strip()

    # If missing required credentials, return empty models list (never pretend with hardcoded list)
    if provider in ["gemini", "anthropic", "openai", "deepseek", "groq"] and not api_key:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message=f"API key required. Enter your API key to discover live models from {provider}.",
        )

    if provider == "custom" and not base_url:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message="Base URL required to fetch custom models.",
        )

    if provider == "ollama" and not base_url:
        base_url = "http://localhost:11434/v1"

    if base_url:
        try:
            allow_lb = True if provider == "ollama" or ("11434" in base_url and ("localhost" in base_url or "127.0.0.1" in base_url)) else None
            validate_llm_endpoint(base_url, allow_loopback=allow_lb)
        except BlockedEndpointError as exc:
            return FetchModelsResponse(
                success=False,
                provider=provider,
                models=[],
                message=f"Endpoint blocked by the outbound connection policy: {exc}",
            )

    try:
        with httpx.Client(timeout=6.0) as client:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models_list = []
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            mid = m.get("name", "").replace("models/", "")
                            disp = m.get("displayName", mid)
                            models_list.append(ModelItem(id=mid, name=f"{disp} ({mid})"))
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list,
                            message=f"Discovered {len(models_list)} live Gemini models.",
                        )

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/models"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                }
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    models_list = [
                        ModelItem(id=m["id"], name=m.get("display_name", m["id"]))
                        for m in data.get("data", [])
                        if "id" in m
                    ]
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list,
                            message=f"Discovered {len(models_list)} live Anthropic models.",
                        )

            else:  # OpenAI, DeepSeek, Groq, Custom
                base = base_url
                if not base:
                    if provider == "openai":
                        base = "https://api.openai.com/v1"
                    elif provider == "deepseek":
                        base = "https://api.deepseek.com/v1"
                    elif provider == "groq":
                        base = "https://api.groq.com/openai/v1"
                    elif provider == "ollama":
                        base = "http://localhost:11434/v1"
                    else:
                        base = "https://api.openai.com/v1"

                clean_base = base.rstrip("/")
                if clean_base.endswith("/chat/completions"):
                    clean_base = clean_base[:-17]
                url = f"{clean_base}/models"
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                res = client.get(url, headers=headers)

                # Fallback probe for native Ollama /api/tags if /models returns 404 or empty
                if (res.status_code != 200 or not res.json().get("data")) and ("11434" in clean_base or "ollama" in clean_base or provider == "ollama"):
                    ollama_url = f"{clean_base.removesuffix('/v1').rstrip('/')}/api/tags"
                    try:
                        res_ollama = client.get(ollama_url, timeout=3.0)
                        if res_ollama.status_code == 200:
                            tag_data = res_ollama.json()
                            raw_models = tag_data.get("models", [])
                            models_list = [
                                ModelItem(id=m.get("name", m.get("model", "")), name=m.get("name", m.get("model", "")))
                                for m in raw_models
                                if m.get("name") or m.get("model")
                            ]
                            if models_list:
                                return FetchModelsResponse(
                                    success=True,
                                    provider=provider,
                                    models=models_list[:50],
                                    message=f"Discovered {len(models_list)} live Ollama models.",
                                )
                    except Exception:
                        pass

                if res.status_code == 200:
                    data = res.json()
                    raw_items = data.get("data", [])
                    models_list = [
                        ModelItem(id=m["id"], name=m.get("name", m["id"]))
                        for m in raw_items
                        if isinstance(m, dict) and "id" in m
                    ]
                    if models_list:
                        return FetchModelsResponse(
                            success=True,
                            provider=provider,
                            models=models_list[:50],
                            message=f"Discovered {len(models_list)} live models from {provider}.",
                        )

    except Exception as exc:
        return FetchModelsResponse(
            success=False,
            provider=provider,
            models=[],
            message=f"Live model discovery failed ({str(exc)[:80]}). Verify connection and credentials.",
        )

    return FetchModelsResponse(
        success=False,
        provider=provider,
        models=[],
        message=f"Unable to query /models endpoint for {provider}. Verify connection and credentials.",
    )

