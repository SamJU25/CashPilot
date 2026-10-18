"""
Turnkey Kaggle Training Script for SME Finance Copilot (Qwen3-4B-Instruct-2507).
Trains 4-bit QLoRA on free Kaggle NVIDIA Tesla T4 GPU (16 GB VRAM).
Outputs a downloadable zip of the trained adapter weights.
"""

import os
import sys
import glob
import zipfile
import torch

# 1. Detect dataset files (either uploaded as Kaggle Dataset or placed in working directory)
possible_train_paths = [
    "/kaggle/input/**/finetune_train.jsonl",
    "./finetune_train.jsonl",
    "./dataset/finetune_train.jsonl",
]
possible_val_paths = [
    "/kaggle/input/**/finetune_val.jsonl",
    "./finetune_val.jsonl",
    "./dataset/finetune_val.jsonl",
]

train_path = None
for p in possible_train_paths:
    matches = glob.glob(p, recursive=True)
    if matches:
        train_path = matches[0]
        break

val_path = None
for p in possible_val_paths:
    matches = glob.glob(p, recursive=True)
    if matches:
        val_path = matches[0]
        break

if not train_path:
    raise FileNotFoundError(
        "Could not locate finetune_train.jsonl! Please upload dataset_qwen3_ready.zip as a Kaggle Dataset."
    )

print("=" * 70)
print("SME Finance Copilot — Kaggle QLoRA Fine-Tuning Pipeline")
print(f"Target Model:   Qwen/Qwen3-4B-Instruct-2507")
print(f"Train Dataset:  {train_path}")
print(f"Val Dataset:    {val_path}")
print(f"GPU Detected:   {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU'}")
if torch.cuda.is_available():
    print(f"VRAM:           {round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)} GB")
print("=" * 70)

# Permanent bypass: Mock torchaudio to prevent CUDA mismatch and missing module errors in text-only training
import types
sys.modules["torchaudio"] = types.ModuleType("torchaudio")
try:
    import transformers.utils.import_utils as t_utils
    t_utils.is_torchaudio_available = lambda: False
    t_utils._torchaudio_available = False
except Exception:
    pass

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import load_dataset
try:
    from trl import SFTConfig, SFTTrainer
    HAS_SFT_CONFIG = True
except ImportError:
    from trl import SFTTrainer
    HAS_SFT_CONFIG = False

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
OUTPUT_DIR = "/kaggle/working/sme-finance-lora-qwen3-4b"
ZIP_OUTPUT = "/kaggle/working/sme_finance_lora_qwen3_4b.zip"

# 2. Tokenizer & 4-bit Quantization
print("\n[1/5] Loading tokenizer and base model in 4-bit NF4...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

# Hardware precision logic: Tesla T4 (CC 7.5) requires fp16. Only CC >= 8.0 (Ampere/Hopper) supports native bf16.
is_ampere_or_newer = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
compute_dtype = torch.bfloat16 if is_ampere_or_newer else torch.float16

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=compute_dtype,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=compute_dtype,
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(model)

# 3. LoRA Configuration
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
model.print_trainable_parameters()

# Eliminate BFloat16 on Tesla T4: cast base tensors to float16, and all trainable adapter tensors to float32
for name, param in model.named_parameters():
    if param.dtype == torch.bfloat16:
        param.data = param.data.to(torch.float16)
    if param.requires_grad:
        param.data = param.data.to(torch.float32)

# 4. Dataset Ingestion
print("\n[3/5] Loading ChatML dataset...")
data_files = {"train": train_path}
if val_path:
    data_files["val"] = val_path
raw_datasets = load_dataset("json", data_files=data_files)
train_dataset = raw_datasets["train"]
val_dataset = raw_datasets.get("val")

def format_chatml(batch):
    formatted = []
    for conversation in batch["messages"]:
        text = tokenizer.apply_chat_template(
            conversation,
            tokenize=False,
            add_generation_prompt=False,
        )
        formatted.append(text)
    return {"text": formatted}

train_dataset = train_dataset.map(format_chatml, batched=True, load_from_cache_file=False)
if val_dataset:
    val_dataset = val_dataset.map(format_chatml, batched=True, load_from_cache_file=False)

# 5. Training Execution (Fast Turbo Settings: ~25-30 min on Tesla T4)
print("\n[4/5] Starting supervised fine-tuning (1 epoch fast run)...")
training_kwargs = {
    "output_dir": OUTPUT_DIR,
    "num_train_epochs": 1,                 # 1 epoch (193 steps) is optimal for LoRA instruction alignment
    "per_device_train_batch_size": 4,      # 4 batch size fits in 16GB T4 (~8.2 GB utilized)
    "gradient_accumulation_steps": 4,       # Effective batch size = 16
    "learning_rate": 2e-4,
    "lr_scheduler_type": "cosine",
    "warmup_steps": 15,
    "logging_steps": 5,
    "save_strategy": "epoch",
    "save_total_limit": 1,
    "fp16": not is_ampere_or_newer,
    "bf16": is_ampere_or_newer,
    "gradient_checkpointing": False,       # False eliminates forward-recomputation (1.8x speedup)
    "optim": "paged_adamw_8bit",
    "report_to": "none",
    "max_length": 1536,                    # 1536 covers 95%+ of examples with 1.8x faster attention
    "dataset_text_field": "text",
    "eval_strategy": "no",                 # Skip mid-training eval to avoid pauses
}

if HAS_SFT_CONFIG:
    sft_config = SFTConfig(**training_kwargs)
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        args=sft_config,
    )
else:
    from transformers import TrainingArguments
    training_kwargs.pop("max_length", None)
    training_kwargs.pop("dataset_text_field", None)
    training_kwargs.pop("eval_strategy", None)
    if val_dataset:
        training_kwargs["evaluation_strategy"] = "epoch"
    args = TrainingArguments(**training_kwargs)
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        tokenizer=tokenizer,
        args=args,
    )

trainer.train()

# 6. Save Adapter & Export Zip
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
