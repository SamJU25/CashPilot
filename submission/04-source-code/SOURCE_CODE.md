# CashPilot — Source Code, Deployment and Test Cases

**GitHub repository:** https://github.com/SamJU25/F-SME-Finance-Copilot
**Team:** Sampad Chakma (@SamJU25), Purno Dewan (@coderx86), Binoy Kumar Chakma (@binoy-kumar-changmha), Parban Chakma (@Parban1527)  
**Branch:** `main` · **License:** MIT · **Languages:** Python 3.11+ (FastAPI backend), TypeScript (Next.js 14 dashboard), Solidity 0.8.20 (invoice registry)

The project README (`README.md` at the repository root) is the entry point. This file is the reviewer's checklist for the "Source code" submission item: where the code is, how to run it, and which tests prove what.

---

## 1. Repository layout

```
F-SME-Finance-Copilot/
├── README.md                    Project overview, quickstart, API table
├── api/                         FastAPI app: main.py, rate_limit.py, routes/
├── services/
│   ├── ingestion/               CSV + PDF statement parsing, tie-out, row error codes
│   ├── calculations/            25 Decimal financial engines
│   ├── matcher/                 Liquidity scoring and financing match
│   ├── decision/                Decision-table registry (ZenEngine + fallback)
│   ├── agent/                   AI CFO supervisor, semantic router, LLM bridge, local SLM
│   ├── security/                Three-tier gate, staging ledger, tenant tokens, encryption
│   └── blockchain/              Canonical invoice hash + pledge registry
├── contracts/
│   ├── InvoiceRegistry.sol      FISCO BCOS double-pledge contract
│   └── decision_tables/         15 JSON policy tables
├── src/                         Next.js 14 dashboard (7 workspaces)
├── tests/                       unit / integration / security / e2e (964 tests)
├── data/samples/                7 sample bank statements (USD, EUR, deficit, payroll, payouts)
├── docker/, docker-compose.yml  Container build and stack
├── .github/workflows/ci.yml     CI: tests + container smoke test
├── docs/                        system.md, architecture.md, security.md, GLOSSARY.md
└── submission/                  Competition deliverables (this folder)
```

---

## 2. Deployment

### Option A — Docker (recommended)

Requires Docker Desktop or Docker Engine with Compose.

```bash
git clone https://github.com/SamJU25/F-SME-Finance-Copilot.git
cd F-SME-Finance-Copilot
cp .env.example .env
```

Edit `.env` and set at minimum:

```ini
TENANT_TOKEN_SECRET=<random 32+ char string>
TENANT_ENROLLMENT_KEY=<random key you will type into Settings>
TENANT_ENROLLMENT_TENANT_ID=SME-DEMO-001
```

Then:

```bash
docker compose up --build -d
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API health | http://localhost:8000/api/v1/health |
| OpenAPI docs | http://localhost:8000/docs |

Stop with `docker compose down`. State persists in the `copilot-data`, `copilot-models` and `copilot-hf-cache` volumes.

### Option B — Local development

Prerequisites: Python 3.11+, Node.js 18+.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1    macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000 and upload `data/samples/synthetic-statement.csv` on the Statements page.

### Optional — on-device model

```bash
python -m pip install -r requirements-local.txt
python scripts/download_model.py
```

This downloads `openbmb/MiniCPM5-2B` to `models/base/`. Without it, chat falls back to deterministic answers with the same verified figures, or to a cloud provider configured in Settings.

### Production switches

| Variable | Effect |
|---|---|
| `COPILOT_ENV=production` | Refuses to start without `COPILOT_DATA_KEY` |
| `COPILOT_DATA_KEY` | Fernet-encrypts sessions, staged intents and invoice registry at rest |
| `ALLOWED_ORIGINS` | CORS allow-list |
| `RATE_LIMIT_PER_MINUTE`, `TRUSTED_PROXY_HOPS` | Per-IP limiter |
| `DECISION_ADMIN_KEY` | Enables operator-only decision-table reload |

---

## 3. Test cases

Run everything:

```bash
python -m pytest -q
```

Latest result (2026-10-20, Windows 11, Python 3.14): **970 passed, 1 skipped in 25.24 s**. The skip is a POSIX file-mode assertion that does not apply on Windows. Full log: `../06-execution-evidence/logs/pytest_full_run.log`.

Frontend checks:

```bash
npm run type-check
npm run build
```

### 3.1 Suite breakdown

| Suite | Count | What it proves |
|---|---|---|
| `tests/unit/` (37 files) | 810 | Every financial engine against fixed Decimal fixtures; parser row errors; decision tables; tenant tokens; session store; blockchain registry |
| `tests/integration/` (7 files) | 104 | Each API route end to end through FastAPI, including PDF upload, LLM bridge, model discovery, session memory |
| `tests/security/` (6 files) | 55 | Tier invariants, tenant auth and isolation, hardening, encryption at rest, rate limit, SSRF guard |
| `tests/e2e/` (1 file) | 2 | Full owner journey via REST and via chat |

### 3.2 Key test cases mapped to requirements

| Requirement | Test case | File |
|---|---|---|
| Cash-flow analysis from a statement | `test_complete_sme_copilot_user_journey`: upload CSV → balance 7500.00, burn 100.00/day, runway 75 days, status `WATCH`, row 6 rejected `INVALID_AMOUNT` | `tests/e2e/test_csv_upload_e2e.py` |
| Financing match with true APR | Same test: underwriting returns ≥ 1 facility, top facility not predatory, APR ≤ 36% | `tests/e2e/test_csv_upload_e2e.py` |
| AI agent completes the task by dialogue | `test_complete_conversational_agent_user_journey`: chat routes to `CASH_DIAGNOSTIC`, `CREDIT_UNDERWRITING`, `ACTION_STAGING`; reply says nothing has been sent | `tests/e2e/test_csv_upload_e2e.py` |
| Cash crunch prediction | Deficit date and shortfall on a declining statement | `tests/unit/test_predictive_cash.py` |
| Decimal-only money | Runway, DAB, CCC, DSCR, Z′, DuPont, DCF fixtures | `tests/unit/test_calculations.py`, `test_financial_metrics.py`, `test_enterprise_finance_tools.py` |
| Tier 3 never executes | `/execute` returns 404/405; prepare → `PREPARED`; second decision → 409 | `tests/e2e/`, `tests/security/test_action_gate_auth.py` |
| Tenant isolation | Cross-tenant read/prepare returns 404; client `tenant_id` ignored | `tests/security/test_action_gate_auth.py` |
| Schema boundary | Extra fields rejected | `tests/security/test_invariants.py` |
| PII masking | IBAN and phone redacted; company and person names replaced in the exact outgoing cloud payload and restored in the reply | `tests/security/test_invariants.py`, `tests/unit/test_name_masking.py` |
| SSRF guard | Loopback, private, metadata and credentialed URLs rejected | `tests/security/test_url_guard.py` |
| Encryption at rest | Sealed files carry `enc:v1:`; production refuses to start without key | `tests/security/test_encryption_at_rest.py` |
| Double-pledge prevention | Second pledge raises `ERR_INVOICE_ALREADY_PLEDGED` | `tests/unit/test_blockchain_registry.py` |
| Sample data parses | All files in `data/samples/` | `tests/unit/test_sample_csvs.py` |

### 3.3 Sandbox replay

`python submission/06-execution-evidence/run_sandbox_evidence.py` replays 34 operator and attacker operations against the real app and writes timestamped logs. Latest: 34/34 as expected. See `../06-execution-evidence/`.

---

## 4. Third-party components and licences

| Component | Licence | Use |
|---|---|---|
| FastAPI, Starlette, Pydantic | MIT | API and validation |
| Next.js, React | MIT | Dashboard |
| Tailwind CSS, Radix UI / shadcn/ui | MIT | UI styling and primitives |
| Recharts | MIT | Charts |
| zen-engine (GoRules) | MIT | Decision tables |
| FastEmbed, `BAAI/bge-small-en-v1.5` | Apache-2.0 / MIT | Intent embeddings |
| `openbmb/MiniCPM5-2B` | Model licence published by OpenBMB on Hugging Face | Optional local model, downloaded by the user, not redistributed in the repository |
| cryptography (Fernet) | Apache-2.0 / BSD | Encryption at rest |
| pypdf | BSD-3-Clause | PDF statements |
| numpy, httpx, huggingface-hub | BSD / BSD / Apache-2.0 | Numerics, HTTP client, model download |
| react-markdown, remark/rehype, KaTeX, lucide-react, motion | MIT | Chat rendering, icons, animation |

All sample statements in `data/samples/` are fabricated demo data written in each bank's export layout; none contain real customer records.
