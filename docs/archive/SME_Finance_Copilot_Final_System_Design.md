# SME Finance Copilot: Final Master System Design & Architectural Plan

- **Status**: Definitive System Architecture Specification
- **Date**: 2026-10-14
- **Competition Target**: FinTechathon 2026 (Tsinghua University PBCSF & WeBank) — Track E: AI as a Financial Participant
- **Scoring Alignment**: 40% Task Completion, 30% Security & Compliance, 30% Innovation & Interaction, +5 Pts Consortium Blockchain

---

## 1. End-to-End System Topology (6 Structural Layers)

```
[ User Browser / Mobile Device ]
            │ (TLS 1.3 + WebAuthn Hardware Biometrics)
            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: CLIENT PRESENTATION (Next.js 14 App Router)                   │
│ • Monospace tabular figures (font-variant-numeric: tabular-nums)       │
│ • Emil Kowalski spring motion (<300ms transitions)                     │
│ • Zero API keys, zero local financial calculation authority           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP-Only RS256 Cookies
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: API GATEWAY & SECURITY INGRESS (FastAPI + Nginx)              │
│ • Token-bucket rate limiting (60 req/min per IP)                       │
│ • Rust-compiled Pydantic v2 strict type validation (extra="forbid")    │
│ • Automated 422 drop for malformed payloads before execution          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: AGENTIC SUPERVISOR (LiteLLM + Instructor + Pydantic v2)       │
│ • Context Packager: Injects deterministic backend numbers into prompt  │
│ • Conversational synthesis: Gemini 2.0 / GPT-4o / DeepSeek / Ollama    │
│ • Strict JSON output: CopilotResponse schema enforced by Instructor    │
│ • Zero Write Credentials: Emits ActionIntent drafts only               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Internal Invocations
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 4: DETERMINISTIC COMPUTATION ENGINE (Pure Python & Algorithms)   │
│ • Squad 1 (Ingestion): Microsoft Presidio PII stripping + CSV parser   │
│ • Squad 2 (CFO Diagnostics): Pure Python decimal.Decimal ratios        │
│ • Squad 3 (Risk Forecasting): MAPIE conformal prediction (P10/P50/P90) │
│ • Squad 4 (Underwriting): PuLP MILP cost minimizer + APR check (>36%)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 5: STORAGE & DATA SECURITY (PostgreSQL 16 + RLS)                 │
│ • Isolated Private VPC Subnet (No public IP assigned to port 5432)     │
│ • Kernel Row-Level Security: SET LOCAL app.current_tenant_id           │
│ • Event Sourcing: Immutable ledger_entries (UPDATE/DELETE forbidden)  │
│ • Staging Ledger: action_intents awaiting WebAuthn physical signature  │
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

## 2. Deep Reasoning & Verification for Every Component Selection

Every component in this architecture has been chosen to eliminate specific failure modes:

### Selection 1: Pure Python `decimal.Decimal` (Calculation Engine)
- **Problem Solved**: Floating-point binary rounding errors (`0.1 + 0.2 == 0.30000000000000004`) and LLM arithmetic hallucinations.
- **Deep Rationale**: In banking, currency calculations must be exact to 2 decimal places using deterministic half-up rounding (`ROUND_HALF_UP`). Giving calculation duties to an LLM is a fatal design defect.
- **Alternative Rejected**: JavaScript `Number` (binary float IEEE-754) and LLM prompt arithmetic.
- **Verification Method**: Pytest financial test suite verifying exact runway and burn calculations across 100 benchmark transaction sets with zero floating-point drift.

### Selection 2: Microsoft Presidio PII Masking (Ingestion Layer)
- **Problem Solved**: Corporate espionage, data mining, and GDPR/CCPA violations caused by sending customer names, phone numbers, and bank account details to third-party LLM cloud servers.
- **Deep Rationale**: By sanitizing text on the local host before API dispatch, the cloud model sees only aggregated financial figures and synthetic tokens (`<CUSTOMER_1>`, `[REDACTED_IBAN]`).
- **Alternative Rejected**: Relying on commercial LLM provider privacy promises.
- **Verification Method**: Automated regex and Presidio entity scans on all outgoing HTTP payloads to external LLMs; test fails if any IBAN or phone pattern is detected.

### Selection 3: MAPIE Conformal Prediction (Risk Engine)
- **Problem Solved**: Deceptive single-point cash predictions that fail to warn of worst-case liquidity shortfalls.
- **Deep Rationale**: Conformal prediction generates mathematically guaranteed coverage intervals (P10 pessimistic, P50 median, P90 optimistic). An SME needs to know their worst-case payroll shortfall date, not a naive average.
- **Alternative Rejected**: Uncalibrated linear regression or black-box LSTM forecasts.
- **Verification Method**: Backtesting across historical transaction splits; verify that 90% of actual future cash balances fall within the predicted conformal bounds.

### Selection 4: PuLP Mixed-Integer Linear Programming (Underwriting Matcher)
- **Problem Solved**: Sub-optimal financing selection and predatory lending traps.
- **Deep Rationale**: Formulates liquidity matching as an optimization problem:
  $$\min \sum c_i \cdot x_i \quad \text{subject to} \quad \sum x_i \ge \text{Deficit}, \quad \text{APR}_i \le 36\%$$
  Guarantees the lowest total interest cost while enforcing truth-in-lending rules.
- **Alternative Rejected**: LLM recommendation heuristics (prone to ranking bias and unverified fees).
- **Verification Method**: Mathematical verification showing total interest minimized across competing products (credit line vs invoice factoring) with predatory APR flags triggered at $>36.0\%$.

### Selection 5: WebAuthn / FIDO2 Biometric Execution (Tier 3 Gate)
- **Problem Solved**: Account takeover, session hijacking, stolen API keys, and prompt injection disbursements.
- **Deep Rationale**: Moving money requires a cryptographic signature generated inside the user device's hardware Secure Enclave. Private keys never leave physical silicon. A remote attacker or compromised LLM cannot forge a physical touch.
- **Alternative Rejected**: SMS OTP (vulnerable to SIM swapping) and bearer JWT tokens (vulnerable to XSS theft).
- **Verification Method**: Test suite injecting fake approvals; verify that the payment service rejects any execution attempt missing a valid hardware-signed challenge.

### Selection 6: PostgreSQL Kernel Row-Level Security (RLS)
- **Problem Solved**: Broken Object Level Authorization (BOLA/IDOR) and cross-tenant data leaks.
- **Deep Rationale**: Enforces tenant boundary directly inside the PostgreSQL database engine (`app.current_tenant_id`). Even if application code contains a bug or omits a `WHERE` clause, PostgreSQL returns 0 rows belonging to another company.
- **Alternative Rejected**: Relying solely on application-layer `WHERE tenant_id = ...` filters in Python.
- **Verification Method**: Execute raw `SELECT * FROM invoices` without a `WHERE` clause under Tenant A's connection; verify that zero rows from Tenant B are returned.

### Selection 7: FISCO BCOS Consortium Blockchain (`InvoiceRegistry.sol`)
- **Problem Solved**: Invoice double-financing fraud across multiple independent banks.
- **Deep Rationale**: Independent banks do not share private relational databases. A consortium blockchain provides a shared state machine with PBFT consensus. Once an invoice hash is marked `PLEDGED`, any subsequent pledge by any participating bank reverts.
- **Alternative Rejected**: Public Ethereum (unacceptable gas fees and zero commercial privacy) or centralized clearinghouses (single point of failure).
- **Verification Method**: Submit duplicate invoice pledge transactions 5 milliseconds apart; verify that the second transaction reverts with `ERR_INVOICE_ALREADY_PLEDGED`.

### Selection 8: Rootless & Read-Only Container Infrastructure
- **Problem Solved**: Container breakout, root privilege escalation, and malware installation.
- **Deep Rationale**: Container runs as unprivileged `UID 10001` with `--read-only` root filesystem and `--cap-drop=ALL`. Even under Remote Code Execution (RCE), an attacker cannot alter binaries or download scripts.
- **Alternative Rejected**: Default Docker root containers with writable root filesystems.
- **Verification Method**: Container security audit running `whoami` (returns appuser) and attempting `touch /bin/test` (fails with Read-only file system).

---

## 3. Sprint-by-Sprint Execution Roadmap

```
Sprint 1: Deterministic Math Core (services/calculations/)
  └── Cash runway, DAB, DSCR, Burn rate in Python decimal.Decimal + Pytest

Sprint 2: Ingestion & Privacy Shield (services/ingestion/)
  └── Bank CSV parsing, PDF invoice extraction, Presidio PII redaction

Sprint 3: Risk Forecaster & Underwriting Matcher (services/risk/ & services/matcher/)
  └── MAPIE conformal bounds (P10/P50/P90) + PuLP financing optimizer

Sprint 4: Three-Tier Security Gate & WebAuthn (services/security/)
  └── Staging ledger (action_intents) + WebAuthn FIDO2 challenge verifier

Sprint 5: Consortium Blockchain Anchor (contracts/ & services/blockchain/)
  └── InvoiceRegistry.sol on FISCO BCOS + canonical SHA-256 invoice hashing

Sprint 6: Next.js Executive Dashboard & Live WebSocket Alerts (frontend/)
  └── Monospace tabular data cards, Emil Kowalski spring animations, 4-state UI
```
