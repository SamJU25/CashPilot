# SME Finance Copilot — Kaggle Training Guide

Train **`Qwen/Qwen3-4B-Instruct-2507`** on free Kaggle GPU hardware (NVIDIA Tesla T4, 16 GB VRAM) with zero load on your local laptop.

---

### Step 1: Open Kaggle & Create a New Notebook
1. Go to [kaggle.com](https://www.kaggle.com) and log in.
2. Click **+ Create** $\to$ **New Notebook**.

---

### Step 2: Upload the Notebook & Dataset
1. In the Kaggle notebook menu, click **File** $\to$ **Upload Notebook**.
2. Select [`kaggle/kaggle_qwen3_4b_training.ipynb`](kaggle_qwen3_4b_training.ipynb) from this repository.
3. On the right-hand panel under **Input**, click **Upload** $\to$ **New Dataset**.
4. Upload [`dataset_qwen3_ready.zip`](../dataset_qwen3_ready.zip) (2.41 MB). Set dataset title to `sme-finance-dataset`.

---

### Step 3: Configure GPU Accelerator & Internet
In the right-hand sidebar under **Notebook settings**:
- **Accelerator**: Select **GPU T4** (or **GPU T4 x2**).
- **Internet**: Toggle **ON** (required to download base weights from Hugging Face).

---

### Step 4: Run Training
Click **Run All** (or `Shift + Enter` through the 5 cells):
- Cell 1: Installs PyTorch, Hugging Face `transformers`, `peft`, `trl`, `bitsandbytes`.
- Cell 2: Verifies NVIDIA Tesla T4 (15.9 GB VRAM).
- Cell 3: Automatically unpacks the verified training and validation datasets.
- Cell 4: Loads `Qwen3-4B-Instruct-2507` in 4-bit NF4 and executes 3 epochs of QLoRA training (~25–35 minutes).
- Cell 5: Tests native inference and zips the fine-tuned adapter into `sme_finance_lora_qwen3_4b.zip`.

---

### Step 5: Download Weights Back to Your Laptop
1. When cell 5 completes, open the **Output** section in the right sidebar.
2. Click the three dots next to `sme_finance_lora_qwen3_4b.zip` $\to$ **Download**.
3. Extract the downloaded zip file into your local project directory at:
   `models/sme-finance-lora/`
