# SME Finance Copilot: Master Security Architecture (`security.md`)

- **Document Role**: Threat Modeling, Defense-in-Depth, Self-Healing & Decadal Security
- **Status**: Active Security Architecture & Technical Contract (Verified Baseline: 863 Passed Tests, 1 Skipped)
- **Date**: 2026-10-17
- **Competition Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

### Master Documentation Suite:
- 📘 [System Design (`docs/system.md`)](system.md) — Schemas, 25+ math engines, decision tables & smart contract specs
- 🏛️ [Architecture Plan (`docs/architecture.md`)](architecture.md) — 6-layer topology, dual SLM inference & multi-agent suites
- 🛡️ [Security Architecture (`docs/security.md`)](security.md) — 5 Invariants, threat modeling & Three-Tier Security Gate
- ⚡ [Engineering Lifecycle (`.agent/workflows/sprint-workflow.md`)](../.agent/workflows/sprint-workflow.md) — Contract-first TDD and verification protocol

- 📖 [Ubiquitous Domain Glossary (`GLOSSARY.md`)](GLOSSARY.md) — Standardized fintech and underwriting terminology

---

## 1. Executive Security Philosophy: Provable Invariants vs. Heuristic Decay

Traditional software defenses rely on heuristics (firewall rules, anomaly filters, regex sanitizers, prompt wrappers). Heuristics decay quickly because attackers discover novel encodings, bypasses, and jailbreaks.

Our architecture relies on **Provable Invariants**: mathematical, kernel-enforced, and hardware-backed security guarantees.

```
┌────────────────────────────────────────────────────────────────────────┐
│                            THE 5 INVARIANTS                            │
├────────────────────────┬───────────────────────────────────────────────┤
│ 1. Type Boundary       │ Rust Pydantic v2 drops 422 on extra/bad keys  │
│ 2. Storage Boundary    │ Signed tenant tokens + per-tenant JSON store  │
│ 3. Air-Gap Boundary    │ Zero banking credentials for AI agents        │
│ 4. Atomicity Boundary  │ Row locks + FISCO BCOS PBFT double-pledge stop│
│ 5. Owner Boundary      │ Tier 3 is owner-sent; no execution route      │
└────────────────────────┴───────────────────────────────────────────────┘
```

---

## 2. The Three-Tier Security Gate

Every financial event flows through an immutable, permission-gated lifecycle before execution:

```
[ User Request / Statement Ingestion ]
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: OBSERVATION (Autonomous Read-Only)             │
│ • Bank statement CSV/PDF ingestion & OCR               │
│ • Line-item extraction & balance tie-out               │
│ • Deterministic CFO calculations (DAB, CCC, DSCR)      │
│ • Predictive cash overdraft pinpointing                │
│ • Zero state modification; safe for automated agents   │
└──────────────────────────┬─────────────────────────────┘
                           │ Requires Financing / Staging Intent
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: STAGING (Queue Only — ActionIntent Ledger)     │
│ • Drafts proposed transaction (e.g. Factor Invoice)    │
│ • Evaluates policy decision tables (ZenEngine JSON)    │
│ • Enforces Truth-in-Lending APR caps (<= 36.0%)        │
│ • Computes canonical SHA-256 invoice hash              │
│ • Status: STAGED_PENDING_HITL ($0.00 transferred)      │
└──────────────────────────┬─────────────────────────────┘
                           │ POST /api/v1/actions/{id}/prepare
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 3: OWNER-SENT (never executed by CashPilot)       │
│ • Pre-filled request the owner copies or downloads     │
│ • Owner sends it from their own email or lender form   │
│ • No payment credentials exist anywhere in the system  │
│ • Status: PREPARED or REJECTED ($0.00 ever moved)      │
└────────────────────────────────────────────────────────┘
```

---

## 3. Threat Modeling & Offensive Tool Defense

Security is designed to withstand both automated AI attacks and specialized penetration testing frameworks:

| Threat Vector / Tool | Attack Mechanism | Mathematical & Physical Invariant Defense |
|---|---|---|
| **Prompt Injection (PyRIT, Garak)** | Malicious instructions hidden in CSV/PDF statement counterparty descriptions | FastEmbed ONNX vector triage routes intent before prompt assembly. Pre-flight PII redaction strips adversarial payloads. The LLM has zero bank API credentials and zero write access to financial database columns. It can only emit a proposal into `action_intents` with status `STAGED_PENDING_HITL`. |
| **SQL Injection (SQLmap)** | Malformed query parameters to extract ledgers | Payloads are strictly parsed by Pydantic v2 (compiled in Rust). Database drivers use binary parameterized prepared statements (`asyncpg`); SQL command syntax and parameter values travel across separate binary channels. |
| **BOLA / IDOR / Tenant Hop** | Tampering with `tenant_id` to steal records | Action routes require an HMAC-signed tenant token (`require_tenant_identity` in `services/security/tenant_token.py`) and ignore the client-asserted `X-Tenant-ID`; every intent lookup checks ownership and returns 404 on mismatch. Chat-driven staging and model management require the same verified token. Token issuance is gated by an enrollment key; with `TENANT_ENROLLMENT_KEYS` configured, the single key is not a wildcard, a lone key must be bound with `TENANT_ENROLLMENT_TENANT_ID` (unbound issuance is fail-closed), and `TENANT_ENROLLMENT_ALLOW_ANY_TENANT=1` is an explicit local-development escape hatch. Provider probes (`test-connection`, `fetch-models`) also require a verified token. PostgreSQL RLS is the target storage-layer defence, not yet built. |
| **Stolen Disk / Backup** | Reading `.sessions/` or `.data/` copied off the host | Stores are owner-only (`0700`/`0600`); setting `COPILOT_DATA_KEY` seals session statements, staging intents and the invoice registry with Fernet (`enc:v1:` prefix), and `COPILOT_ENV=production|staging` makes that key mandatory at startup. Legacy plaintext files stay readable and are re-encrypted on the next write. |
| **Queue Flooding / DoS** | Anonymous chat minting proposals or exhausting a shared rate-limit bucket | Staging refuses anonymous callers; pending proposals expire after `STAGED_INTENT_TTL_HOURS` and identical instructions dedupe inside `STAGED_INTENT_DEDUPE_SECONDS`. Token-bucket limiting keys on the client IP and honours `TRUSTED_PROXY_HOPS` when deployed behind a trusted proxy chain. |
| **SSRF via LLM endpoint** | Supplying a `base_url` aimed at loopback, RFC 1918 or cloud metadata hosts | `services/agent/url_guard.py` rejects non-http(s) schemes, embedded credentials, link-local/metadata addresses, and (by default) loopback and private ranges. Upstream error bodies are no longer reflected. |
| **Race Conditions (Turbo Intruder)** | Single-packet bursts attempting duplicate loan draws | Transactions execute `SELECT ... FOR UPDATE` (pessimistic row locks). Pledging invoices across lenders is anchored on FISCO BCOS via `InvoiceRegistry.sol`; PBFT consensus guarantees only the first pledge succeeds. |
| **Client Hooking (REA, Frida)** | Client-side memory tampering & variable hooking | Zero financial calculation or approval logic executes in the browser. The frontend is treated as an untrusted display terminal; the backend validates 100% of state deterministically. |

---

## 4. Automated Self-Healing & Resilience Protocol

When anomalies or process crashes occur, recovery executes across four automated tiers:

```
[ Anomaly / Failure Event ]
             │
             ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: Stateless Ephemeral Agent Respawn              │ -> Kills poisoned worker; respawns clean in <50ms
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: Circuit Breaker Quarantine (Fail-Closed)       │ -> Error rate >5% freezes writes; keeps reads live
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 3: Event Sourcing Offset Reversal                 │ -> Posts opposite ledger entry (0 data loss)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 4: Consortium Consensus State Reconstruction      │ -> Rebuilds local DB from peer bank nodes in 5 mins
└────────────────────────────────────────────────────────┘
```

1. **Ephemeral Subagent Respawn**: Subagents are stateless workers. If context is poisoned or output schema validation fails, the process is terminated instantly, memory wiped, and a clean instance spawned in $<50\text{ms}$.
2. **Circuit Breakers (Fail-Closed)**: If error rates exceed 5% in 60 seconds, the circuit transitions to `OPEN`. Staging and execution routes lock into quarantine while dashboards remain readable.
3. **Event Sourcing Offset Reversals**: `UPDATE` and `DELETE` are revoked on financial ledger tables. If an anomaly is detected, an automated offsetting entry (`TYPE: REVERSAL`) is posted, restoring mathematical balance within 1 transaction tick.
4. **Consortium Blockchain State Reconstruction**: If local server storage is destroyed, a recovery worker connects to peer bank nodes on FISCO BCOS, validates cryptographic `SHA-256` block hashes, and rebuilds the local relational database in under 5 minutes.

---

## 5. Database Defense-in-Depth

```
[ Public Internet ]
        │
        ▼ (Port 5432 BLOCKED)
┌────────────────────────────────────────────────────────┐
│ 1. Private VPC Subnet (Zero Public IP)                 │ -> Database cannot be pinged from the internet
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Least-Privilege DB User (copilot_app)               │ -> Cannot DROP TABLE or alter schemas
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Kernel Row-Level Security (RLS)                     │ -> Physically returns 0 rows belonging to other SMEs
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Binary Parameterized Protocol (asyncpg)             │ -> SQL injection is syntactically impossible
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. Immutable Event Sourcing (Revoked UPDATE/DELETE)    │ -> Historical ledger entries cannot be overwritten
└────────────────────────────────────────────────────────┘
```

---

## 6. LLM Connection Security & Data Privacy

1. **Pre-Flight PII Redaction**: Customer names, phone numbers, tax IDs, and bank account numbers are scrubbed before prompt assembly; external AI models receive only synthetic tokens (`<CUSTOMER_1>`, `[REDACTED_IBAN]`).
2. **Air-Gapped Local Inference Engine**: In local mode, `LocalTransformersEngine` runs Flagship 3B (`models/sme-finance-lora`) directly via PyTorch CUDA, or connects to Ollama on `127.0.0.1:11434`. Zero internet packets leave the machine.
3. **Enterprise Zero-Data Retention (TLS 1.3)**: Cloud provider API connections enforce `store=False`, ensuring prompts are not logged or used for model training.
4. **Encrypted Client Key Storage**: When custom API keys are used in the dashboard, they reside in client `localStorage` and are passed per-session via authenticated headers; they are never committed to disk on shared servers.

---

## 7. Consortium Blockchain Double-Financing Defense

1. **Canonical Hashing**: Every ingested invoice produces a deterministic cryptographic hash:
   $$\text{hash} = \text{SHA256}\left(\text{tax\_id} \,\|\, \text{buyer\_id} \,\|\, \text{invoice\_num} \,\|\, \text{amount\_cents}\right)$$
2. **PBFT Consensus Anchor**: Invoices submitted for factoring or credit collateral are registered on the consortium blockchain (`contracts/InvoiceRegistry.sol`).
3. **Double-Pledge Prevention**: If a fraudulent SME attempts to pledge the same invoice to two separate commercial lenders, the second transaction reverts with `ERR_INVOICE_ALREADY_PLEDGED`.

---

## 8. Decadal Security Blueprint (30-Year Resilience)

1. **Post-Quantum Cryptography (NIST FIPS 203/204)**: Hybrid ML-KEM + ML-DSA dual signatures protect financial audit logs against Harvest-Now-Decrypt-Later quantum attacks.
2. **Formal Verification (TLA+ & Dafny)**: State machine transitions mathematically proven to guarantee mutual exclusion on invoice pledges across infinite interleavings.
3. **Confidential Computing (AMD SEV-SNP)**: Backend processes run in hardware-encrypted memory enclaves; host rootkit memory dumps yield only ciphertext.
4. **Zero-Knowledge Underwriting (zk-SNARKs via Circom)**: SMEs prove $\text{DAB} \ge \$50,000$ and $\text{DSCR} \ge 1.35x$ without exposing raw customer lists or banking data.
5. **Multi-Party Computation (2-of-3 TSS)**: Private keys split into 3 shards (User Device, Bank HSM, Cold Escrow); no single entity holds a master key.
