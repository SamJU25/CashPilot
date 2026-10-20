"""Hugging Face GGUF catalog: search filtering, quantization listing, downloads and safe deletes."""

import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from services.agent import hf_catalog, local_transformers
from services.agent.local_transformers import LocalTransformersEngine, scan_models_directory
from tests.auth_helpers import tenant_headers

TOOLS_TEMPLATE = "{% if tools %}<tools>{{ tools }}</tools>{% endif %}{{ messages }}"


def _repo(repo_id, template):
    return SimpleNamespace(
        id=repo_id,
        author=repo_id.split("/")[0],
        downloads=10,
        likes=2,
        last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
        gguf={"chat_template": template, "total": 3_000_000_000, "context_length": 32768, "architecture": "qwen2"},
    )


def _hub_page(repos, next_cursor=None):
    link = f'<https://huggingface.co/api/models?filter=gguf&cursor={next_cursor}>; rel="next"' if next_cursor else ""
    body = [
        {"id": rid, "author": rid.split("/")[0], "downloads": 10, "likes": 2, "lastModified": "2026-01-01T00:00:00.000Z",
         "gguf": {"chat_template": tpl, "total": 3_000_000_000, "context_length": 32768, "architecture": "qwen2"}}
        for rid, tpl in repos
    ]
    return MagicMock(status_code=200, headers={"link": link}, json=MagicMock(return_value=body))


def test_search_keeps_only_tool_capable_repos_and_returns_the_next_cursor():
    page = _hub_page([("a/tools-GGUF", TOOLS_TEMPLATE), ("b/plain-GGUF", "{{ messages }}")], next_cursor="abc+/=")
    with patch("httpx.get", return_value=page) as get, patch.object(hf_catalog, "MAX_HUB_PAGES", 1):
        res = hf_catalog.search_gguf_models("qwen", sort="latest")
    assert [m["repo_id"] for m in res["models"]] == ["a/tools-GGUF"]
    assert res["models"][0]["parameters"] == 3_000_000_000
    assert res["next_cursor"] == "abc+/="
    params = dict(get.call_args.kwargs["params"])
    assert params["sort"] == "lastModified" and params["search"] == "qwen"


def test_search_follows_cursor_until_enough_results_or_the_end():
    pages = [_hub_page([("b/plain-GGUF", "{{ messages }}")], next_cursor="p2"), _hub_page([("a/tools-GGUF", TOOLS_TEMPLATE)])]
    with patch("httpx.get", side_effect=pages) as get:
        res = hf_catalog.search_gguf_models("", cursor="p1")
    assert [m["repo_id"] for m in res["models"]] == ["a/tools-GGUF"]
    assert res["next_cursor"] is None
    assert [dict(c.kwargs["params"]).get("cursor") for c in get.call_args_list] == ["p1", "p2"]


def test_search_reports_network_failure():
    with patch("httpx.get", side_effect=OSError("offline")):
        res = hf_catalog.search_gguf_models("qwen")
    assert res["success"] is False
    assert "internet" in res["message"]


def test_files_skip_shards_and_projectors_and_flag_q4_k_m():
    siblings = [
        SimpleNamespace(rfilename=name, size=size)
        for name, size in [
            ("Model-Q8_0.gguf", 300),
            ("Model-Q4_K_M.gguf", 200),
            ("Model-IQ3_M.gguf", 100),
            ("Model-F16-00001-of-00002.gguf", 900),
            ("mmproj-Model-f16.gguf", 50),
            ("README.md", 1),
        ]
    ]
    with patch("huggingface_hub.HfApi") as api:
        api.return_value.model_info.return_value = SimpleNamespace(siblings=siblings)
        res = hf_catalog.list_gguf_files("org/Model-GGUF")
    assert [f["filename"] for f in res["files"]] == ["Model-IQ3_M.gguf", "Model-Q4_K_M.gguf", "Model-Q8_0.gguf"]
    assert [f["quant"] for f in res["files"]] == ["IQ3_M", "Q4_K_M", "Q8_0"]
    assert [f["recommended"] for f in res["files"]] == [False, True, False]


def test_download_rejects_path_traversal():
    assert hf_catalog.start_download("org/repo", "../evil.gguf")["success"] is False
    assert hf_catalog.start_download("org/repo", "notes.txt")["success"] is False
    assert hf_catalog.start_download("../x", "a.gguf")["success"] is False


def test_download_writes_file_and_sidecar_into_models(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_catalog, "MODELS_ROOT", str(tmp_path))
    body = [b"GGUF", b"\x00" * 1020]
    resp = MagicMock(status_code=200, headers={"content-length": "1024"})
    resp.iter_bytes.return_value = body
    stream = MagicMock()
    stream.__enter__.return_value = resp

    with patch("httpx.stream", return_value=stream), patch(
        "huggingface_hub.model_info", return_value=SimpleNamespace(gguf={"chat_template": TOOLS_TEMPLATE, "context_length": 8192})
    ):
        job = hf_catalog.start_download("org/Tiny-GGUF", "Tiny-Q4_K_M.gguf")["job"]
        for _ in range(100):
            state = next(j for j in hf_catalog.list_downloads() if j["job_id"] == job["job_id"])
            if state["status"] in ("completed", "failed"):
                break
            time.sleep(0.02)

    assert state["status"] == "completed", state["message"]
    assert (tmp_path / "Tiny-Q4_K_M.gguf").stat().st_size == 1024
    assert not (tmp_path / "Tiny-Q4_K_M.gguf.part").exists()
    sidecar = json.loads((tmp_path / "Tiny-Q4_K_M.json").read_text())
    assert sidecar["tool_calling"] == "Native" and sidecar["quant"] == "Q4_K_M"

    meta = scan_models_directory(str(tmp_path))["tiny-q4_k_m"]
    assert meta["repo_id"] == "org/Tiny-GGUF"
    assert meta["tool_calling"] == "Native"


def test_deleting_a_root_level_gguf_keeps_the_models_folder(tmp_path, monkeypatch):
    models = tmp_path / "models"
    (models / "base").mkdir(parents=True)
    (models / "adapter").mkdir()
    (models / "adapter" / "keep.txt").write_text("adapter")
    (models / "a.gguf").write_bytes(b"GGUF")
    (models / "a.json").write_text("{}")
    (models / "b.gguf").write_bytes(b"GGUF")
    monkeypatch.setattr(local_transformers, "MODELS_ROOT", str(models))
    monkeypatch.setattr(local_transformers, "BASE_MODELS_ROOT", str(models / "base"))
    catalog = scan_models_directory(str(models))
    monkeypatch.setattr(local_transformers, "build_supported_models_catalog", lambda: catalog)

    res = LocalTransformersEngine.get_instance().delete_model("a")

    assert res["success"] is True
    assert not (models / "a.gguf").exists() and not (models / "a.json").exists()
    assert (models / "b.gguf").exists()
    assert (models / "adapter" / "keep.txt").exists()


def test_hf_routes_require_a_tenant_token():
    client = TestClient(app)
    assert client.get("/api/v1/agent/hf/downloads").status_code == 401
    with patch("httpx.get", return_value=_hub_page([])):
        resp = client.get("/api/v1/agent/hf/search?q=qwen&cursor=abc%2B%2F%3D", headers=tenant_headers(client, "SME-HF-TEST"))
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Empty cursor parameter should not trigger 422 Unprocessable Entity
    with patch("httpx.get", return_value=_hub_page([])):
        resp_empty = client.get("/api/v1/agent/hf/search?q=qwen&cursor=", headers=tenant_headers(client, "SME-HF-TEST"))
    assert resp_empty.status_code == 200
    assert resp_empty.json()["success"] is True


def test_one_file_in_models_does_not_mark_other_models_installed(tmp_path, monkeypatch):
    models = tmp_path / "models"
    (models / "base").mkdir(parents=True)
    (models / "downloaded.gguf").write_bytes(b"GGUF" + b"\x00" * (2 * 1024 * 1024))
    monkeypatch.setattr(local_transformers, "MODELS_ROOT", str(models))
    monkeypatch.setattr(local_transformers, "BASE_MODELS_ROOT", str(models / "base"))
    catalog = scan_models_directory(str(models))
    catalog["manifest-only"] = {"id": "manifest-only", "name": "Never downloaded", "repo_id": "org/Other-GGUF", "filename": "other-q4_k_m.gguf", "local_dir": str(models / "base" / "manifest-only"), "is_gguf": True}
    monkeypatch.setattr(local_transformers, "build_supported_models_catalog", lambda: catalog)

    engine = LocalTransformersEngine.get_instance()
    assert engine.is_available("downloaded") is True
    assert engine.is_available("manifest-only") is False


def test_download_jobs_history_bounded():
    """Verify completed download jobs are capped at MAX_JOB_HISTORY to avoid memory leaks."""
    with hf_catalog._jobs_lock:
        hf_catalog._jobs.clear()
        for i in range(60):
            jid = f"job-{i:03d}"
            hf_catalog._jobs[jid] = {
                "job_id": jid,
                "filename": f"model-{i}.gguf",
                "status": "completed",
                "started_at": i,
            }
        hf_catalog._prune_jobs_locked()
        assert len(hf_catalog._jobs) == hf_catalog.MAX_JOB_HISTORY
        # The 10 oldest jobs (started_at 0..9) should have been pruned
        assert "job-000" not in hf_catalog._jobs
        assert "job-009" not in hf_catalog._jobs
        assert "job-010" in hf_catalog._jobs
        assert "job-059" in hf_catalog._jobs
