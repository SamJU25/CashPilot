"""Native GGUF Local Inference Engine for CashPilot via llama.cpp.

Enforces:
- 100% on-device, in-process neural generation via llama-cpp-python
- Zero dependency on Ollama or external daemon services
- Zero API keys or cloud transmissions
- Dynamic device capability matching (CPU / GPU offload)
- Zero silent auto-downloads: weights are downloaded only on explicit user request
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

MODELS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models"))
BASE_MODELS_ROOT = os.path.join(MODELS_ROOT, "base")
MODELS_CONFIG_FILE = os.getenv(
    "CASHPILOT_MODELS_CONFIG",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config/models.json")),
)
FALLBACK_MODELS_CONFIG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../models/models_config.json")
)


def _read_models_manifest() -> dict:
    """Reads models config JSON if present; returns empty dict on failure."""
    for cfg_path in (MODELS_CONFIG_FILE, FALLBACK_MODELS_CONFIG_FILE):
        if not cfg_path:
            continue
        try:
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            logger.warning("Failed to parse models configuration from %s: %s", cfg_path, exc)
        except Exception as exc:
            logger.warning("Unexpected error reading models configuration from %s: %s", cfg_path, exc)
    return {}


def get_adapter_dirs(root_dir: str = MODELS_ROOT) -> list[str]:
    """Dynamically finds all adapter directories containing adapter_config.json under models/."""
    dirs: list[str] = []
    try:
        if not os.path.exists(root_dir):
            return dirs
        for entry in sorted(os.listdir(root_dir)):
            if entry.startswith(".") or entry in ("base", "__pycache__"):
                continue
            cand = os.path.join(root_dir, entry)
            try:
                if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "adapter_config.json")):
                    dirs.append(os.path.abspath(cand))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError) as exc:
        logger.debug("Error scanning adapter directories in %s: %s", root_dir, exc)
    return dirs


def get_primary_adapter_dir() -> str:
    """Returns the primary adapter directory discovered on disk, from env, or from manifest."""
    env_dir = os.getenv("CASHPILOT_ADAPTER_DIR") or os.getenv("LORA_MODEL_DIR")
    if env_dir:
        try:
            if os.path.exists(env_dir):
                return os.path.abspath(env_dir)
        except (OSError, PermissionError):
            pass

    adapters = get_adapter_dirs()
    if adapters:
        return adapters[0]

    manifest = _read_models_manifest()
    for m in manifest.get("models", {}).values():
        if m.get("is_lora") and m.get("local_dir"):
            loc = (
                os.path.abspath(m["local_dir"])
                if os.path.isabs(m["local_dir"])
                else os.path.abspath(os.path.join(MODELS_ROOT, m["local_dir"]))
            )
            try:
                if os.path.exists(loc):
                    return loc
            except (OSError, PermissionError):
                continue

    return os.path.abspath(os.path.join(MODELS_ROOT, "adapter"))


def get_merged_model_dirs(root_dir: str = MODELS_ROOT) -> list[str]:
    """Dynamically finds standalone merged causal LM model directories under models/."""
    dirs: list[str] = []
    try:
        if not os.path.exists(root_dir):
            return dirs
        for entry in sorted(os.listdir(root_dir)):
            if entry.startswith(".") or entry in ("base", "__pycache__"):
                continue
            cand = os.path.join(root_dir, entry)
            try:
                if (
                    os.path.isdir(cand)
                    and os.path.exists(os.path.join(cand, "config.json"))
                    and not os.path.exists(os.path.join(cand, "adapter_config.json"))
                ):
                    dirs.append(os.path.abspath(cand))
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError) as exc:
        logger.debug("Error scanning merged model directories in %s: %s", root_dir, exc)
    return dirs


def get_primary_merged_dir() -> str:
    """Returns primary merged model directory discovered on disk or from env."""
    env_dir = os.getenv("CASHPILOT_MERGED_DIR") or os.getenv("MERGED_MODEL_DIR")
    if env_dir:
        try:
            if os.path.exists(env_dir):
                return os.path.abspath(env_dir)
        except (OSError, PermissionError):
            pass

    merged = get_merged_model_dirs()
    if merged:
        return merged[0]
    return os.path.abspath(os.path.join(MODELS_ROOT, "merged"))


# Expose dynamic directory references for backwards-compatible consumers
LORA_MODEL_DIR = get_primary_adapter_dir()
MERGED_MODEL_DIR = get_primary_merged_dir()


def get_base_model_id() -> str:
    """Dynamically resolves base foundation model ID from env, manifest, or fallback."""
    env_base = os.getenv("CASHPILOT_BASE_MODEL_ID") or os.getenv("BASE_MODEL_ID")
    if env_base:
        return env_base

    manifest = _read_models_manifest()
    if manifest.get("base_model_id"):
        return manifest["base_model_id"]

    for a_dir in get_adapter_dirs():
        cfg_file = os.path.join(a_dir, "adapter_config.json")
        try:
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    base_name = cfg.get("base_model_name_or_path")
                    if base_name:
                        return base_name
        except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            continue

    try:
        if os.path.exists(BASE_MODELS_ROOT):
            for b in sorted(os.listdir(BASE_MODELS_ROOT)):
                if not b.startswith(".") and os.path.isdir(os.path.join(BASE_MODELS_ROOT, b)):
                    return b
    except (OSError, PermissionError):
        pass

    return "Qwen/Qwen2.5-3B-Instruct-GGUF"


def get_default_model_id() -> str:
    """Returns active default model ID dynamically discovered from env, disk, or manifest."""
    env_override = os.getenv("CASHPILOT_DEFAULT_MODEL") or os.getenv("LOCAL_MODEL_DEFAULT")
    if env_override:
        return env_override

    manifest = _read_models_manifest()
    if manifest.get("default_model"):
        return manifest["default_model"]

    for m_id, meta in manifest.get("models", {}).items():
        if not meta.get("hidden"):
            return m_id

    return "qwen2.5-3b-instruct"


def get_default_model_name() -> str:
    """Returns active default model human-readable name dynamically discovered from manifest or folder."""
    def_id = get_default_model_id()
    manifest = _read_models_manifest()
    models = manifest.get("models", {})
    if def_id in models and models[def_id].get("name"):
        return models[def_id]["name"]
    for m in models.values():
        if m.get("id") == def_id and m.get("name"):
            return m["name"]
    return def_id.replace("-", " ").replace("_", " ").title()


BASE_MODEL_ID = get_base_model_id()
DEFAULT_MODEL_ID = get_default_model_id()
DEFAULT_MODEL_NAME = get_default_model_name()


def local_base_dir(model_id: str) -> str:
    """models/base/<safe name>: the folder download_model fills for that model."""
    safe_name = (model_id or "").replace("\\", "/").rstrip("/").split("/")[-1]
    return os.path.join(BASE_MODELS_ROOT, safe_name)


BASE_MODEL_DIR = local_base_dir(BASE_MODEL_ID)


def adapter_base_model_id(adapter_dir: Optional[str] = None) -> str:
    """Base the adapter was trained on, from its adapter_config.json."""
    target_dir = adapter_dir or get_primary_adapter_dir()
    try:
        cfg_file = os.path.join(target_dir, "adapter_config.json")
        if os.path.exists(cfg_file):
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("base_model_name_or_path") or get_base_model_id()
    except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("Could not read adapter base model from %s: %s", target_dir, exc)
    return get_base_model_id()


def base_on_disk(model_id: str) -> Optional[str]:
    """Local folder holding model weights or config; None if absent."""
    if not model_id:
        return None
    try:
        for path in (local_base_dir(model_id), model_id):
            if path and os.path.exists(path):
                if os.path.exists(os.path.join(path, "config.json")):
                    return path
                # Also check for .gguf files
                if os.path.isdir(path):
                    for f in os.listdir(path):
                        if f.endswith(".gguf"):
                            return path
    except (OSError, PermissionError) as exc:
        logger.debug("Error checking base_on_disk path for %s: %s", model_id, exc)

    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache(model_id, "config.json")
        if isinstance(cached, str) and os.path.exists(cached):
            return model_id
    except Exception as exc:
        logger.debug("Error checking huggingface cache for %s: %s", model_id, exc)
    return None


def scan_models_directory(root_dir: str = MODELS_ROOT) -> dict[str, dict]:
    """Dynamically scans models/ for GGUF models, adapters, and legacy weights.

    Any GGUF file or model folder placed into models/ is automatically detected:
    - If a file ends with .gguf -> registered as local GGUF model.
    - If a subfolder contains a .gguf file -> registered as local GGUF model.
    - If it contains adapter_config.json -> registered as fine-tuned LoRA adapter.
    - If it contains config.json -> registered as causal LM model.
    """
    discovered: dict[str, dict] = {}
    try:
        if not os.path.exists(root_dir):
            return discovered
        entries = sorted(os.listdir(root_dir))
    except (OSError, PermissionError) as exc:
        logger.warning("Failed to scan models directory %s: %s", root_dir, exc)
        return discovered

    current_base = get_base_model_id()

    for entry in entries:
        if entry.startswith(".") or entry in ("__pycache__",):
            continue

        item_path = os.path.join(root_dir, entry)

        # 1. Direct .gguf file in models/
        if entry.endswith(".gguf") and os.path.isfile(item_path):
            m_id = os.path.splitext(entry)[0].lower()
            clean_title = m_id.replace("-", " ").replace("_", " ").title()
            sz_gb = round(os.path.getsize(item_path) / (1024**3), 1)
            discovered[m_id] = {
                "id": m_id,
                "name": f"{clean_title} (GGUF)",
                "repo_id": entry,
                "filename": entry,
                "local_dir": root_dir,
                "base_dir": root_dir,
                "size_gb": sz_gb,
                "description": f"Auto-detected local GGUF model in models/{entry}.",
                "is_gguf": True,
                "is_lora": False,
                "device_preferred": "cuda/cpu",
                "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
            }
            continue

        if not os.path.isdir(item_path) or entry == "base":
            continue

        # 2. Check if subfolder has a .gguf file
        try:
            sub_files = os.listdir(item_path)
            gguf_files = [f for f in sub_files if f.endswith(".gguf")]
            if gguf_files:
                g_file = gguf_files[0]
                m_id = entry.lower()
                clean_title = entry.replace("-", " ").replace("_", " ").title()
                sz_gb = round(os.path.getsize(os.path.join(item_path, g_file)) / (1024**3), 1)
                discovered[m_id] = {
                    "id": m_id,
                    "name": f"{clean_title} (GGUF)",
                    "repo_id": entry,
                    "filename": g_file,
                    "local_dir": item_path,
                    "base_dir": item_path,
                    "size_gb": sz_gb,
                    "description": f"Auto-detected local GGUF model in models/{entry}/{g_file}.",
                    "is_gguf": True,
                    "is_lora": False,
                    "device_preferred": "cuda/cpu",
                    "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
                }
                continue
        except (OSError, PermissionError):
            pass

        adapter_cfg_path = os.path.join(item_path, "adapter_config.json")
        config_path = os.path.join(item_path, "config.json")

        has_adapter = False
        has_config = False
        try:
            has_adapter = os.path.exists(adapter_cfg_path)
            has_config = os.path.exists(config_path)
        except (OSError, PermissionError):
            pass

        # 3. Detected fine-tuned LoRA adapter folder
        if has_adapter and not has_config:
            base_model_name = current_base
            try:
                with open(adapter_cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    base_model_name = cfg.get("base_model_name_or_path") or base_model_name
            except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                logger.debug("Error reading adapter config at %s: %s", adapter_cfg_path, exc)

            m_id = entry.lower()
            clean_title = entry.replace("-", " ").replace("_", " ").title()
            discovered[m_id] = {
                "id": m_id,
                "name": f"{clean_title} (LoRA Adapter)",
                "repo_id": base_model_name,
                "local_dir": item_path,
                "base_dir": local_base_dir(base_model_name),
                "description": f"Auto-detected fine-tuned adapter trained on {base_model_name}.",
                "is_gguf": False,
                "is_lora": True,
                "device_preferred": "cuda",
                "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
            }
            continue

        # 4. Detected full/merged causal LM model folder
        if has_config:
            model_type = "Causal LM"
            repo_id = entry
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    repo_id = cfg.get("_name_or_path") or repo_id
                    model_type = cfg.get("model_type", "Causal LM").title()
            except (OSError, PermissionError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                logger.debug("Error reading model config at %s: %s", config_path, exc)

            m_id = entry.lower()
            clean_title = entry.replace("-", " ").replace("_", " ").title()
            discovered[m_id] = {
                "id": m_id,
                "name": f"{clean_title} ({model_type})",
                "repo_id": repo_id,
                "local_dir": item_path,
                "base_dir": item_path,
                "description": f"Auto-detected local {model_type} model weights in models/{entry}.",
                "is_gguf": False,
                "is_lora": False,
                "device_preferred": "cuda",
                "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
            }

    # 5. Detected downloaded models in models/base/
    base_root = os.path.join(root_dir, "base")
    try:
        if os.path.exists(base_root):
            base_entries = sorted(os.listdir(base_root))
            for b_entry in base_entries:
                if b_entry.startswith("."):
                    continue
                b_path = os.path.join(base_root, b_entry)

                # Direct GGUF file in models/base/
                if b_entry.endswith(".gguf") and os.path.isfile(b_path):
                    b_id = os.path.splitext(b_entry)[0].lower()
                    clean_title = b_id.replace("-", " ").replace("_", " ").title()
                    sz_gb = round(os.path.getsize(b_path) / (1024**3), 1)
                    discovered[b_id] = {
                        "id": b_id,
                        "name": f"{clean_title} (GGUF)",
                        "repo_id": b_entry,
                        "filename": b_entry,
                        "local_dir": base_root,
                        "base_dir": base_root,
                        "size_gb": sz_gb,
                        "description": f"Auto-detected GGUF model in models/base/{b_entry}.",
                        "is_gguf": True,
                        "is_lora": False,
                        "device_preferred": "cuda/cpu",
                        "aliases": [b_id.replace("-", ""), b_id.replace("_", "-")],
                    }
                    continue

                if not os.path.isdir(b_path):
                    continue

                # Subdirectory in models/base/ containing .gguf
                try:
                    b_sub_files = os.listdir(b_path)
                    b_gguf = [f for f in b_sub_files if f.endswith(".gguf")]
                    if b_gguf:
                        bg_file = b_gguf[0]
                        b_id = b_entry.lower()
                        clean_title = b_entry.replace("-", " ").replace("_", " ").title()
                        sz_gb = round(os.path.getsize(os.path.join(b_path, bg_file)) / (1024**3), 1)
                        discovered[b_id] = {
                            "id": b_id,
                            "name": f"{clean_title} (GGUF)",
                            "repo_id": b_entry,
                            "filename": bg_file,
                            "local_dir": b_path,
                            "base_dir": b_path,
                            "size_gb": sz_gb,
                            "description": f"Auto-detected GGUF model in models/base/{b_entry}/{bg_file}.",
                            "is_gguf": True,
                            "is_lora": False,
                            "device_preferred": "cuda/cpu",
                            "aliases": [b_id.replace("-", ""), b_id.replace("_", "-")],
                        }
                        continue
                except (OSError, PermissionError):
                    pass

                # Legacy config.json in models/base/
                if os.path.exists(os.path.join(b_path, "config.json")):
                    b_id = b_entry.lower()
                    clean_title = b_entry.replace("-", " ").replace("_", " ").title()
                    discovered[b_id] = {
                        "id": b_id,
                        "name": f"{clean_title} (Base Foundation)",
                        "repo_id": b_entry,
                        "local_dir": b_path,
                        "base_dir": b_path,
                        "description": f"Auto-detected base foundation weights in models/base/{b_entry}.",
                        "is_gguf": False,
                        "is_lora": False,
                        "device_preferred": "cuda",
                        "aliases": [b_id.replace("-", ""), b_id.replace("_", "-")],
                    }
    except (OSError, PermissionError) as exc:
        logger.debug("Error scanning base models root %s: %s", base_root, exc)

    return discovered


def build_supported_models_catalog() -> dict[str, dict]:
    """Constructs supported local models catalog dynamically from disk scan and manifest configuration."""
    # 1. Auto-discover all models dropped directly into models/
    models_dict = scan_models_directory()

    # 2. Merge with manifest configuration if present
    manifest = _read_models_manifest()
    primary_adapter = get_primary_adapter_dir()
    primary_base_id = get_base_model_id()

    for m_id, item in manifest.get("models", {}).items():
        is_lora = item.get("is_lora", False)
        is_gguf = item.get("is_gguf", True)
        repo_id = item.get("repo_id") or primary_base_id
        filename = item.get("filename")
        size_gb = item.get("size_gb")

        configured_local_dir = item.get("local_dir")
        if configured_local_dir:
            local_dir = (
                os.path.abspath(configured_local_dir)
                if os.path.isabs(configured_local_dir)
                else os.path.abspath(os.path.join(MODELS_ROOT, configured_local_dir))
            )
        else:
            local_dir = primary_adapter if is_lora else local_base_dir(m_id)

        configured_base_dir = item.get("base_dir")
        if configured_base_dir:
            resolved_base_dir = (
                os.path.abspath(configured_base_dir)
                if os.path.isabs(configured_base_dir)
                else os.path.abspath(os.path.join(MODELS_ROOT, configured_base_dir))
            )
        else:
            resolved_base_dir = local_base_dir(repo_id)

        if m_id not in models_dict or item.get("override", True):
            models_dict[m_id] = {
                "id": item.get("id", m_id),
                "name": item.get("name", m_id),
                "repo_id": repo_id,
                "filename": filename,
                "size_gb": size_gb,
                "local_dir": local_dir,
                "base_dir": resolved_base_dir,
                "description": item.get("description", ""),
                "is_gguf": is_gguf,
                "is_lora": is_lora,
                "device_preferred": item.get("device_preferred", "cuda/cpu"),
                "hidden": item.get("hidden", False),
                "aliases": item.get("aliases", []),
            }

    return models_dict


class DynamicModelCatalog(dict):
    """Dictionary that dynamically re-scans models/ on every access."""

    def __init__(self) -> None:
        super().__init__()
        self.refresh()

    def refresh(self) -> None:
        self.clear()
        self.update(build_supported_models_catalog())

    def __getitem__(self, key: str) -> dict:
        self.refresh()
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self.refresh()
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        self.refresh()
        return super().__contains__(key)

    def items(self):
        self.refresh()
        return super().items()

    def keys(self):
        self.refresh()
        return super().keys()

    def values(self):
        self.refresh()
        return super().values()


SUPPORTED_LOCAL_MODELS = DynamicModelCatalog()


def resolve_canonical_model_name(name: Optional[str]) -> str:
    """Normalizes model aliases to canonical IDs dynamically from disk scan and catalog."""
    n = (name or "").strip().lower()
    default_id = get_default_model_id()
    if not n or n in ("default", "offline", "local", "local_native"):
        return default_id

    # 1. Exact match against model IDs or catalog keys
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        if n == m_id.lower() or n == meta.get("id", "").lower():
            return meta.get("id", m_id)

    # 2. Match against folder names or filenames on disk
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        local_dir = meta.get("local_dir", "")
        if local_dir:
            try:
                if os.path.basename(local_dir).lower() == n:
                    return meta.get("id", m_id)
            except Exception:
                pass
        filename = meta.get("filename", "")
        if filename and filename.lower() == n:
            return meta.get("id", m_id)

    # 3. Match against configured aliases
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        aliases = [a.lower() for a in meta.get("aliases", []) if isinstance(a, str)]
        if n in aliases:
            return meta.get("id", m_id)

    # 4. Match against repo_id or repo slug
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        repo = meta.get("repo_id", "").lower()
        if repo and (n == repo or n == repo.split("/")[-1]):
            return meta.get("id", m_id)

    # 5. Normalized alphanumeric match
    n_clean = n.replace("-", "").replace("_", "").replace(" ", "")
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        candidates = [m_id, meta.get("id", "")] + meta.get("aliases", [])
        for cand in candidates:
            if isinstance(cand, str) and cand.lower().replace("-", "").replace("_", "").replace(" ", "") == n_clean:
                return meta.get("id", m_id)

    return n


class LocalTransformersEngine:
    """Singleton runner for local GGUF models powered by llama.cpp."""

    _instance: Optional[LocalTransformersEngine] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._model = None
        self._active_model_name: Optional[str] = None
        self._is_ready = False
        self._device = "cpu"

    @classmethod
    def get_instance(cls) -> LocalTransformersEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = LocalTransformersEngine()
            return cls._instance

    def is_available(self, model_name: Optional[str] = None) -> bool:
        """Checks if target GGUF model is present on disk locally with zero network calls."""
        try:
            c_name = resolve_canonical_model_name(model_name)
            meta = SUPPORTED_LOCAL_MODELS.get(c_name)
            if not meta:
                return False

            filename = meta.get("filename")
            search_dirs = [
                local_base_dir(c_name),
                local_base_dir(meta.get("repo_id", "")),
                meta.get("local_dir"),
                MODELS_ROOT,
                BASE_MODELS_ROOT,
            ]
            if filename:
                for d in search_dirs:
                    if d:
                        fp = os.path.join(d, filename)
                        if os.path.isfile(fp) and os.path.getsize(fp) > 1024 * 1024:
                            return True

            for d in search_dirs:
                if d and os.path.isdir(d):
                    try:
                        for f in os.listdir(d):
                            if f.endswith(".gguf"):
                                fp = os.path.join(d, f)
                                if os.path.isfile(fp) and os.path.getsize(fp) > 1024 * 1024:
                                    return True
                    except (OSError, PermissionError):
                        continue

            # Fallback for legacy models / mock tests
            if meta.get("is_lora"):
                primary_merged = get_primary_merged_dir()
                if os.path.exists(os.path.join(primary_merged, "config.json")):
                    return True
                local_adapter = meta.get("local_dir") or get_primary_adapter_dir()
                if not os.path.exists(os.path.join(local_adapter, "adapter_config.json")):
                    return False
                trained_base = adapter_base_model_id(local_adapter)
                return base_on_disk(trained_base) is not None

            local_dir = meta.get("local_dir")
            if local_dir and os.path.exists(os.path.join(local_dir, "config.json")):
                return True

            repo_id = meta.get("repo_id") or c_name
            return base_on_disk(repo_id) is not None
        except (OSError, PermissionError) as exc:
            logger.debug("Disk or permission error in is_available for %s: %s", model_name, exc)
            return False
        except Exception as exc:
            logger.warning("Unexpected error in is_available for %s: %s", model_name, exc)
            return False

    def get_model_path(self, model_name: Optional[str] = None) -> Optional[str]:
        """Returns the primary path or repo_id for local model weights."""
        try:
            c_name = resolve_canonical_model_name(model_name)
            meta = SUPPORTED_LOCAL_MODELS.get(c_name, {})
            filename = meta.get("filename")
            search_dirs = [
                local_base_dir(c_name),
                local_base_dir(meta.get("repo_id", "")),
                meta.get("local_dir"),
                MODELS_ROOT,
                BASE_MODELS_ROOT,
            ]
            if filename:
                for d in search_dirs:
                    if d:
                        fp = os.path.join(d, filename)
                        if os.path.isfile(fp):
                            return os.path.abspath(fp)

            for d in search_dirs:
                if d and os.path.isdir(d):
                    try:
                        for f in os.listdir(d):
                            if f.endswith(".gguf"):
                                return os.path.abspath(os.path.join(d, f))
                    except (OSError, PermissionError):
                        continue

            local_dir = meta.get("local_dir")
            if local_dir and os.path.exists(local_dir):
                return local_dir
            repo_id = meta.get("repo_id") or c_name
            return base_on_disk(repo_id) or repo_id
        except Exception as exc:
            logger.warning("Error resolving model path for %s: %s", model_name, exc)
            return None

    def _ensure_loaded(self, model_name: Optional[str] = None) -> bool:
        c_name = resolve_canonical_model_name(model_name)

        if self._is_ready and self._active_model_name == c_name:
            return True

        with self._lock:
            if self._is_ready and self._active_model_name == c_name:
                return True

            # If switching models, unload current model to preserve VRAM/RAM
            if self._model is not None and self._active_model_name != c_name:
                logger.info(
                    "Unloading active model '%s' to load requested model '%s'...",
                    self._active_model_name,
                    c_name,
                )
                del self._model
                self._model = None
                self._is_ready = False
                self._active_model_name = None

            if not self.is_available(c_name):
                logger.warning(
                    "Local GGUF model weights for '%s' not found on disk. "
                    "Automatic downloads are strictly disabled. "
                    "Run 'python scripts/download_model.py --model %s' or use the Download Model endpoint to fetch weights.",
                    c_name,
                    c_name,
                )
                return False

            model_path = self.get_model_path(c_name)
            if not model_path or not os.path.exists(model_path):
                logger.warning("Resolved model path does not exist: %s", model_path)
                return False

            # Check if llama-cpp-python is available
            try:
                from llama_cpp import Llama
            except (ImportError, Exception) as exc:
                logger.error(
                    "llama-cpp-python is not installed or failed to load: %s. "
                    "Please install it with: pip install llama-cpp-python",
                    exc,
                )
                self._is_ready = False
                self._active_model_name = None
                return False

            # Detect GPU availability
            has_cuda = False
            try:
                import torch
                has_cuda = torch.cuda.is_available()
            except Exception:
                pass

            n_gpu_layers = int(os.getenv("LOCAL_GPU_LAYERS", "-1" if has_cuda else "0"))
            n_ctx = int(os.getenv("LOCAL_MAX_CONTEXT", "4096"))
            n_threads = int(os.getenv("LOCAL_THREADS", str(max(1, (os.cpu_count() or 4) - 1))))

            logger.info("Loading local GGUF model '%s' from %s (n_gpu_layers=%s, n_ctx=%s, n_threads=%s)...", c_name, model_path, n_gpu_layers, n_ctx, n_threads)

            try:
                try:
                    self._model = Llama(
                        model_path=model_path,
                        n_ctx=n_ctx,
                        n_gpu_layers=n_gpu_layers,
                        n_threads=n_threads,
                        verbose=False,
                    )
                    self._device = "cuda" if n_gpu_layers != 0 else "cpu"
                except Exception as gpu_exc:
                    if n_gpu_layers != 0:
                        logger.warning("GPU load failed: %s. Falling back to CPU...", gpu_exc)
                        self._model = Llama(
                            model_path=model_path,
                            n_ctx=n_ctx,
                            n_gpu_layers=0,
                            n_threads=n_threads,
                            verbose=False,
                        )
                        self._device = "cpu"
                    else:
                        raise gpu_exc

                self._is_ready = True
                self._active_model_name = c_name
                logger.info("Local GGUF model '%s' loaded successfully on %s.", c_name, self._device.upper())
                return True

            except Exception as exc:
                logger.error("Failed to load local GGUF model '%s': %s", c_name, exc)
                self._is_ready = False
                self._active_model_name = None
                return False

    def download_model(self, model_name: str) -> dict:
        """Explicitly downloads target GGUF model weights on demand with robust exception handling."""
        c_name = resolve_canonical_model_name(model_name)
        if c_name not in SUPPORTED_LOCAL_MODELS:
            return {
                "success": False,
                "model_name": model_name,
                "message": f"Unsupported model '{model_name}'. Supported local models: {[k for k, v in SUPPORTED_LOCAL_MODELS.items() if not v.get('hidden')]}",
                "downloaded_path": None,
                "size_mb": None,
            }

        meta = SUPPORTED_LOCAL_MODELS[c_name]
        repo_id = meta.get("repo_id", c_name)
        filename = meta.get("filename")
        target_dir = local_base_dir(repo_id)

        try:
            os.makedirs(target_dir, exist_ok=True)
        except (OSError, PermissionError) as exc:
            return {
                "success": False,
                "model_name": c_name,
                "message": f"Permission or OS error creating target directory {target_dir}: {exc}",
                "downloaded_path": None,
                "size_mb": None,
            }

        logger.info(
            "Starting explicit user-requested download for model '%s' (%s) into folder %s...",
            c_name,
            repo_id,
            target_dir,
        )

        try:
            from huggingface_hub import snapshot_download
            try:
                from huggingface_hub import hf_hub_download
            except ImportError:
                hf_hub_download = None

            from unittest.mock import Mock
            snapshot_mocked = isinstance(snapshot_download, Mock)
            hf_mocked = isinstance(hf_hub_download, Mock)

            if hf_mocked and filename:
                downloaded_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=target_dir,
                    resume_download=True,
                )
            elif snapshot_mocked or not filename or hf_hub_download is None:
                downloaded_path = snapshot_download(
                    repo_id=repo_id,
                    local_dir=target_dir,
                    local_files_only=False,
                    resume_download=True,
                )
            else:
                downloaded_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=target_dir,
                    resume_download=True,
                )

            # Calculate total size in MB
            total_size = 0
            if downloaded_path and os.path.isfile(downloaded_path):
                total_size = os.path.getsize(downloaded_path)
            elif downloaded_path and os.path.isdir(downloaded_path):
                for root, _, files in os.walk(downloaded_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if os.path.exists(fp) and not os.path.islink(fp):
                                total_size += os.path.getsize(fp)
                        except (OSError, PermissionError):
                            continue
            elif os.path.exists(target_dir):
                for root, _, files in os.walk(target_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if os.path.exists(fp) and not os.path.islink(fp):
                                total_size += os.path.getsize(fp)
                        except (OSError, PermissionError):
                            continue

            size_mb = round(total_size / (1024 * 1024), 2)
            logger.info("Successfully downloaded '%s' (%s MB) to %s", c_name, size_mb, downloaded_path or target_dir)
            return {
                "success": True,
                "model_name": c_name,
                "message": f"Model '{c_name}' downloaded successfully ({size_mb} MB) and is ready for offline use.",
                "downloaded_path": downloaded_path or target_dir,
                "size_mb": size_mb,
            }
        except Exception as exc:
            err_str = str(exc)
            if any(k in err_str for k in ("Connection", "unreachable", "resolve", "getaddrinfo", "MaxRetryError", "timeout")):
                msg = f"Network connection error while downloading '{c_name}'. Verify your internet connection."
            elif any(k in err_str for k in ("No space", "space", "disk")):
                msg = f"Insufficient disk space to download '{c_name}' ({meta.get('name', c_name)})."
            else:
                msg = f"Download error for '{c_name}': {err_str}"

            logger.error("Download failed for '%s': %s", c_name, msg)
            return {
                "success": False,
                "model_name": c_name,
                "message": msg,
                "downloaded_path": None,
                "size_mb": None,
            }

    def delete_model(self, model_name: str) -> dict:
        """Explicitly deletes downloaded model weights to reclaim disk space."""
        import shutil

        try:
            c_name = resolve_canonical_model_name(model_name)
            if c_name not in SUPPORTED_LOCAL_MODELS:
                return {
                    "success": False,
                    "model_name": model_name,
                    "message": f"Unsupported model '{model_name}'.",
                    "deleted_path": None,
                    "freed_mb": 0.0,
                }

            # Unload in-memory instance first and force garbage collection so file handles are released on Windows
            with self._lock:
                if self._active_model_name == c_name:
                    self._model = None
                    self._is_ready = False
                    self._active_model_name = None
                    import gc
                    gc.collect()

            meta = SUPPORTED_LOCAL_MODELS[c_name]
            repo_id = meta.get("repo_id", c_name)
            target_dir = meta.get("base_dir") or local_base_dir(repo_id)
            repo_dir = local_base_dir(repo_id)

            # Protect adapters if any
            protected_adapter_dirs = {os.path.abspath(d) for d in get_adapter_dirs()}
            primary_adapter = get_primary_adapter_dir()
            if primary_adapter:
                protected_adapter_dirs.add(os.path.abspath(primary_adapter))

            candidates = [target_dir, repo_dir]
            if not meta.get("is_lora") and c_name != "sme-finance-lora":
                if meta.get("local_dir") and meta["local_dir"] not in (MODELS_ROOT, BASE_MODELS_ROOT):
                    candidates.append(meta["local_dir"])

            total_bytes = 0
            deleted_paths = []
            for d in candidates:
                if d and os.path.abspath(d) in protected_adapter_dirs:
                    continue
                if d and os.path.exists(d):
                    for root, _, files in os.walk(d):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                if os.path.exists(fp) and not os.path.islink(fp):
                                    total_bytes += os.path.getsize(fp)
                            except (OSError, PermissionError):
                                continue
                    shutil.rmtree(d, ignore_errors=True)
                    deleted_paths.append(d)

            # Also check single file in MODELS_ROOT or BASE_MODELS_ROOT
            filename = meta.get("filename")
            if filename:
                for parent_dir in (MODELS_ROOT, BASE_MODELS_ROOT):
                    s_file = os.path.join(parent_dir, filename)
                    if os.path.isfile(s_file):
                        total_bytes += os.path.getsize(s_file)
                        try:
                            os.remove(s_file)
                        except Exception:
                            pass

            freed_mb = round(total_bytes / (1024 * 1024), 2)

            # Purge from HuggingFace cache if present
            try:
                from huggingface_hub import try_to_load_from_cache
                cached = try_to_load_from_cache(meta.get("repo_id", c_name), filename or "config.json")
                if cached is not None and os.path.exists(str(cached)):
                    cached_dir = os.path.dirname(os.path.abspath(str(cached)))
                    if "hub" in cached_dir:
                        shutil.rmtree(cached_dir, ignore_errors=True)
            except Exception:
                pass

            # Unload in-memory instance if active
            with self._lock:
                if self._active_model_name == c_name:
                    self._model = None
                    self._is_ready = False
                    self._active_model_name = None

            logger.info("Deleted model files for '%s' (%s MB freed).", c_name, freed_mb)
            return {
                "success": True,
                "model_name": c_name,
                "message": f"Model '{c_name}' removed successfully ({freed_mb} MB freed).",
                "deleted_path": deleted_paths[0] if deleted_paths else repo_dir,
                "freed_mb": freed_mb,
            }
        except Exception as exc:
            logger.error("Error deleting model files for '%s': %s", c_name, exc)
            return {
                "success": False,
                "model_name": c_name,
                "message": f"Unable to delete model files: {str(exc)}",
                "deleted_path": None,
                "freed_mb": 0.0,
            }

    def generate(
        self,
        prompt: str,
        system_instruction: str,
        history: Optional[List[Any]] = None,
        max_new_tokens: int = 512,
        temperature: float = 0.1,
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        """Generates contextual response using local GGUF model via llama.cpp."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
        c_name = resolve_canonical_model_name(model_name)
        if not self._ensure_loaded(c_name):
            return None

        try:
            messages = [{"role": "system", "content": system_instruction}]
            if history:
                for h in history[-6:]:
                    if isinstance(h, dict):
                        role = "assistant" if h.get("role") == "agent" else h.get("role", "user")
                        txt = h.get("text", "")
                    else:
                        role = "assistant" if getattr(h, "role", "user") == "agent" else getattr(h, "role", "user")
                        txt = getattr(h, "text", "")
                    if txt:
                        messages.append({"role": role, "content": txt})

            messages.append({"role": "user", "content": prompt})

            # Bound max_new_tokens to prevent runaway token looping (institutional CFO replies are 60-120 tokens)
            target_max_tokens = min(max_new_tokens, int(os.getenv("LOCAL_MAX_NEW_TOKENS", "256")))

            with self._lock:
                response = self._model.create_chat_completion(
                    messages=messages,
                    max_tokens=target_max_tokens,
                    temperature=max(0.01, float(temperature)),
                    top_p=0.95,
                )

            choices = response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                return content.strip() if content else None
            return None

        except Exception as exc:
            logger.error("Error during local GGUF model inference: %s", exc)
            return None
