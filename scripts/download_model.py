"""Standalone CLI utility to download and verify local SLM/LoRA models for CashPilot.

Enforces zero-silent-download architecture: models are only downloaded when
explicitly requested by the user via CLI or UI.
"""

import argparse
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.agent.local_transformers import (
    SUPPORTED_LOCAL_MODELS,
    LocalTransformersEngine,
    resolve_canonical_model_name,
)


def list_models(engine: LocalTransformersEngine) -> None:
    print("\n" + "=" * 56)
    print("  CashPilot by Blueprint -- Supported Local Models")
    print("=" * 56 + "\n")
    for m_id, meta in SUPPORTED_LOCAL_MODELS.items():
        if meta.get("hidden"):
            continue
        installed = engine.is_available(m_id)
        status_badge = "[INSTALLED & READY]" if installed else "[NOT DOWNLOADED]"
        print(f"* Model ID:     {m_id}")
        print(f"  Name:         {meta['name']}")
        print(f"  Status:       {status_badge}")
        print(f"  Target HW:    {meta['device_preferred'].upper()} ({meta['description']})")
        print(f"  HuggingFace:  {meta['repo_id']}")
        print("-" * 56)
    print()


def download_single_model(engine: LocalTransformersEngine, model_id: str) -> bool:
    canonical = resolve_canonical_model_name(model_id)
    if canonical not in SUPPORTED_LOCAL_MODELS:
        print(f"[ERROR] Unsupported model identifier: '{model_id}'")
        print(f"Available models: {list(SUPPORTED_LOCAL_MODELS.keys())}")
        return False

    meta = SUPPORTED_LOCAL_MODELS[canonical]
    print(f"\n[INFO] Checking status for model '{canonical}' ({meta['name']})...")

    if engine.is_available(canonical):
        print(f"[OK] Model '{canonical}' is already downloaded and ready on disk!")
        return True

    print(f"[INFO] Initiating explicit download for '{canonical}' from Hugging Face ({meta['repo_id']})...")
    print("[INFO] This may take a few moments depending on your network speed...")

    res = engine.download_model(canonical)
    if res["success"]:
        print(f"\n[SUCCESS] {res['message']}")
        print(f"[SUCCESS] Model files saved to: {res.get('downloaded_path')}")
        return True
    else:
        print(f"\n[ERROR] Download failed: {res['message']}")
        return False


def main() -> None:
    from services.agent.local_transformers import get_default_model_id
    default_id = get_default_model_id()
    supported_keys = [k for k, v in SUPPORTED_LOCAL_MODELS.items() if not v.get("hidden")]

    parser = argparse.ArgumentParser(
        description="Explicit Model Downloader for CashPilot (No Auto-Downloads)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Target model to download ({', '.join(repr(k) for k in supported_keys)}, or 'all')",
    )
    parser.add_argument(
        "--delete",
        type=str,
        default=None,
        help="Delete downloaded base model weights to free disk space (adapters are preserved)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all supported local models and their disk availability",
    )

    args = parser.parse_args()
    engine = LocalTransformersEngine.get_instance()

    if args.delete:
        canonical = resolve_canonical_model_name(args.delete)
        print(f"\n[INFO] Deleting downloaded base model weights for '{canonical}'...")
        res = engine.delete_model(canonical)
        if res["success"]:
            print(f"[SUCCESS] {res['message']}")
            sys.exit(0)
        else:
            print(f"[ERROR] {res['message']}")
            sys.exit(1)

    if args.list or (not args.model and len(sys.argv) == 1):
        list_models(engine)
        if not args.model:
            print("To download or verify a model, run:")
            print(f"  python scripts/download_model.py --model {default_id}")
            print("\nTo delete downloaded base weights to reclaim disk space:")
            print(f"  python scripts/download_model.py --delete {default_id}\n")
        return

    if args.model:
        if args.model.lower() == "all":
            all_ok = True
            for m_id in SUPPORTED_LOCAL_MODELS.keys():
                ok = download_single_model(engine, m_id)
                if not ok:
                    all_ok = False
            sys.exit(0 if all_ok else 1)
        else:
            ok = download_single_model(engine, args.model)
            sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[CANCELLED] Download aborted by user.")
        sys.exit(130)
