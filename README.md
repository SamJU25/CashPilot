# CashPilot

**The Autonomous AI Chief Financial Officer & Treasury Operating System for Growing Businesses.**

CashPilot connects to your business bank accounts, detects hidden cash crunches weeks before payroll is due, standardizes predatory financing terms, and prepares pre-qualified credit lines in real time. Built with banking-grade deterministic Decimal arithmetic, on-device local AI inference, and an owner-sent Three-Tier security gate where money never moves without your signature.

[![CI](https://github.com/SamJU25/CashPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/SamJU25/CashPilot/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/pytest-1022_passed-brightgreen.svg)](tests/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14_App_Router-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](docker-compose.yml)
[![Solidity 0.8.20](https://img.shields.io/badge/Solidity-0.8.20-363636.svg)](contracts/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Reality: Why Profitable Businesses Fail

Over 82% of small business bankruptcies happen to profitable companies. The killer is the **Cash Conversion Cycle**—the dead time between paying suppliers and collecting from customers.

```
       [Raw Materials Purchased]         [Finished Goods Delivered]         [Customer Cash Collected]
  Day 0 -------------------------- Day 45 ------------------------- Day 105 -----------------
        |                                 |                          |
        +-- Supplier Paid: Day 30         |                          |
            (-$30,000 cash out)           |                          |
                                          +-- Invoiced: Day 45       |
                                              ($100,000 Net 60)      |
                                                                     +-- Cash Received: Day 105
                                                                         (+$100,000 cash in)

  ==> THE 75-DAY CASH CHASM: Cash Conversion Cycle (CCC) = DIO (45) + DSO (60) - DPO (30) = 75 Days
```

Traditional commercial banks take 4 to 8 weeks to underwrite working capital loans and reject up to 80% of applicants due to a lack of physical real estate collateral. Accounting software only shows what happened last month.

**CashPilot changes how companies manage working capital**:
1. **Reads Reality in Seconds**: Drop in bank statement CSVs or PDFs. CashPilot audits running balances down to the exact cent across all your accounts.
2. **Predicts the Crunch**: Forward-simulates daily liquidity over 30, 60, and 90-day horizons to pinpoint the exact day cash drops below zero.
3. **Underwrites Without Collateral**: Replaces audited balance sheets with transactional digital underwriting (Daily Average Balance, cash flow volatility, and payment stability).
4. **Levels the Playing Field**: Unmasks predatory financing factor rates into true Annual Percentage Rate (APR) so you never pay hidden fees.

---

## Product Tour: 8 Specialized Treasury Workspaces

CashPilot ships with **8 dedicated workspaces** compiled in Next.js 14, styled in a precision cockpit theme with Emil Kowalski spring motion transitions and monospace tabular numbers:

```
┌─────────────────┬────────────────────────────────────────────────────────┐
│ Workspace       │ Core Capability                                        │
├─────────────────┼────────────────────────────────────────────────────────┤
│ Overview        │ Runway gauge, 90-day cash curve, and owner audit ledger│
│ Assistant       │ Streaming AI CFO grounded in deterministic calculation │
│ Workstation     │ Live 7-stage cognitive blueprint with execution traces │
│ Early Warning   │ 30/60/90-day predictive shortfall alerts with sliders  │
│ Funding         │ Underwriting marketplace with True APR & loan filter   │
│ Approvals       │ Three-Tier human-in-the-loop proposal staging queue    │
│ Receivables     │ Aging matrix & SHA-256 consortium double-pledge defense│
│ Statements      │ Multi-account ingestion with contra-transfer removal   │
└─────────────────┴────────────────────────────────────────────────────────┘
```

### 1. Overview (`/`)
- **Runway & Cash Horizon**: Live gauge displaying days of cash remaining alongside the 90-day trajectory curve.
- **Dynamic Cash Bridge**: Visual breakdown of starting cash, operating inflows, operating outflows, and net period change.
- **Owner Entries Ledger**: Immutable audit log of manual adjustments with single-click reversal entries so cash history stays balanced.

### 2. Live Workstation (`/workstation`)
- **Interactive Execution Blueprint**: Visualizes the complete 7-stage reasoning path (`Ask -> Guard -> Route -> Agent -> Work -> Knowledge -> Answer`).
- **Telemetry Inspection**: Click any node to inspect execution times, ZenEngine rule IDs, confidence scores, and knowledge card matches.
- **Zero-PII Trace Context Engine**: Captures full timing and rule trees without storing customer statement rows or message text.

### 3. Early Warning Sentinel (`/sentinel`)
- **Cash Crunch Early Warning**: Forward simulation identifying the exact day liquidity dips below zero and computing the exact bridge loan required.
- **Dynamic Window Sliders**: Adjust early warning horizons from 15 to 90 days with instant recalculation of risk profiles.

### 4. AI Treasury Assistant (`/assistant`)
- **Anti-Slop Grounded Answers**: An AI financial advisor grounded strictly in deterministic calculations without hallucinations.
- **Live Financial Telemetry**: Side panel displaying live Cash Balance, Cash Runway, Daily Burn, and Period Change with status pips.
- **Privacy Shield**: Pre-flight regex redacting IBANs, routing numbers, and contact details before data reaches external LLMs.

### 5. Funding Marketplace (`/funding`)
- **Digital Underwriting (0–100 Score)**: Scores liquidity stability based on Daily Average Balance (DAB) and revenue volatility.
- **True APR Normalization**: Converts opaque factor rates (e.g., 1.15x) into standardized APR for transparent comparison.
- **Predatory Loan Quarantine**: Facilities exceeding 36% APR are quarantined in the "Avoid this offer" section.

### 6. Human-In-The-Loop Approvals (`/approvals`)
- **Non-Destructive Staging**: AI drafts credit applications, factoring terms, and vendor notices into an immutable staging queue.
- **Owner-Sent Invariant**: The system never executes money movements. The business owner reviews the pre-filled request (`POST /api/v1/actions/{id}/prepare`) and transmits it themselves.

### 7. Statements & Portfolio Consolidator (`/statements`)
- **Balance Tie-Out Verification**: Validates statements mathematically ($Opening + Inflows - Outflows == Closing$).
- **Multi-Account Auto-Clustering**: Merges sequential monthly statements and separates distinct accounts automatically.
- **Contra-Transfer Elimination**: Detects internal sweeps (e.g., Chase Operating $\to$ SVB Payroll) and subtracts them from revenue and burn calculations.

### 8. B2B Receivables & Anti-Double-Financing (`/receivables`)
- **Aging Invoices Matrix**: Buckets outstanding invoices into Current, 1–30, 31–60, 61–90, and 90+ day tiers.
- **Consortium Blockchain Verification**: Cryptographic SHA-256 invoice hashing checked against `InvoiceRegistry.sol` on FISCO BCOS to prevent double-pledging across lenders.

---

## System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["1. Multi-Account Ingestion"]
        CSV[CSV Statements] --> Consolidator[Portfolio Consolidator]
        PDF[PDF Statements] --> PDFParser[PDF Extractor]
        PDFParser --> Consolidator
        Consolidator --> TieOut{Balance Tie-Out & Contra Elimination}
    end

    subgraph Engines ["2. Deterministic FinTech Engine (services/calculations/)"]
        TieOut --> DAB[Daily Average Balance Carry-Forward]
        TieOut --> Flow[Operating vs Gross Flow Decomposition]
        TieOut --> Crunch[Forward Cash Crunch Simulation]
        TieOut --> CCC[Cash Conversion Cycle: DSO + DIO - DPO]
        TieOut --> Solvency[DSCR, FCCR & Altman Z'-Score]
    end

    subgraph Policies ["3. Policy & Underwriting (contracts/decision_tables/)"]
        DAB & Flow & Crunch & CCC & Solvency --> Zen[ZenEngine JDM Decision Tables]
        Zen --> Underwrite[Continuous Liquidity Score 0-100]
        Zen --> FacilityMatch[True APR Standardizer & Predatory Filter]
    end

    subgraph Routing ["4. Dynamic Vector Routing & Agentic Core"]
        UserMsg[User Query / Staged Instruction] --> FastEmbed[FastEmbed ONNX Vector Router]
        FastEmbed --> Supervisor[Copilot Supervisor]
        Supervisor --> Subagents[Liquidity / Risk / Credit Subagents]
        Supervisor --> Trace[Zero-PII Trace Context Engine]
        Supervisor --> Bridge[services/agent/llm_bridge.py]
        Bridge --> LocalSLM[Local GGUF via llama.cpp]
        Bridge --> CloudLLM[Cloud Providers: Gemini, Claude, GPT-4o, DeepSeek]
    end

    subgraph SecurityGate ["5. Three-Tier Human-In-The-Loop Gate"]
        Underwrite & FacilityMatch & Bridge --> Gate{Security Gatekeeper}
        Gate -->|Autonomous| T1[Tier 1: Read-Only Ingestion & Math]
        Gate -->|Proposal Queue| T2[Tier 2: Staging Queue in Sealed Ledger]
        Gate -->|Outflow Intent| T3[Tier 3: Owner-Sent Request Draft]
    end

    subgraph Surfaces ["6. Executive Dashboard & Audit Rails"]
        T1 & T2 & T3 --> Dashboard[Next.js 14 Cockpit: 8 Workspaces]
        Trace --> Workstation[Live Workstation Blueprint]
        T3 --> FISCO[FISCO BCOS InvoiceRegistry.sol SHA-256 Anti-Double-Financing]
    end
```

---

## Deterministic FinTech Engine

All monetary calculations execute in isolated Python routines (`services/calculations/`) using `decimal.Decimal` with `ROUND_HALF_UP` rounding. LLMs are never used for arithmetic:

| Financial Routine | Module | Formula / Mechanics |
|---|---|---|
| **Daily Average Balance (DAB)** | `services/calculations/dab.py` | Carry-forward over weekends/holidays: $\text{DAB} = \frac{1}{N} \sum_{t=1}^N \text{Balance}_t$ |
| **Cash Conversion Cycle (CCC)** | `services/calculations/working_capital.py` | $\text{CCC} = \text{DSO} + \text{DIO} - \text{DPO}$ |
| **Revenue Inflow Volatility (CV)** | `services/calculations/predictive_cash.py` | $CV = \frac{\sigma_{\text{weekly}}}{\mu_{\text{weekly}}}$ mapped to LOW / MEDIUM / HIGH / CRITICAL |
| **Debt Coverage (DSCR & FCCR)** | `services/calculations/credit.py` | $\text{DSCR} = \frac{\text{Net Operating Income}}{\text{Total Debt Service}}$ |
| **Private Firm Altman Z'-Score** | `services/calculations/credit.py` | $Z' = 0.717X_1 + 0.847X_2 + 3.107X_3 + 0.420X_4 + 0.998X_5$ |
| **DuPont ROE 3-Stage** | `services/calculations/profitability.py` | $\text{ROE} = \text{Profit Margin} \times \text{Asset Turnover} \times \text{Financial Leverage}$ |
| **Truth-in-Lending APR** | `services/calculations/credit.py` | Converts factor rates to true APR; flags loans $> 36\%$ APR |
| **SaaS Unit Economics** | `services/calculations/unit_economics.py` | LTV/CAC ratio, CAC Payback months, Magic Number, and Net Retention |

---

## The Three-Tier Security Gate

Every action endpoint requires a signed tenant token minted via `POST /api/v1/auth/token`. CashPilot enforces a strict physical separation between intelligence and fund movement:

```
┌────────────────────────────────────────────────────────────────────────┐
│ TIER 1: AUTONOMOUS OBSERVATION (Read-Only)                             │
│ CSV/PDF statement ingestion, 25+ Decimal ratios, runway forecasting.   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TIER 2: STAGING QUEUE (Queue Only — Zero Capital Movement)             │
│ Financing proposals and reminders drafted in a Fernet-sealed ledger.   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TIER 3: OWNER-SENT REQUEST (Never Executed by System)                  │
│ CashPilot prepares the request draft at POST /api/v1/actions/{id}/     │
│ prepare. The business owner transmits it themselves. Zero payment      │
│ credentials stored in the system = Zero prompt injection drain risk.   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Quickstart & Deployment

### Option 1: One-Command Docker Launch (Recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Docker Compose.

```bash
# 1. Clone the repository
git clone https://github.com/SamJU25/CashPilot.git
cd CashPilot

# 2. Copy the environment template
cp .env.example .env

# 3. Launch all services in isolated containers
docker compose up --build -d
```

- **Frontend Cockpit**: Open <http://localhost:3000>
- **FastAPI Backend Health**: Open <http://localhost:8000/api/v1/health>
- **Interactive OpenAPI Documentation**: Open <http://localhost:8000/docs>

```bash
# View live logs
docker compose logs -f

# Tear down
docker compose down
```

---

### Option 2: Local Developer Setup

#### 1. Backend Service (FastAPI & Deterministic Engine)
```bash
# Create and activate virtual environment
python -m venv .venv

# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install backend dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Start FastAPI backend service
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 2. Frontend Cockpit (Next.js 14)
```bash
# Open a new terminal in the project root
npm ci

# Launch production build (sub-10ms route switching)
npm run build
npm start -- -p 3000

# Or launch hot-reloading dev server
npm run dev
```

#### 3. AI Engine Configuration (Choose Cloud, Local, or Deterministic)

CashPilot adapts seamlessly to your environment:
- **Cloud AI (Zero Local Footprint)**: Add your provider API key in `.env` (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `GROQ_API_KEY`).
- **Local SLM (100% Offline via GGUF)**: Run quantized models locally on your GPU or CPU without third-party APIs:
  ```bash
  python scripts/download_model.py --model qwen2.5-3b-instruct
  ```
- **Pure Deterministic (Zero AI Config)**: If no LLM is configured, CashPilot runs 100% of its financial ratios, runway projections, and loan matching via pure Python `decimal.Decimal`.

---

## Automated Verification Suite

Run the full deterministic verification suite from the repository root:

```bash
# 1. Run full backend pytest suite (1,022 passed, 1 POSIX skip)
pytest -q

# 2. Run frontend TypeScript verification
npm run type-check

# 3. Compile production Next.js static routes
npm run build
```

### Verified Test Breakdown (Audited 2026-10-22)
```
tests/unit/            861 passed            (Ingestion, Decimal Math, Underwriting, Tracing, Session Store)
tests/integration/     105 passed            (FastAPI Endpoints, Multi-Account Sync, Action Ledger, Model Discovery)
tests/security/         54 passed, 1 skipped (Three-Tier Invariants, PII Scrubbing, Fernet Sealing, Hardening)
tests/e2e/               2 passed            (Full Multi-Statement Ingestion to Prepared-Action Journey)
======================= 1022 passed, 1 skipped in 33.09s =======================
```

*(Note: The single skipped test is a POSIX-only file mode assertion `0700/0600` on Windows filesystems; it is verified in Ubuntu 24.04 CI containers).*

---

## Documentation Index

| Specification | Focus & Technical Scope |
|---|---|
| 📘 [System Design Specification](docs/system.md) | Mathematical formulas, JSON schemas, and smart contract specifications |
| 🏛️ [Architectural Plan](docs/architecture.md) | 6-layer topology, local SLM inference, dynamic vector routing, and multi-agent suites |
| 🛡️ [Security Architecture](docs/security.md) | Threat modeling, Three-Tier Gate invariants, Fernet encryption, and tenant isolation |
| 📖 [Domain Glossary](docs/GLOSSARY.md) | Standardized fintech definitions (CCC, DAB, DSCR, True APR, NSF) |
| ⚡ [Sprint Workflow](.agent/workflows/sprint-workflow.md) | Contract-first development protocol and verification gates |

---

## Origin & License

Developed for FinTechathon 2026 (Tsinghua University PBCSF & WeBank).

Distributed under the MIT License. See [`LICENSE`](LICENSE) for complete terms.
