"""Hugging Face GGUF catalog: live search, quantization listing and background downloads into models/.

A repo counts as tool-capable when its GGUF chat template renders a `tools` block; that is the
template llama.cpp applies, so it is the ground truth for whether the model was trained to call tools.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from typing import Optional

from services.agent.local_transformers import MODELS_ROOT, SUPPORTED_LOCAL_MODELS

logger = logging.getLogger(__name__)

REPO_ID_RE = re.compile(r"^[A-Za-z0-9][\w.\-]*/[\w.\-]+$")
FILENAME_RE = re.compile(r"^[\w.\-]+\.gguf$", re.IGNORECASE)
SHARD_RE = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)
QUANT_RE = re.compile(r"(?:^|[-_.])((?:IQ|Q)\d(?:_[A-Z0-9]+)*|F16|BF16|F32)(?=[-_.]|$)", re.IGNORECASE)
# Smallest quant that keeps instruction following intact on 3B to 8B models.
RECOMMENDED_QUANT = "Q4_K_M"


def _tool_calling(chat_template: Optional[str]) -> Optional[str]:
    return "Native" if chat_template and "tools" in chat_template else None


def _quant(filename: str) -> Optional[str]:
    m = QUANT_RE.search(os.path.splitext(filename)[0])
    return m.group(1).upper() if m else None


# Hub REST sort keys; name and size are sorted in the browser over the pages loaded so far.
SORTS = {"popular": "downloads", "trending": "trendingScore", "latest": "lastModified", "newest": "createdAt", "liked": "likes"}
HUB_MODELS_URL = "https://huggingface.co/api/models"
HUB_PAGE = 100
# Raw pages fetched per call before returning; the tools filter can drop most of a page of image/audio repos.
MAX_HUB_PAGES = 3
MIN_RESULTS = 20


def _next_cursor(link_header: Optional[str]) -> Optional[str]:
    from urllib.parse import unquote

    m = re.search(r'<[^>]*[?&]cursor=([^&>]+)[^>]*>;\s*rel="next"', link_header or "")
    # unquote, not parse_qs: the cursor is base64 and parse_qs would turn its "+" into a space.
    return unquote(m.group(1)) if m else None


def search_gguf_models(query: str = "", sort: str = "popular", cursor: Optional[str] = None) -> dict:
    """One page of tool-capable GGUF repos, plus the cursor for the next page (None at the end).

    Tool support is read from each repo's chat template; the Hub cannot filter on it.
    """
    import httpx
    from huggingface_hub.utils import build_hf_headers

    cursor = cursor.strip() if cursor and cursor.strip() else None
    params = [("filter", "gguf"), ("sort", SORTS.get(sort, "downloads")), ("direction", "-1"), ("limit", str(HUB_PAGE))]
    params += [("expand[]", k) for k in ("gguf", "downloads", "likes", "lastModified", "author")]
    if query.strip():
        params.append(("search", query.strip()))

    results: list[dict] = []
    try:
        for _ in range(MAX_HUB_PAGES):
            page = params + ([("cursor", cursor)] if cursor else [])
            r = httpx.get(HUB_MODELS_URL, params=page, headers=build_hf_headers(), timeout=15.0)
            r.raise_for_status()
            for m in r.json():
                gguf = m.get("gguf") or {}
                tools = _tool_calling(gguf.get("chat_template"))
                if not tools:
                    continue
                results.append({
                    "repo_id": m["id"],
                    "author": m.get("author") or m["id"].split("/")[0],
                    "name": m["id"].split("/")[-1],
                    "downloads": m.get("downloads") or 0,
                    "likes": m.get("likes") or 0,
                    "last_modified": m.get("lastModified"),
                    "parameters": gguf.get("total"),
                    "context_length": gguf.get("context_length"),
                    "architecture": gguf.get("architecture"),
                    "tool_calling": tools,
                })
            cursor = _next_cursor(r.headers.get("link"))
            if not cursor or len(results) >= MIN_RESULTS:
                break
        return {"success": True, "models": results, "next_cursor": cursor, "message": None}
    except Exception as exc:
        logger.warning("Hugging Face search failed: %s", exc)
        return {"success": False, "models": [], "next_cursor": None, "message": "Could not reach Hugging Face. Check your internet connection."}


def list_gguf_files(repo_id: str) -> dict:
    """Single-file GGUF quantizations in a repo, smallest first, with the recommended one flagged."""
    if not REPO_ID_RE.match(repo_id or ""):
        return {"success": False, "repo_id": repo_id, "files": [], "message": "Invalid repository id."}
    from huggingface_hub import HfApi

    try:
        info = HfApi().model_info(repo_id, files_metadata=True, expand=None)
    except Exception as exc:
        logger.warning("Hugging Face file listing failed for %s: %s", repo_id, exc)
        return {"success": False, "repo_id": repo_id, "files": [], "message": "Could not load files for this model."}

    # The manifest names files that may never have been downloaded; only a file on disk counts.
    installed = {
        os.path.basename(m["filename"])
        for m in SUPPORTED_LOCAL_MODELS.values()
        if m.get("is_gguf") and m.get("filename")
        and os.path.isfile(os.path.join(m.get("base_dir") or m.get("local_dir") or MODELS_ROOT, os.path.basename(m["filename"])))
    }
    files = []
    for s in info.siblings or []:
        name = s.rfilename
        # shortcut: split shards and vision projectors are skipped; add multi-file download if large models are needed.
        if not name.lower().endswith(".gguf") or "/" in name or SHARD_RE.search(name) or "mmproj" in name.lower():
            continue
        files.append({
            "filename": name,
            "size_bytes": s.size,
            "quant": _quant(name),
            "installed": name in installed,
            "recommended": False,
        })
    files.sort(key=lambda f: f["size_bytes"] or 0)
    rec = next((f for f in files if f["quant"] == RECOMMENDED_QUANT), None) or next(
        (f for f in files if (f["quant"] or "").startswith("Q4")), None
    )
    if rec:
        rec["recommended"] = True
    return {"success": True, "repo_id": repo_id, "files": files, "message": None if files else "No single-file GGUF builds in this repository."}


_jobs: dict[str, dict] = {}
_cancel: dict[str, threading.Event] = {}
_jobs_lock = threading.Lock()
MAX_JOB_HISTORY = 50


def _prune_jobs_locked() -> None:
    if len(_jobs) <= MAX_JOB_HISTORY:
        return
    terminated = [
        (jid, j["started_at"])
        for jid, j in _jobs.items()
        if j.get("status") in ("completed", "cancelled", "failed")
    ]
    terminated.sort(key=lambda item: item[1])
    excess = len(_jobs) - MAX_JOB_HISTORY
    for jid, _ in terminated[:excess]:
        _jobs.pop(jid, None)


def _set(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            if fields.get("status") in ("completed", "cancelled", "failed"):
                _prune_jobs_locked()


def list_downloads() -> list[dict]:
    with _jobs_lock:
        return [dict(j) for j in sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)]


def cancel_download(job_id: str) -> bool:
    ev = _cancel.get(job_id)
    if ev is None:
        return False
    ev.set()
    return True


def start_download(repo_id: str, filename: str) -> dict:
    """Queues a background download of one GGUF file into models/<filename>."""
    if not REPO_ID_RE.match(repo_id or "") or not FILENAME_RE.match(filename or ""):
        return {"success": False, "message": "Invalid repository or file name.", "job": None}
    with _jobs_lock:
        for j in _jobs.values():
            if j["filename"] == filename and j["status"] in ("queued", "downloading"):
                return {"success": True, "message": "Already downloading.", "job": dict(j)}
        job_id = uuid.uuid4().hex[:12]
        _prune_jobs_locked()
        _jobs[job_id] = {
            "job_id": job_id,
            "repo_id": repo_id,
            "filename": filename,
            "model_id": os.path.splitext(filename)[0].lower(),
            "status": "queued",
            "downloaded_bytes": 0,
            "total_bytes": None,
            "message": None,
            "started_at": time.time(),
        }
        _cancel[job_id] = threading.Event()
        job = dict(_jobs[job_id])
    threading.Thread(target=_download, args=(job_id, repo_id, filename), daemon=True).start()
    return {"success": True, "message": "Download started.", "job": job}


def _download(job_id: str, repo_id: str, filename: str) -> None:
    import httpx
    from huggingface_hub import hf_hub_url, model_info
    from huggingface_hub.utils import build_hf_headers

    os.makedirs(MODELS_ROOT, exist_ok=True)
    target = os.path.join(MODELS_ROOT, filename)
    part = target + ".part"
    cancel = _cancel[job_id]
    try:
        with httpx.stream("GET", hf_hub_url(repo_id, filename), headers=build_hf_headers(), follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0)) as r:
            if r.status_code in (401, 403):
                raise RuntimeError("This model is gated. Accept its license on Hugging Face and set HF_TOKEN.")
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0) or None
            if total and shutil.disk_usage(MODELS_ROOT).free < total + 512 * 1024**2:
                raise RuntimeError(f"Not enough disk space: {total / 1024**3:.1f} GB needed.")
            _set(job_id, status="downloading", total_bytes=total)
            done = 0
            last = 0.0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1024 * 1024):
                    if cancel.is_set():
                        raise InterruptedError
                    f.write(chunk)
                    done += len(chunk)
                    if time.monotonic() - last > 0.25:
                        _set(job_id, downloaded_bytes=done)
                        last = time.monotonic()
        if total and done != total:
            raise RuntimeError("Download ended early. Try again.")
        os.replace(part, target)
        _write_sidecar(repo_id, filename, model_info)
        SUPPORTED_LOCAL_MODELS.refresh()
        _set(job_id, status="completed", downloaded_bytes=done, message=f"{filename} is ready.")
    except InterruptedError:
        _set(job_id, status="cancelled", message="Download cancelled.")
    except Exception as exc:
        logger.warning("Download of %s/%s failed: %s", repo_id, filename, exc)
        msg = str(exc) if isinstance(exc, RuntimeError) else "Download failed. Check your connection and try again."
        _set(job_id, status="failed", message=msg)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        _cancel.pop(job_id, None)


def _write_sidecar(repo_id: str, filename: str, model_info) -> None:
    """models/<stem>.json keeps where a file came from and whether it calls tools; the scanner reads it."""
    meta = {"repo_id": repo_id, "filename": filename, "quant": _quant(filename), "tool_calling": None}
    try:
        gguf = model_info(repo_id, expand=["gguf"]).gguf or {}
        meta.update(tool_calling=_tool_calling(gguf.get("chat_template")), context_length=gguf.get("context_length"), architecture=gguf.get("architecture"))
    except Exception as exc:
        logger.debug("Could not read GGUF metadata for %s: %s", repo_id, exc)
    with open(os.path.join(MODELS_ROOT, os.path.splitext(filename)[0] + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
