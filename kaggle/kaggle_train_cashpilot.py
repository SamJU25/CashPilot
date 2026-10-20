"""
Turnkey Kaggle Training Script for SME Finance Copilot (CashPilot-2B / MiniCPM5-2B).
Trains 4-bit QLoRA on free Kaggle NVIDIA Tesla T4 GPU (16 GB VRAM).
Outputs a downloadable zip of the trained adapter weights.
"""

import os
# Pin to single GPU to prevent SFTTrainer DataParallel multi-GPU conflict
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import sys
import gc
import glob
import zipfile
import json
import torch

# 0. Clean any torchaudio stubs from sys.modules to prevent Python 3.13 find_spec ValueError
sys.modules.pop("torchaudio", None)

try:
    import transformers.utils.import_utils as t_utils
    t_utils.is_torchaudio_available = lambda: False
    t_utils._torchaudio_available = False
except Exception:
    pass

# 1. Clean previous memory in kernel
for obj in list(globals().keys()):
    if obj in ["model", "trainer", "train_dataset", "val_dataset", "tokenizer", "sft_args", "args"]:
        del globals()[obj]
sys.last_traceback = None
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    if hasattr(torch.cuda, "ipc_collect"):
        torch.cuda.ipc_collect()

# 2. Robust dataset extraction and location
print("=" * 70)
print("SME Finance Copilot — CashPilot-2B QLoRA Fine-Tuning Pipeline")
print("=" * 70)

if not torch.cuda.is_available():
    raise RuntimeError(
        "Kaggle is still running on CPU! In the right sidebar under 'Notebook settings' -> 'Accelerator', select 'GPU T4' and turn it on."
    )

# Unpack any uploaded zip in /kaggle/input or /kaggle/working
zip_candidates = (
    glob.glob("/kaggle/input/**/*.zip", recursive=True)
    + glob.glob("/kaggle/working/**/*.zip", recursive=True)
    + glob.glob("./*.zip")
)
for zf in zip_candidates:
    if "lora" in os.path.basename(zf).lower():
        continue
    try:
        with zipfile.ZipFile(zf, "r") as z:
            names = z.namelist()
            if any("finetune_train" in n for n in names):
                print(f"Unpacking dataset archive: {zf} -> /kaggle/working/dataset")
                z.extractall("/kaggle/working/dataset")
                break
    except Exception as e:
        print(f"Skipping archive {zf}: {e}")

# Search for finetune_train.jsonl
train_matches = (
    glob.glob("/kaggle/working/**/finetune_train*.jsonl", recursive=True)
    + glob.glob("/kaggle/input/**/finetune_train*.jsonl", recursive=True)
    + glob.glob("./**/finetune_train*.jsonl", recursive=True)
)
val_matches = (
    glob.glob("/kaggle/working/**/finetune_val*.jsonl", recursive=True)
    + glob.glob("/kaggle/input/**/finetune_val*.jsonl", recursive=True)
    + glob.glob("./**/finetune_val*.jsonl", recursive=True)
)
tools_matches = (
    glob.glob("/kaggle/working/**/tools_train*.jsonl", recursive=True)
    + glob.glob("/kaggle/input/**/tools_train*.jsonl", recursive=True)
    + glob.glob("./**/tools_train*.jsonl", recursive=True)
)

if not train_matches:
    all_jsonl = glob.glob("/kaggle/input/**/*.jsonl", recursive=True)
    if all_jsonl:
        all_jsonl.sort(key=lambda p: os.path.getsize(p), reverse=True)
        train_path = all_jsonl[0]
        val_path = all_jsonl[1] if len(all_jsonl) > 1 else None
        print(f"Auto-selected largest JSONL as train dataset: {train_path}")
    else:
        raise FileNotFoundError(
            "Could not locate finetune_train.jsonl! Please upload sme-finance-dataset.zip or the dataset/ folder as a Kaggle Dataset."
        )
else:
    train_path = train_matches[0]
    val_path = val_matches[0] if val_matches else None

tool_path = tools_matches[0] if tools_matches else None

MODEL_ID = os.environ.get("BASE_MODEL_ID", os.environ.get("MODEL_ID", "openbmb/MiniCPM5-2B"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/kaggle/working/sme-finance-lora")
ZIP_OUTPUT = os.environ.get("ZIP_OUTPUT", "/kaggle/working/sme_finance_lora.zip")

print(f"Target Model:   {MODEL_ID}")
print(f"Train Dataset:  {train_path} ({round(os.path.getsize(train_path)/1e6, 2)} MB)")
if val_path:
    print(f"Val Dataset:    {val_path} ({round(os.path.getsize(val_path)/1e6, 2)} MB)")
if tool_path:
    print(f"Tools Dataset:  {tool_path} ({round(os.path.getsize(tool_path)/1e6, 2)} MB)")
print(f"GPU Detected:   {torch.cuda.get_device_name(0)}")
print(f"VRAM:           {round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)} GB")
print("=" * 70)

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import Dataset

# 3. Hardware Precision Calibration
# Base model quantized in 4-bit NormalFloat4 with float16 compute
compute_dtype = torch.float16
print(f"\n[1/5] Calibrating compute precision for {MODEL_ID}...")
print(f"Hardware Compute Dtype: {compute_dtype}")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=compute_dtype,
)

print(f"Loading {MODEL_ID} in 4-bit NormalFloat4...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=compute_dtype,
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(
    model,
    use_gradient_checkpointing=True,
)

# 4. LoRA Configuration on all linear projections
print("\n[2/5] Configuring LoRA adapters...")
target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
peft_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=target_modules,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, peft_config)

# Cast all trainable adapter weights to float32 to ensure numerical stability without GradScaler
for param in model.parameters():
    if param.requires_grad:
        param.data = param.data.to(torch.float32)

model.print_trainable_parameters()

# 5. Dataset Ingestion & Formatting
print("\n[3/5] Loading and formatting ChatML conversations...")
train_files = [train_path]
if tool_path:
    train_files.append(tool_path)

def build_chatml_dataset(file_paths, tok):
    texts = []
    skipped = 0
    for fp in file_paths:
        if not fp or not os.path.exists(fp):
            continue
        print(f"Processing {fp}...")
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    formatted = tok.apply_chat_template(
                        row["messages"],
                        tools=row.get("tools"),
                        tokenize=False,
                        add_generation_prompt=False,
                    )
                    texts.append(formatted)
                except Exception as ex:
                    skipped += 1
                    if skipped <= 3:
                        print(f"Warning: skipped row {line_no} in {fp}: {ex}")
    print(f"Total formatted examples: {len(texts)} (skipped: {skipped})")
    return Dataset.from_dict({"text": texts})

train_dataset = build_chatml_dataset(train_files, tokenizer)
val_dataset = build_chatml_dataset([val_path], tokenizer) if val_path else None

# 6. Training Execution (~18-25 min on Tesla T4)
print("\n[4/5] Starting supervised fine-tuning...")
if torch.cuda.is_available():
    torch.cuda.empty_cache()

from trl import SFTTrainer

training_kwargs = {
    "output_dir": OUTPUT_DIR,
    "num_train_epochs": 1,
    "per_device_train_batch_size": 4,      # Fits cleanly in ~7 GB VRAM
    "gradient_accumulation_steps": 4,       # Effective batch size = 16
    "learning_rate": 2e-4,
    "lr_scheduler_type": "cosine",
    "warmup_steps": 15,
    "logging_steps": 10,
    "save_strategy": "epoch",
    "save_total_limit": 1,
    "fp16": False,                         # Disabled: eliminates AMP GradScaler unscale crash on BFloat16/T4
    "bf16": False,                         # Disabled on T4 (compute capability 7.5 lacks native BF16)
    "optim": "paged_adamw_8bit",
    "report_to": "none",
}

try:
    from trl import SFTConfig
    sft_args = SFTConfig(
        **training_kwargs,
        max_length=1536,
        dataset_text_field="text",
        gradient_checkpointing=True,
    )
    sft_args._n_gpu = 1  # Force single-GPU mode to bypass SFTTrainer DataParallel exception
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        args=sft_args,
    )
except (ImportError, TypeError):
    from transformers import TrainingArguments
    args = TrainingArguments(
        **training_kwargs,
        gradient_checkpointing=True,
    )
    args._n_gpu = 1  # Force single-GPU mode to bypass SFTTrainer DataParallel exception
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=1536,
        tokenizer=tokenizer,
        args=args,
    )

trainer.train()

# 7. Save Adapter & Export Zip
print(f"\n[5/5] Saving fine-tuned LoRA weights to {OUTPUT_DIR}...")
trainer.model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"Zipping adapter artifacts into {ZIP_OUTPUT} for 1-click download...")
with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(OUTPUT_DIR):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, OUTPUT_DIR)
            zipf.write(full_path, rel_path)

print(f"\nSUCCESS! Download '{ZIP_OUTPUT}' from the Kaggle Output panel.")
print("Place the unzipped files into 'models/sme-finance-lora/' in your local workspace.")
