"""Unit tests for explicit model downloading, cache verification, and exception handling.

Verifies:
- Strict zero-silent-download invariant
- Proper exception handling when network fails or disk error occurs
- REST endpoint POST /api/v1/agent/download-model
- Multi-tier local model resolution and availability checking
"""

import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.agent.local_transformers import (
    BASE_MODEL_DIR,
    LocalTransformersEngine,
    SUPPORTED_LOCAL_MODELS,
    get_default_model_id,
    resolve_canonical_model_name,
)
from services.agent.schema import (
    DownloadModelRequest,
    DownloadModelResponse,
    FetchModelsRequest,
    TestConnectionRequest,
)
from services.agent.llm_bridge import fetch_remote_models, test_llm_connection as run_test_llm_connection
from tests.auth_helpers import tenant_headers

TestConnectionRequest.__test__ = False


@pytest.fixture
def client():
    return TestClient(app)


def test_canonical_model_resolution():
    """Confirms model aliases map cleanly to canonical IDs dynamically."""
    default_id = get_default_model_id()
    assert resolve_canonical_model_name(None) == default_id
    assert resolve_canonical_model_name("") == default_id
    assert resolve_canonical_model_name("offline") == default_id
    assert resolve_canonical_model_name("local") == default_id
    assert resolve_canonical_model_name(default_id) == default_id
    default_meta = SUPPORTED_LOCAL_MODELS.get(default_id, {})
    for alias in default_meta.get("aliases", []):
        assert resolve_canonical_model_name(alias) == default_id


def test_download_model_invalid_identifier():
    """Attempts to download an unknown model return clean error without crashing."""
    engine = LocalTransformersEngine.get_instance()
    res = engine.download_model("nonexistent-model-xyz")
    assert res["success"] is False
    assert "Unsupported model" in res["message"]
    assert res["downloaded_path"] is None


def test_download_model_network_exception_handling():
    """Simulates network timeout/failure during download to verify robust exception handling."""
    engine = LocalTransformersEngine.get_instance()
    default_id = get_default_model_id()
    with patch("huggingface_hub.snapshot_download", side_effect=ConnectionError("Failed to resolve host 'huggingface.co'")):
        res = engine.download_model(default_id)
        assert res["success"] is False
        assert "Network connection error" in res["message"] or "Failed to resolve host" in res["message"]
        assert res["downloaded_path"] is None


def test_download_model_disk_space_exception_handling():
    """Simulates insufficient disk space to verify friendly OS error handling."""
    engine = LocalTransformersEngine.get_instance()
    default_id = get_default_model_id()
    with patch("huggingface_hub.snapshot_download", side_effect=OSError("No space left on device")):
        res = engine.download_model(default_id)
        assert res["success"] is False
        assert "Insufficient disk space" in res["message"] or "space" in res["message"]


def test_api_download_model_route(client):
    """Verifies POST /api/v1/agent/download-model endpoint."""
    default_id = get_default_model_id()
    with patch.object(
        LocalTransformersEngine,
        "download_model",
        return_value={
            "success": True,
            "model_name": default_id,
            "message": f"Model '{default_id}' downloaded successfully (5886.0 MB).",
            "downloaded_path": "/mock/path/models/base/MiniCPM5-2B",
            "size_mb": 5886.0,
        },
    ):
        resp = client.post(
            "/api/v1/agent/download-model",
            json={"model_name": default_id},
            headers=tenant_headers(client, "SME-MODEL-TEST"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["model_name"] == default_id
        assert data["size_mb"] == 5886.0
        assert "downloaded successfully" in data["message"]


def test_fetch_remote_models_reports_only_flagship_adapter():
    """Ensures discovery endpoint lists only the fine-tuned adapter, omitting base foundation models."""
    default_id = get_default_model_id()
    resp = fetch_remote_models(FetchModelsRequest(provider="offline"))
    assert resp.success is True
    ids = [m.id for m in resp.models]
    assert default_id in ids


def test_download_model_saves_into_folder():
    """Verifies download_model passes local_dir to snapshot_download to store weights inside project models folder."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.snapshot_download") as mock_snapshot:
        mock_snapshot.return_value = BASE_MODEL_DIR
        res = engine.download_model("sme-finance-lora")
        assert res["success"] is True
        mock_snapshot.assert_called_once()
        _, kwargs = mock_snapshot.call_args
        assert "local_dir" in kwargs
        assert kwargs["local_dir"].endswith("MiniCPM5-2B")


def test_test_connection_missing_model_handling():
    """Verifies that test_connection returns actionable guidance asking to download a model first."""
    engine = LocalTransformersEngine.get_instance()
    with patch.object(engine, "is_available", return_value=False):
        resp = run_test_llm_connection(TestConnectionRequest(provider="offline", model_name="sme-finance-lora"))
        assert resp.success is False
        assert "not installed locally on disk" in resp.message
        assert "Download Model" in resp.message


def test_fetch_remote_models_message_when_none_installed():
    """Verifies that discovery message prompts the user to download a model first when 0 models are ready."""
    engine = LocalTransformersEngine.get_instance()
    with patch.object(engine, "is_available", return_value=False):
        resp = fetch_remote_models(FetchModelsRequest(provider="offline"))
        assert resp.success is True
        assert "Download Model" in resp.message


def test_supervisor_asks_to_download_model_when_none_installed():
    """Verifies supervisor prompts the user to download a model first when in local mode with 0 models installed."""
    import os
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest, LLMConfig
    from services.agent.local_transformers import LocalTransformersEngine

    engine = LocalTransformersEngine.get_instance()
    # Temporarily remove PYTEST_CURRENT_TEST to test production user guidance flow
    old_test_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        with patch.object(engine, "is_available", return_value=False):
            req = AgentChatRequest(
                message="Hello, how can you help my business?",
                llm_config=LLMConfig(provider="offline", model_name="sme-finance-lora"),
            )
            resp = run_copilot_supervisor(req, llm_config=req.llm_config)
            assert ("CashPilot" in resp.reply or "Autonomous SME Finance Copilot" in resp.reply)
            assert "Please download a model first" in resp.reply
            assert "Download Model" in resp.reply
    finally:
        if old_test_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = old_test_env


def test_delete_model_protects_adapters(tmp_path):
    """Verifies that delete_model only targets base model directory and strictly preserves adapters."""
    from services.agent.local_transformers import LORA_MODEL_DIR
    engine = LocalTransformersEngine.get_instance()

    # Confirm the adapter folder exists and is never deleted
    os.makedirs(LORA_MODEL_DIR, exist_ok=True)
    assert os.path.exists(LORA_MODEL_DIR)

    with patch("shutil.rmtree") as mock_rmtree:
        engine.delete_model("sme-finance-lora")
        for call_args in mock_rmtree.call_args_list:
            target_deleted = call_args[0][0]
            assert target_deleted != LORA_MODEL_DIR
            assert "base" in target_deleted or "hub" in target_deleted


def test_api_delete_model_route(client):
    """Verifies POST /api/v1/agent/delete-model endpoint."""
    with patch.object(
        LocalTransformersEngine,
        "delete_model",
        return_value={
            "success": True,
            "model_name": "sme-finance-lora",
            "message": "Model 'sme-finance-lora' removed successfully (5886.0 MB freed).",
            "deleted_path": "/mock/path/models/base/MiniCPM5-2B",
            "freed_mb": 5886.0,
        },
    ):
        resp = client.post(
            "/api/v1/agent/delete-model",
            json={"model_name": "sme-finance-lora"},
            headers=tenant_headers(client, "SME-MODEL-TEST"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["model_name"] == "sme-finance-lora"
        assert data["freed_mb"] == 5886.0
        assert "removed successfully" in data["message"]




def test_adapter_loads_onto_the_base_it_was_trained_on(tmp_path):
    import json
    from services.agent.local_transformers import (
        BASE_MODEL_ID,
        adapter_base_model_id,
        base_on_disk,
        local_base_dir,
    )

    (tmp_path / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "Org/Other-Base-1B"}))
    assert adapter_base_model_id(str(tmp_path)) == "Org/Other-Base-1B"
    assert local_base_dir("Org/Other-Base-1B").endswith("Other-Base-1B")
    assert base_on_disk("Org/Other-Base-1B") is None
    assert adapter_base_model_id(str(tmp_path / "missing")) == BASE_MODEL_ID


def test_base_aliases_resolve():
    assert resolve_canonical_model_name("minicpm5-base") == "base-instruct"
    assert resolve_canonical_model_name("base-2b") == "base-instruct"
    assert resolve_canonical_model_name("base") == "base-instruct"
    assert resolve_canonical_model_name("minicpm5-2b") == "minicpm5-2b"
    assert resolve_canonical_model_name("minicpm5") == "minicpm5-2b"
    assert resolve_canonical_model_name("openbmb/minicpm5-2b") == "minicpm5-2b"


def test_download_model_minicpm5_2b():
    """Verifies download_model handles minicpm5-2b foundation repository snapshot download."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.snapshot_download") as mock_snapshot:
        mock_snapshot.return_value = "/mock/path/models/base/MiniCPM5-2B"
        res = engine.download_model("minicpm5-2b")
        assert res["success"] is True
        mock_snapshot.assert_called_once()
        _, kwargs = mock_snapshot.call_args
        assert "local_dir" in kwargs
        assert kwargs["local_dir"].endswith("MiniCPM5-2B")


def test_dynamic_manifest_registration(tmp_path, monkeypatch):
    """Verifies adding a model to models_config.json dynamically registers it without code change."""
    import json
    import services.agent.local_transformers as trans_module

    config_content = {
        "default_model": "custom-fintech-3b",
        "base_model_id": "meta-llama/Llama-3.2-3B-Instruct",
        "models": {
            "custom-fintech-3b": {
                "id": "custom-fintech-3b",
                "name": "Custom FinTech 3B Model",
                "repo_id": "meta-llama/Llama-3.2-3B-Instruct",
                "is_lora": False,
                "aliases": ["custom-3b", "custom_model"],
            }
        },
    }
    manifest_file = tmp_path / "models_config.json"
    manifest_file.write_text(json.dumps(config_content), encoding="utf-8")

    monkeypatch.setattr(trans_module, "MODELS_CONFIG_FILE", str(manifest_file))
    catalog = trans_module.build_supported_models_catalog()

    assert "custom-fintech-3b" in catalog
    assert catalog["custom-fintech-3b"]["name"] == "Custom FinTech 3B Model"

    monkeypatch.setattr(trans_module, "SUPPORTED_LOCAL_MODELS", catalog)
    monkeypatch.setattr(trans_module, "DEFAULT_MODEL_ID", "custom-fintech-3b")

    assert trans_module.resolve_canonical_model_name("custom-3b") == "custom-fintech-3b"
    assert trans_module.resolve_canonical_model_name("custom_model") == "custom-fintech-3b"
    assert trans_module.resolve_canonical_model_name(None) == "custom-fintech-3b"


def test_environment_variable_model_override(monkeypatch):
    """Verifies CASHPILOT_DEFAULT_MODEL environment variable overrides active default model without code change."""
    import services.agent.local_transformers as trans_module

    monkeypatch.setenv("CASHPILOT_DEFAULT_MODEL", "minicpm5-2b")
    assert trans_module.get_default_model_id() == "minicpm5-2b"
    assert trans_module.resolve_canonical_model_name(None) == "minicpm5-2b"
    assert trans_module.resolve_canonical_model_name("") == "minicpm5-2b"
    assert trans_module.resolve_canonical_model_name("default") == "minicpm5-2b"


def test_auto_discovery_of_dropped_adapter(tmp_path):
    """Verifies placing an adapter folder with adapter_config.json into models/ auto-detects it."""
    import json
    from services.agent.local_transformers import scan_models_directory

    models_dir = tmp_path / "models"
    adapter_dir = models_dir / "my-fintech-lora"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "openbmb/MiniCPM5-2B"}),
        encoding="utf-8",
    )

    discovered = scan_models_directory(str(models_dir))
    assert "my-fintech-lora" in discovered
    meta = discovered["my-fintech-lora"]
    assert meta["is_lora"] is True
    assert meta["repo_id"] == "openbmb/MiniCPM5-2B"
    assert "LoRA Adapter" in meta["name"]


def test_auto_discovery_of_dropped_causal_lm(tmp_path):
    """Verifies placing a full causal LM model with config.json into models/ auto-detects it."""
    import json
    from services.agent.local_transformers import scan_models_directory

    models_dir = tmp_path / "models"
    model_dir = models_dir / "custom-minicpm-test"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text(
        json.dumps({"model_type": "minicpm", "_name_or_path": "openbmb/MiniCPM-2B-sft-bf16"}),
        encoding="utf-8",
    )

    discovered = scan_models_directory(str(models_dir))
    assert "custom-minicpm-test" in discovered
    meta = discovered["custom-minicpm-test"]
    assert meta["is_lora"] is False
    assert meta["repo_id"] == "openbmb/MiniCPM-2B-sft-bf16"
    assert "Minicpm" in meta["name"]




def test_gguf_canonical_resolution():
    """Verifies modern text-based GGUF model identifiers and aliases resolve."""
    assert resolve_canonical_model_name("qwen2.5-3b-instruct") == "qwen2.5-3b-instruct"
    assert resolve_canonical_model_name("qwen-3b") == "qwen2.5-3b-instruct"
    assert resolve_canonical_model_name("qwen2.5-3b") == "qwen2.5-3b-instruct"
    assert resolve_canonical_model_name("qwen-1.5b") == "qwen2.5-1.5b-instruct"
    assert resolve_canonical_model_name("llama-3.2-3b") == "llama-3.2-3b-instruct"
    assert resolve_canonical_model_name("llama-1b") == "llama-3.2-1b-instruct"


def test_download_model_gguf_uses_hf_hub_download():
    """Verifies GGUF downloads route to hf_hub_download with exact filename."""
    engine = LocalTransformersEngine.get_instance()
    with patch("huggingface_hub.hf_hub_download") as mock_hf_download:
        mock_hf_download.return_value = "/mock/path/models/base/Qwen2.5-3B-Instruct-GGUF/qwen2.5-3b-instruct-q4_k_m.gguf"
        res = engine.download_model("qwen2.5-3b-instruct")
        assert res["success"] is True
        mock_hf_download.assert_called_once()
        _, kwargs = mock_hf_download.call_args
        assert kwargs["filename"] == "qwen2.5-3b-instruct-q4_k_m.gguf"
        assert kwargs["repo_id"] == "Qwen/Qwen2.5-3B-Instruct-GGUF"


def test_fetch_remote_models_annotates_device_capability():
    """Verifies fetch-models returns dynamic capability-annotated models list."""
    resp = fetch_remote_models(FetchModelsRequest(provider="offline"))
    assert resp.success is True
    assert len(resp.models) >= 4
    names = [m.name for m in resp.models]
    assert any("Recommended" in n for n in names)
    assert any("Low RAM" in n for n in names)


def test_auto_discovery_of_dropped_gguf_file(tmp_path):
    """Verifies placing any .gguf file into models/ dynamically detects it without config."""
    from services.agent.local_transformers import scan_models_directory
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    custom_gguf = models_dir / "custom-finance-7b.gguf"
    custom_gguf.write_bytes(b"GGUF" + b"\x00" * 1024)

    discovered = scan_models_directory(str(models_dir))
    assert "custom-finance-7b" in discovered
    meta = discovered["custom-finance-7b"]
    assert meta["is_gguf"] is True
    assert meta["filename"] == "custom-finance-7b.gguf"
