# SME Finance Copilot — Automated GPU Training Runner
# Configures a clean Python 3.12 environment with CUDA 12.4 for your NVIDIA GeForce RTX 4050 GPU
# Trains the base model named in train_local_model.py (override with -ModelId) without Ollama dependency.

param (
    [string]$ModelId = ""
)

$ErrorActionPreference = "Stop"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "SME Finance Copilot — Local RTX GPU Fine-Tuning Pipeline" -ForegroundColor Cyan
Write-Host "Target GPU: NVIDIA GeForce RTX 4050 (6GB VRAM)" -ForegroundColor Green
Write-Host "Selected Model: $(if ($ModelId) { $ModelId } else { 'train_local_model.py default' })" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan

# Step 1: Ensure isolated Python 3.12 GPU environment is configured
if (-not (Test-Path ".\.venv-train\Scripts\python.exe")) {
    Write-Host "`n[1/5] Provisioning isolated Python 3.12 environment (.venv-train)..." -ForegroundColor Yellow
    uv venv .venv-train --python 3.12
    Write-Host "`nInstalling PyTorch with CUDA 12.4 acceleration and QLoRA libraries via uv..." -ForegroundColor Yellow
    uv pip install --python .\.venv-train\Scripts\python.exe torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    uv pip install --python .\.venv-train\Scripts\python.exe transformers peft bitsandbytes datasets trl accelerate pydantic
} else {
    Write-Host "`n[1/5] Isolated Python 3.12 GPU environment (.venv-train) detected." -ForegroundColor Green
}

# Step 2: Verify CUDA detects the RTX 4050
Write-Host "`n[2/5] Verifying GPU detection and CUDA compute status..." -ForegroundColor Yellow
& .\.venv-train\Scripts\python.exe -c "import torch; print('CUDA Ready:', torch.cuda.is_available()); print('GPU Model:', torch.cuda.get_device_name(0)); print('VRAM (GB):', round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2))"

# Step 3: Run QLoRA training
Write-Host "`n[3/5] Executing QLoRA fine-tuning on 4,566 verified financial examples..." -ForegroundColor Yellow
$modelArgs = if ($ModelId) { @('--model_id', $ModelId) } else { @() }
& .\.venv-train\Scripts\python.exe scripts/train_local_model.py @modelArgs --epochs 3 --batch_size 1 --grad_accum 16 --max_seq_length 1536

# Step 4: Merge weights into standalone native model
Write-Host "`n[4/5] Merging fine-tuned LoRA weights into standalone model..." -ForegroundColor Yellow
& .\.venv-train\Scripts\python.exe scripts/merge_model.py

# Step 5: Native inference test
Write-Host "`n[5/5] Executing native standalone verification battery..." -ForegroundColor Yellow
& .\.venv-train\Scripts\python.exe scripts/verify_local_inference.py --model_path "models/sme-finance-copilot-merged"

Write-Host "`n========================================================================" -ForegroundColor Green
Write-Host "TRAINING, MERGE & VERIFICATION COMPLETE!" -ForegroundColor Green
Write-Host "Your fine-tuned model is ready at: models/sme-finance-copilot-merged" -ForegroundColor Green
Write-Host "Runs 100% natively in Python with zero external daemons." -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Green
