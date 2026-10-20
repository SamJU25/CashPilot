# SME Finance Copilot — Kaggle Training Guide

Train **CashPilot-2B** (default foundation: **`openbmb/MiniCPM5-2B`**) on free Kaggle GPU hardware (NVIDIA Tesla T4, 16 GB VRAM) with zero load on your local machine.

---

### Step 1: Open Kaggle & Create a New Notebook
1. Go to [kaggle.com](https://www.kaggle.com) and log in.
2. Click **+ Create** $\to$ **New Notebook**.

---

### Step 2: Upload the Notebook & Dataset
1. In the Kaggle notebook menu, click **File** $\to$ **Upload Notebook**.
2. Select [`kaggle/kaggle_cashpilot_2b_training.ipynb`](kaggle_cashpilot_2b_training.ipynb) (or run [`kaggle/kaggle_train_cashpilot.py`](kaggle_train_cashpilot.py)).
3. On the right-hand panel under **Input**, click **Upload** $\to$ **New Dataset**.
4. Zip your `dataset/` directory (`finetune_train.jsonl`, `finetune_val.jsonl`, `tools_train.jsonl`) and upload it as `sme-finance-dataset`.

---

### Step 3: Configure GPU Accelerator & Internet
In the right-hand sidebar under **Notebook settings**:
- **Accelerator**: Select **GPU T4** (or **GPU T4 x2**).
- **Internet**: Toggle **ON** (required to download base weights from Hugging Face).

---

### Step 4: Run Training
Click **Run All** (or `Shift + Enter` through the cells):
- Cell 1: Installs PyTorch, Hugging Face `transformers`, `peft`, `trl`, `bitsandbytes`.
- Cell 2: Verifies NVIDIA Tesla T4 (15.9 GB VRAM).
- Cell 3: Automatically detects and unpacks the training and validation datasets.
- Cell 4: Loads `openbmb/MiniCPM5-2B` (or `BASE_MODEL_ID` env variable) in 4-bit NF4 and executes QLoRA training (~25–35 minutes).
- Cell 5: Tests native inference and zips the fine-tuned adapter into `sme_finance_lora.zip`.

---

### Step 5: Download Weights Back to Your Project
1. When training completes, open the **Output** section in the right sidebar.
2. Click the three dots next to `sme_finance_lora.zip` $\to$ **Download**.
3. Extract the downloaded zip file into your local project directory at:
   `models/sme-finance-lora/`
4. The copilot automatically detects the adapter at startup with zero code changes.
