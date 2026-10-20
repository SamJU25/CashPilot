# SME Finance Copilot: Master Architectural Plan (`architecture.md`)

- **Document Role**: Macro Architecture, Multi-Agent Topology, Governance & Verified Technical Baseline
- **Status**: Active Architecture Blueprint & Technical Contract (Verified Baseline: 863 Passed Tests, 1 Skipped)
- **Date**: 2026-10-17
- **Competition Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

### Master Documentation Suite:
- 📘 [System Design (`docs/system.md`)](system.md) — Schemas, 25+ math engines, decision tables & smart contract specs
- 🏛️ [Architecture Plan (`docs/architecture.md`)](architecture.md) — 6-layer topology, dual SLM inference & multi-agent suites
- 🛡️ [Security Architecture (`docs/security.md`)](security.md) — 5 Invariants, threat modeling & Three-Tier Security Gate
- ⚡ [Engineering Lifecycle (`.agent/workflows/sprint-workflow.md`)](../.agent/workflows/sprint-workflow.md) — Contract-first TDD and verification protocol

- 📖 [Ubiquitous Domain Glossary (`GLOSSARY.md`)](../GLOSSARY.md) — Standardized fintech and underwriting terminology

---

## 1. Macro Architecture & 6-Layer Topology

**Project Form Factor**: **Responsive Web Application + Progressive Web App (PWA)**  
- Dual-Device Architecture: Next.js 14 App Router optimized for desktop financial analysis workstations, coupled with mobile PWA home-screen installation for real-time alerts and reviewing drafted requests.

The architecture decouples **Untrusted Conversational Reasoning** from **Deterministic Financial Execution**:

```
[ User Desktop Browser / Mobile PWA ]
            │ (TLS 1.3 + signed tenant tokens)
            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: CLIENT PRESENTATION (Next.js 14 App Router + PWA)             │
│ • Desktop: Multi-column ledger tables, predictive cash crunch cards    │
│ • Current build: health probe + API reference canvas (root app/)       │
│ • Target: provider settings modal, deficit cards, approvals UI         │
│ • Monospace tabular numbers (font-variant-numeric: tabular-nums)       │
│ • Emil Kowalski spring motion (<280ms transitions)                     │
│ • Zero API keys, zero client-side financial calculation authority      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP-Only RS256 / Bearer Auth + X-Tenant-ID
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: API GATEWAY & SECURITY INGRESS (FastAPI + Nginx)              │
│ • Token-bucket rate limiting (60 req/min per IP, api/rate_limit.py)    │
│ • Signed tenant tokens on action routes (X-Tenant-Token/Bearer)        │
│ • Rust-compiled Pydantic v2 strict type validation (extra="forbid")    │
│ • Automated 422 drop for malformed payloads before execution          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: AGENTIC SUPERVISOR & UNIVERSAL LLM BRIDGE                     │
│ • Dynamic Semantic Routing: FastEmbed ONNX (BAAI/bge-small-en-v1.5)    │
│ • Local SLM Inference Engine: LocalTransformersEngine                  │
│   - Flagship 3B (models/sme-finance-lora)                              │
│ • Universal LLM Bridge (services/agent/llm_bridge.py):                 │
│   - Gemini 2.0 Flash, Claude 3.5 Sonnet, GPT-4o, DeepSeek, Groq, Ollama│
│ • Dynamic Model Discovery (POST /api/v1/agent/fetch-models)            │
│ • Pre-Flight PII Redaction: Customer names, phone numbers, account IDs │
│ • Anti-Slop Post-Processing: Grounded neural CFO responses             │
│ • Zero Write Credentials: Emits ActionIntent drafts only               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Internal Invocations
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 4: DETERMINISTIC COMPUTATION & INGESTION ENGINE (Pure Python)    │
│ • Multi-Format Ingestion: UTF-8 CSV + PDF statement parsers           │
│   - Line-item extraction, balance tie-out & row-level error provenance │
│ • 25+ Pure Decimal Financial Engines (services/calculations/):        │
│   - DAB carry-forward, gross inflow/outflow flow decomposition         │
│   - Predictive cash crunch overdraft pinpointing (shortfall & date)    │
│   - Weekly revenue inflow volatility CV & volatility tiers             │
│   - Cash Conversion Cycle (DSO, DIO, DPO), DSCR & FCCR                 │
│   - Altman Z'-score, DuPont ROE 3-stage, ROIC/EVA, DCF/WACC            │
│   - SaaS unit economics, trade credit APR, 160+ ISO currencies         │
│ • Continuous Liquidity Scoring: 0-100 continuous score & gray triage   │
│ • Policy Decision Tables: ZenEngine JSON tables for covenants & risks  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 5: STORAGE & DATA SECURITY (current: JSON store under .data/)    │
│ • Staging ledger persisted with atomic file replace                    │
│ • Tenant scoping enforced in the API layer (signed tokens), not SQL RLS │
│ • PostgreSQL 16 + RLS remains the production target (not yet built)    │
│ • Staging Ledger: action_intents awaiting the owner's prepare/dismiss  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 6: CONSORTIUM BLOCKCHAIN ANCHOR (FISCO BCOS)                     │
│ • InvoiceRegistry.sol smart contract: UNREGISTERED -> PLEDGED          │
│ • Canonical SHA-256 invoice hashing: TaxID + BuyerID + InvNum + Amount │
│ • PBFT Multi-Bank Consensus: Blocks double-financing across lenders   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Operating Model & Multi-Agent Topology

The architecture pairs the **Lead Architect & Operator** with the **Lead Financial Orchestrator**, which coordinates 12 Global Governance Specialists and 45 FinTech Domain Specialists across 7 Project Suites:

```
                          LEAD ARCHITECT & OPERATOR
                                       │
                         LEAD FINANCIAL ORCHESTRATOR
                                       │
  ┌────────────────────────────────────┴────────────────────────────────────┐
  ▼                                                                         ▼
[ 0-global-specialists ]                                          [ 1 to 7 Project Suites ]
12 Macro Governance Agents                                        45 FinTech Domain Agents
─────────────────────────                                        ─────────────────────────
• research-scout        • qa-verifier                            • Suite 1: Agentic Orchestration (7)
• agentic-architect     • code-reviewer                          • Suite 2: FinTech Engine (6)
• systems-architect     • code-optimizer                         • Suite 3: Backend Platform (6)
• frontend-craft-eng    • prompt-engineer                        • Suite 4: Frontend Dashboard (4)
• security-guardian     • technical-writer                       • Suite 5: Security & QA (7)
• cross-platform-eng    • penetration-tester                     • Suite 6: Product & Pitch (6)
                                                                 • Suite 7: Research Intelligence (9)
```

### Runtime Functional Execution Squads

For runtime request handling, specialized specialists collaborate across 4 functional domains:

```
                              [ Human SME Business Owner ]
                                           │
                                           ▼ (Approvals / Chat / Generative UI)
                           ┌───────────────────────────────┐
                           │   LEAD FINANCIAL ORCHESTRATOR │
                           │ • FastEmbed Semantic Routing  │
                           │ • Zero Database Write Rights  │
                           └───────────────┬───────────────┘
                                           │
         ┌──────────────────┬──────────────┴─────┬──────────────────┐
         ▼                  ▼                    ▼                  ▼
  ┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
  │   SQUAD 1    │   │   SQUAD 2    │     │   SQUAD 3    │   │   SQUAD 4    │
  │ Ingestion &  │   │  Diagnostic  │     │Predictive &  │   │ Underwriting │
  │ Privacy Core │   │  CFO Engine  │     │Risk Engine   │   │  & Matching  │
  ├──────────────┤   ├──────────────┤     ├──────────────┤   ├──────────────┤
  │ CSV/PDF OCR  │   │ Pure Python  │     │ Predictive   │   │ Continuous   │
  │ Tie-out      │   │ Decimal math │     │ Overdraft    │   │ 0-100 Score  │
  │ Regex PII    │   │ DAB, CCC, ROE│     │ Inflow CV    │   │ ZenEngine DT │
  └──────────────┘   └──────────────┘     └──────────────┘   └──────────────┘
         │                  │                    │                  │
         └──────────────────┴──────────────┬─────┴──────────────────┘
                                           │ Emits ActionIntent (Draft Only)
                                           ▼
                           ┌───────────────────────────────┐
                           │    THREE-TIER GATEKEEPER      │
                           │ • Tier 1: Read-Only Ledger    │
                           │ • Tier 2: Staged Queue        │
                           │ • Tier 3: owner-sent + BCOS   │
                           └───────────────────────────────┘
```

### Squad Responsibilities & Boundaries
1. **Lead Financial Orchestrator**: Read-only supervisor. Dispatches user intent via FastEmbed ONNX vector triage, packages pre-calculated deterministic context, and invokes the Universal LLM Bridge. Zero database write permissions.
2. **Squad 1 (Ingestion & Privacy Core)**: Ingests CSV and PDF bank statements via `statement_parser.py`, `pdf_parser.py`, and `csv_parser.py`. Executes line-item extraction, opening/closing balance tie-out, assigns row-level error provenance codes, and strips PII before any LLM ingestion.
3. **Squad 2 (Diagnostic CFO Engine)**: 0% LLM math. Pure Python `decimal.Decimal` computation of DAB, Net Daily Flow, Cash Conversion Cycle (DSO/DIO/DPO), DSCR, FCCR, Altman Z'-score, DuPont ROE 3-stage, and ROIC/EVA.
4. **Squad 3 (Predictive & Risk Engine)**: Evaluates daily cash trajectories, pinpoints exact overdraft dates and deficit shortfalls, and computes weekly revenue inflow volatility index and risk tier.
5. **Squad 4 (Underwriting & Matching)**: Computes continuous liquidity scoring (0–100), evaluates loan covenants and persona risk policies using ZenEngine JSON decision tables, and flags loans $>36\%$ APR as predatory.
6. **The Three-Tier Security Gatekeeper**: Stages ActionIntents (`STAGED_PENDING_HITL`), computes canonical `SHA-256` invoice hashes for FISCO BCOS, and never executes: the owner prepares the drafted request at `POST /api/v1/actions/{id}/prepare` and sends it themselves, or dismisses it.

---

## 3. Database & Agent Memory Architectural Decision

### 3.1 Database Selection: PostgreSQL 16 (+ SQLite for Local Dev)
- **Current implementation**: no relational database is wired yet. The staging ledger and invoice registry persist to JSON files under `COPILOT_LEDGER_DIR` (default `.data/`), and session statements under `COPILOT_SESSION_DIR` (default `.sessions/`, set to `/app/.data/sessions` in containers so it shares the persisted volume), using process-local locks and atomic file replacement. This is adequate for the single-process demo and is not safe for multi-worker scaling. The Docker build context excludes `.data/`, `.sessions/`, `.freebuff/` and `.claude/` so sealed statements, staged proposals and passkeys are never baked into an image layer.
- **Why PostgreSQL (target)**: ACID transactional consistency, kernel-level Row-Level Security (RLS), native JSONB staging, and banking industry standard.
- **Why Alternatives Were Rejected**: NoSQL (MongoDB) lacks double-entry atomicity; pure vector databases cannot manage financial ledgers.
- **Local Dev & Testing**: Automated test suite (`pytest -q`) runs 863 deterministic tests (plus one POSIX-only skip) against isolated test storage.

### 3.2 Agent Memory Architecture: Zero Cognitive Graph Bloat
- **Autonomous Vector Memory Rejected**: Autonomous agent memory introduces prompt poisoning risks, token bloat (>15s latency), and arithmetic hallucinations.
- **Our Clean Memory Model**:
  1. *Short-Term Session*: Last 3–5 chat messages for conversational follow-ups.
  2. *The Database IS Long-Term Memory*: Exact SQL queries (`SELECT SUM(amount)...`) provide 100% deterministic historical truth.

---

## 4. Phased Sprint Roadmap & Verified Milestones

All 6 development sprints are complete and verified against the test suite (**863 passed tests, 1 skipped**):

```
Sprint 1: Deterministic Math Core (services/calculations/) — VERIFIED (863 Tests Passing)
  • Scope: 25+ pure Python decimal.Decimal financial routines: DAB carry-forward, cash analysis,
    overdraft forecasting, weekly volatility CV, CCC, DSCR/FCCR, Altman Z', DuPont ROE,
    ROIC/EVA, DCF/WACC, SaaS metrics, trade credit APR, currency conversion for 160+ ISO currencies.
  • Status: 100% passing pytest suite across deterministic financial fixtures.

Sprint 2: Data Ingestion & Privacy Shield (services/ingestion/) — VERIFIED
  • Scope: Multi-format CSV and PDF statement parsers with balance tie-out, row-level error provenance,
    and pre-flight PII redaction.
  • Status: Verified with test statement files; zero raw PII emitted in external payloads.

Sprint 3: Risk Forecaster & Underwriting Matcher (services/risk/ & services/matcher/) — VERIFIED
  • Scope: Predictive cash crunch overdraft pinpointing, continuous liquidity scoring (0-100),
    ZenEngine JSON decision tables, and Truth-in-Lending APR enforcement.
  • Status: Predatory loans >36% APR flagged; gray-zone financing triage verified.

Sprint 4: Three-Tier Security Gate (services/security/) — VERIFIED
  • Scope: Staging queue (action_intents), tenant isolation, and owner-sent Tier 3 requests.
  • Status: No execution route exists; zero funds can move through the system.

Sprint 5: Consortium Blockchain Anchor (contracts/ & services/blockchain/) — VERIFIED
  • Scope: InvoiceRegistry.sol on FISCO BCOS + canonical SHA-256 invoice hashing.
  • Status: Second concurrent pledge reverts with ERR_INVOICE_ALREADY_PLEDGED.

Sprint 6: Next.js Dashboard shell & Universal LLM Bridge (app/ & services/agent/) — PARTIAL
  • Scope: Next.js 14 App Router shell, dynamic model discovery, FastEmbed ONNX semantic router,
    local SLM loader, and live connection testing.
  • Status: API bridge and semantic routing verified by tests. Dashboard UI (settings modal, deficit
    cards, chat) and WebSocket alerts are not implemented; local SLM needs an
    installed base model plus optional torch/transformers dependencies (requirements-local.txt).
```
