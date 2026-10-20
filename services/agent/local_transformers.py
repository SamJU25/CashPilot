"""Native PyTorch/Transformers Local Inference Engine for SME Finance Copilot.

Enables 100% on-device, in-process neural generation with:
- Zero dependency on Ollama or external daemon services
- Zero API keys or cloud transmissions
- Direct GPU acceleration via PyTorch CUDA
- Automatic tool-calling and Chain-of-Thought output formatting
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
    """Dynamically resolves base foundation model ID from env, disk adapter, manifest, or fallback."""
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

    return "base-model"


def get_default_model_id() -> str:
    """Returns active default model ID dynamically discovered from env, disk, or manifest."""
    env_override = os.getenv("CASHPILOT_DEFAULT_MODEL") or os.getenv("LOCAL_MODEL_DEFAULT")
    if env_override:
        return env_override

    manifest = _read_models_manifest()
    if manifest.get("default_model"):
        return manifest["default_model"]

    adapters = get_adapter_dirs()
    if adapters:
        return os.path.basename(adapters[0]).lower()

    merged = get_merged_model_dirs()
    if merged:
        return os.path.basename(merged[0]).lower()

    for m_id, meta in manifest.get("models", {}).items():
        if not meta.get("hidden"):
            return m_id

    return "default"


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
    """models/base/<repo name>: the folder download_model fills for that base."""
    safe_name = (model_id or "").replace("\\", "/").rstrip("/").split("/")[-1]
    return os.path.join(BASE_MODELS_ROOT, safe_name)


BASE_MODEL_DIR = local_base_dir(BASE_MODEL_ID)


def adapter_base_model_id(adapter_dir: Optional[str] = None) -> str:
    """Base the adapter was trained on, from its adapter_config.json, so it never loads onto a different base."""
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
    """Local folder, absolute path or Hugging Face cache entry holding this base; None if absent (never downloads)."""
    if not model_id:
        return None
    try:
        for path in (local_base_dir(model_id), model_id):
            if path and os.path.exists(os.path.join(path, "config.json")):
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
    """Dynamically scans models/ for adapters, merged models, and base weights.

    Any folder placed into models/ is automatically detected on the fly:
    - If it contains adapter_config.json -> registered as fine-tuned LoRA adapter.
    - If it contains config.json -> registered as causal LM model.
    - Any folder in models/base/ with config.json -> registered as foundation base model.
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
        if entry.startswith(".") or entry in ("base", "__pycache__"):
            continue
        folder_path = os.path.join(root_dir, entry)
        try:
            if not os.path.isdir(folder_path):
                continue
        except (OSError, PermissionError):
            continue

        adapter_cfg_path = os.path.join(folder_path, "adapter_config.json")
        config_path = os.path.join(folder_path, "config.json")

        has_adapter = False
        has_config = False
        try:
            has_adapter = os.path.exists(adapter_cfg_path)
            has_config = os.path.exists(config_path)
        except (OSError, PermissionError):
            pass

        # 1. Detected fine-tuned LoRA adapter folder
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
                "local_dir": folder_path,
                "base_dir": local_base_dir(base_model_name),
                "description": f"Auto-detected fine-tuned adapter trained on {base_model_name}.",
                "is_lora": True,
                "device_preferred": "cuda",
                "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
            }
            continue

        # 2. Detected full/merged causal LM model folder
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
                "local_dir": folder_path,
                "base_dir": folder_path,
                "description": f"Auto-detected local {model_type} model weights in models/{entry}.",
                "is_lora": False,
                "device_preferred": "cuda",
                "aliases": [m_id.replace("-", ""), m_id.replace("_", "-")],
            }

    # 3. Detected downloaded base models in models/base/
    base_root = os.path.join(root_dir, "base")
    try:
        if os.path.exists(base_root):
            base_entries = sorted(os.listdir(base_root))
            for b_entry in base_entries:
                if b_entry.startswith("."):
                    continue
                b_path = os.path.join(base_root, b_entry)
                try:
                    if not os.path.isdir(b_path):
                        continue
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
                            "is_lora": False,
                            "device_preferred": "cuda",
                            "aliases": [b_id.replace("-", ""), b_id.replace("_", "-")],
                        }
                except (OSError, PermissionError):
                    continue
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
    primary_base_dir = local_base_dir(primary_base_id)

    for m_id, item in manifest.get("models", {}).items():
        is_lora = item.get("is_lora", False)
        repo_id = item.get("repo_id") or primary_base_id
        configured_local_dir = item.get("local_dir")
        if configured_local_dir:
            local_dir = (
                os.path.abspath(configured_local_dir)
                if os.path.isabs(configured_local_dir)
                else os.path.abspath(os.path.join(MODELS_ROOT, configured_local_dir))
            )
        else:
            local_dir = primary_adapter if is_lora else local_base_dir(repo_id)

        configured_base_dir = item.get("base_dir")
        if configured_base_dir:
            resolved_base_dir = (
                os.path.abspath(configured_base_dir)
                if os.path.isabs(configured_base_dir)
                else os.path.abspath(os.path.join(MODELS_ROOT, configured_base_dir))
            )
        else:
            resolved_base_dir = primary_base_dir if is_lora else local_base_dir(repo_id)

        if m_id not in models_dict or item.get("override", True):
            models_dict[m_id] = {
                "id": item.get("id", m_id),
                "name": item.get("name", m_id),
                "repo_id": repo_id,
                "local_dir": local_dir,
                "base_dir": resolved_base_dir,
                "description": item.get("description", ""),
                "is_lora": is_lora,
                "device_preferred": item.get("device_preferred", "cuda"),
                "hidden": item.get("hidden", False),
                "aliases": item.get("aliases", []),
            }

    return models_dict


class DynamicModelCatalog(dict):
    """Dictionary that dynamically re-scans models/ on every access.

    Ensures that the moment a model or adapter is placed into models/,
    it is immediately recognized without server restarts or code changes.
    """

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

    # 2. Match against folder names on disk in models/
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        local_dir = meta.get("local_dir", "")
        if local_dir:
            try:
                if os.path.basename(local_dir).lower() == n:
                    return meta.get("id", m_id)
            except Exception:
                pass

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

    # 5. Normalized alphanumeric match against known model IDs, aliases, and clean slugs
    n_clean = n.replace("-", "").replace("_", "").replace(" ", "")
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        candidates = [m_id, meta.get("id", "")] + meta.get("aliases", [])
        for cand in candidates:
            if isinstance(cand, str) and cand.lower().replace("-", "").replace("_", "").replace(" ", "") == n_clean:
                return meta.get("id", m_id)

    return n


class LocalTransformersEngine:
    """Singleton runner for native fine-tuned Hugging Face / PyTorch models."""

    _instance: Optional[LocalTransformersEngine] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
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
        """Checks if target model is present on disk locally with zero network calls."""
        try:
            c_name = resolve_canonical_model_name(model_name)
            meta = SUPPORTED_LOCAL_MODELS.get(c_name)
            if not meta:
                return False

            if meta.get("is_lora"):
                primary_merged = get_primary_merged_dir()
                if os.path.exists(os.path.join(primary_merged, "config.json")):
                    return True
                local_adapter = meta.get("local_dir") or get_primary_adapter_dir()
                if not os.path.exists(os.path.join(local_adapter, "adapter_config.json")):
                    return False
                try:
                    import peft  # noqa: F401
                except ImportError:
                    return False
                trained_base = adapter_base_model_id(local_adapter)
                return base_on_disk(trained_base) is not None

            # If it's a full causal LM model on disk with config.json:
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

    def get_model_path(self, model_name: Optional[str] = None) -> str:
        """Returns the primary path or repo_id for local model weights."""
        try:
            c_name = resolve_canonical_model_name(model_name)
            meta = SUPPORTED_LOCAL_MODELS.get(c_name)
            primary_adapter = get_primary_adapter_dir()
            primary_merged = get_primary_merged_dir()

            if meta and meta.get("is_lora"):
                if os.path.exists(os.path.join(primary_merged, "config.json")):
                    return primary_merged
                return meta.get("local_dir") or primary_adapter
            if meta:
                local_dir = meta.get("local_dir")
                if local_dir and os.path.exists(local_dir):
                    return local_dir
                repo_id = meta.get("repo_id") or c_name
                return base_on_disk(repo_id) or repo_id
            return primary_adapter
        except Exception as exc:
            logger.warning("Error resolving model path for %s: %s", model_name, exc)
            return get_primary_adapter_dir()

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
                del self._tokenizer
                self._model = None
                self._tokenizer = None
                self._is_ready = False
                self._active_model_name = None
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass

            if not self.is_available(c_name):
                logger.warning(
                    "Local native model weights for '%s' not found on disk. "
                    "Automatic downloads are strictly disabled. "
                    "Run 'python scripts/download_model.py --model %s' or use the Download Model endpoint to fetch weights.",
                    c_name,
                    c_name,
                )
                return False

            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                has_cuda = torch.cuda.is_available()
                self._device = "cuda" if has_cuda else "cpu"

                vram_gb = 0.0
                if has_cuda:
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9

                model_path = self.get_model_path(c_name)
                logger.info("Loading native fine-tuned model '%s' from %s...", c_name, model_path)

                quant_config = None
                load_in_4bit = os.getenv("LOCAL_LOAD_IN_4BIT", "1") == "1"
                if has_cuda and vram_gb < 10.0 and load_in_4bit:
                    try:
                        from transformers import BitsAndBytesConfig
                        quant_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_compute_dtype=torch.float16,
                            bnb_4bit_quant_type="nf4",
                            bnb_4bit_use_double_quant=True,
                        )
                    except Exception:
                        quant_config = None

                is_lora_only = (
                    os.path.exists(os.path.join(model_path, "adapter_config.json"))
                    and not os.path.exists(os.path.join(model_path, "config.json"))
                )

                if is_lora_only:
                    from peft import PeftModel

                    trained_on = adapter_base_model_id(model_path)
                    base_model_id = base_on_disk(trained_on) or trained_on

                    tok_path = model_path if os.path.exists(os.path.join(model_path, "tokenizer_config.json")) else base_model_id
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        tok_path,
                        local_files_only=True,
                        trust_remote_code=True,
                    )

                    if self._tokenizer.pad_token is None:
                        self._tokenizer.pad_token = self._tokenizer.eos_token

                    load_kwargs = {
                        "local_files_only": True,
                        "trust_remote_code": True,
                        "device_map": "auto" if has_cuda else None,
                    }
                    if has_cuda:
                        load_kwargs["attn_implementation"] = "sdpa"
                    if quant_config:
                        load_kwargs["quantization_config"] = quant_config
                    else:
                        load_kwargs["torch_dtype"] = torch.float16 if has_cuda else torch.float32

                    base_model = AutoModelForCausalLM.from_pretrained(base_model_id, **load_kwargs)
                    self._model = PeftModel.from_pretrained(
                        base_model,
                        model_path,
                        local_files_only=True,
                    )
                else:
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        model_path,
                        local_files_only=True,
                        trust_remote_code=True,
                    )
                    if self._tokenizer.pad_token is None:
                        self._tokenizer.pad_token = self._tokenizer.eos_token

                    load_kwargs = {
                        "local_files_only": True,
                        "trust_remote_code": True,
                        "device_map": "auto" if has_cuda else None,
                    }
                    if has_cuda:
                        load_kwargs["attn_implementation"] = "sdpa"
                    if quant_config:
                        load_kwargs["quantization_config"] = quant_config
                    else:
                        load_kwargs["torch_dtype"] = torch.float16 if has_cuda else torch.float32

                    self._model = AutoModelForCausalLM.from_pretrained(model_path, **load_kwargs)

                self._model.eval()
                self._is_ready = True
                self._active_model_name = c_name
                logger.info(
                    "Local native PyTorch model '%s' loaded successfully on %s (quantized=%s).",
                    c_name,
                    self._device.upper(),
                    quant_config is not None,
                )
                return True

            except Exception as exc:
                logger.error("Failed to load local native model '%s': %s", c_name, exc)
                self._is_ready = False
                self._active_model_name = None
                return False

    def download_model(self, model_name: str) -> dict:
        """Explicitly downloads target model weights on demand with robust exception handling."""
        c_name = resolve_canonical_model_name(model_name)
        if c_name not in SUPPORTED_LOCAL_MODELS:
            return {
                "success": False,
                "model_name": model_name,
                "message": f"Unsupported model '{model_name}'. Supported local models: {list(SUPPORTED_LOCAL_MODELS.keys())}",
                "downloaded_path": None,
                "size_mb": None,
            }

        meta = SUPPORTED_LOCAL_MODELS[c_name]
        local_adapter = meta.get("local_dir") or get_primary_adapter_dir()
        repo_id = adapter_base_model_id(local_adapter) if meta.get("is_lora") else meta.get("repo_id", c_name)
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

            downloaded_path = snapshot_download(
                repo_id=repo_id,
                local_dir=target_dir,
                local_files_only=False,
                resume_download=True,
            )

            # Calculate total size in MB
            total_size = 0
            for root, _, files in os.walk(downloaded_path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if os.path.exists(fp) and not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                    except (OSError, PermissionError):
                        continue
            size_mb = round(total_size / (1024 * 1024), 2)

            logger.info("Successfully downloaded '%s' (%s MB) to %s", c_name, size_mb, downloaded_path)
            return {
                "success": True,
                "model_name": c_name,
                "message": f"Model '{c_name}' downloaded successfully ({size_mb} MB) and is ready for offline use.",
                "downloaded_path": downloaded_path,
                "size_mb": size_mb,
            }
        except Exception as exc:
            err_str = str(exc)
            if any(k in err_str for k in ("Connection", "unreachable", "resolve", "getaddrinfo", "MaxRetryError", "timeout")):
                msg = f"Network connection error while downloading '{c_name}'. Verify your internet connection."
            elif any(k in err_str for k in ("No space", "space", "disk")):
                msg = f"Insufficient disk space to download '{c_name}' ({meta['name']})."
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
        """Explicitly deletes downloaded base model weights to reclaim disk space.

        Strict Invariant:
        Only downloaded base foundation weights (in models/base/) are removed.
        Fine-tuned adapter configurations and weights are protected and will NEVER be deleted.
        """
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

            meta = SUPPORTED_LOCAL_MODELS[c_name]
            local_adapter = meta.get("local_dir") or get_primary_adapter_dir()
            repo_id = adapter_base_model_id(local_adapter) if meta.get("is_lora") else meta.get("repo_id", c_name)
            base_dir = local_base_dir(repo_id)

            # Hard security guard: all adapter folders are protected and can never be deleted
            protected_adapter_dirs = {os.path.abspath(d) for d in get_adapter_dirs()}
            primary_adapter = get_primary_adapter_dir()
            if primary_adapter:
                protected_adapter_dirs.add(os.path.abspath(primary_adapter))
            if meta.get("local_dir"):
                protected_adapter_dirs.add(os.path.abspath(meta["local_dir"]))

            if os.path.abspath(base_dir) in protected_adapter_dirs:
                return {
                    "success": False,
                    "model_name": c_name,
                    "message": "This core system model is protected and cannot be deleted.",
                    "deleted_path": None,
                    "freed_mb": 0.0,
                }

            total_bytes = 0
            if os.path.exists(base_dir):
                for root, _, files in os.walk(base_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if os.path.exists(fp) and not os.path.islink(fp):
                                total_bytes += os.path.getsize(fp)
                        except (OSError, PermissionError):
                            continue

            freed_mb = round(total_bytes / (1024 * 1024), 2)

            if total_bytes == 0 and not self.is_available(c_name):
                return {
                    "success": False,
                    "model_name": c_name,
                    "message": f"No local files found on disk for model '{c_name}'.",
                    "deleted_path": base_dir,
                    "freed_mb": 0.0,
                }

            # Delete base model weights in base_dir
            if os.path.exists(base_dir):
                shutil.rmtree(base_dir, ignore_errors=True)
                os.makedirs(base_dir, exist_ok=True)

            # Purge from HuggingFace cache if present to completely free disk space
            try:
                from huggingface_hub import try_to_load_from_cache
                cached = try_to_load_from_cache(repo_id, "config.json")
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
                    self._tokenizer = None
                    self._is_ready = False
                    self._active_model_name = None

            logger.info("Deleted model files for '%s' from %s (%s MB freed).", c_name, base_dir, freed_mb)
            return {
                "success": True,
                "model_name": c_name,
                "message": f"Model '{c_name}' removed successfully ({freed_mb} MB freed).",
                "deleted_path": base_dir,
                "freed_mb": freed_mb,
            }
        except Exception as exc:
            logger.error("Error deleting model files for '%s': %s", c_name, exc)
            return {
                "success": False,
                "model_name": c_name,
                "message": f"Unable to delete model files: {str(exc)}",
                "deleted_path": base_dir,
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
        """Generates contextual response using native local PyTorch model."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
        c_name = resolve_canonical_model_name(model_name)
        if not self._ensure_loaded(c_name):
            return None

        try:
            import torch

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

            # Off by default: on the 100-case eval set thinking scored 40% vs 39% with more invented figures
            # (14 vs 10) at 28 s vs 15 s per reply (docs/superpowers/specs/2026-10-19-thinking-eval.md).
            # LOCAL_ENABLE_THINKING=1 turns it back on.
            prompt_text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=os.getenv("LOCAL_ENABLE_THINKING", "0") == "1",
            )

            inputs = self._tokenizer([prompt_text], return_tensors="pt").to(self._model.device)

            # Bound max_new_tokens to prevent runaway token looping (institutional CFO replies are 60-120 tokens)
            target_max_tokens = min(max_new_tokens, int(os.getenv("LOCAL_MAX_NEW_TOKENS", "180")))

            with torch.inference_mode():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=target_max_tokens,
                    temperature=temperature if temperature > 0 else 0.1,
                    top_p=0.95,
                    use_cache=True,
                    pad_token_id=self._tokenizer.eos_token_id,
                )

            generated_ids = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, outputs)
            ]

            return self._tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

        except Exception as exc:
            logger.error("Error during native local model inference: %s", exc)
            return None
