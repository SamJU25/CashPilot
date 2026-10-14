# SME Finance Copilot: Complete Architectural Plan & Governance Blueprint

- **Document Type**: Macro Architecture & Governance Blueprint
- **Status**: Definitive Architectural Plan
- **Date**: 2026-10-14
- **Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

---

## 1. Macro Architecture & Runtime Subagent Topology

The architecture enforces strict decoupling between **Conversational Reasoning (Untrusted)** and **Financial Execution (Deterministically Gated)**:

```
                              [ Human SME Business Owner ]
                                           │
                                           ▼ (WebAuthn Biometrics / Next.js)
                           ┌───────────────────────────────┐
                           │       LEAD ORCHESTRATOR       │
                           │ • User Dialogue & Intent Route│
                           │ • Zero Database Write Rights  │
                           └───────────────┬───────────────┘
                                           │
         ┌──────────────────┬──────────────┴─────┬──────────────────┐
         ▼                  ▼                    ▼                  ▼
  ┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
  │   SQUAD 1    │   │   SQUAD 2    │     │   SQUAD 3    │   │   SQUAD 4    │
  │  Ingestion   │   │  Diagnostic  │     │Risk Forecast │   │ Underwriting │
  │  & Privacy   │   │  CFO Engine  │     │ & Alerting   │   │  & Matching  │
  ├──────────────┤   ├──────────────┤     ├──────────────┤   ├──────────────┤
  │ Presidio PII │   │ Pure Python  │     │ MAPIE bounds │   │ PuLP MILP    │
  │ Pydantic v2  │   │ Decimal math │     │ P10/P50/P90  │   │ True APR >36%│
  └──────────────┘   └──────────────┘     └──────────────┘   └──────────────┘
         │                  │                    │                  │
         └──────────────────┴──────────────┬─────┴──────────────────┘
                                           │ Emits ActionIntent (Draft Only)
                                           ▼
                           ┌───────────────────────────────┐
                           │    THREE-TIER GATEKEEPER      │
                           │ • Tier 1: Read-Only Ledger    │
                           │ • Tier 2: Staged Queue        │
                           │ • Tier 3: WebAuthn 2FA + BCOS │
                           └───────────────────────────────┘
```

---

## 2. Invariant-Driven Threat Defense (Zero-Trust Security)

Security does not rely on fragile heuristic blacklists or regex filters. Defense is anchored in five mathematical and physical invariants:

| Invariant Layer | Threat Vector Neutralized | Defensive Mechanism |
|---|---|---|
| **1. Type Boundary** | SQLmap, Burp Suite, Malformed JSON | Rust-compiled Pydantic v2 schemas reject non-conforming types with HTTP 422 before Python runs. |
| **2. Storage Boundary** | IDOR, BOLA, Multi-Tenant Snooping | PostgreSQL storage engine enforces Row-Level Security (`SET LOCAL app.current_tenant_id`). |
| **3. Air-Gap Boundary** | Strix, Garak, PyRIT, Prompt Injection | LLM has zero write credentials. Can only emit draft proposals into an isolated staging table. |
| **4. Atomicity Boundary** | Turbo Intruder, Concurrency Race Conditions | Database `SELECT FOR UPDATE` locks + FISCO BCOS PBFT consensus prevent duplicate commitments. |
| **5. Hardware Boundary** | Token Hijacking, Remote Botnet Execution | WebAuthn private keys reside in client hardware Secure Enclaves; physical touch required. |

---

## 3. Automated Self-Healing & Resilience Protocol

When attacks, corruptions, or node crashes occur, the system heals across four automated tiers:

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

---

## 4. Secret Hygiene & Blast Radius Containment

1. **Zero-Secret Frontend Invariant**: The client browser contains zero API keys, zero database credentials, and zero private keys.
2. **Blast Radius Decoupling**: The LLM API key has zero authority over bank rails or databases; even if stolen, it can only generate text tokens.
3. **Short-Lived Ephemeral IAM Tokens**: Uses Workload Identity Federation with 60-minute auto-expiry.
4. **Egress IP Pinning & Daily Spend Caps**: Stolen keys cannot be called from outside the backend's static IP; spending is capped at $10/day.
5. **Air-Gapped Local Fallback (Ollama)**: Local inference on `127.0.0.1` requires zero keys and zero internet access.

---

## 5. Decadal Security Blueprint (30-Year Resilience)

1. **Post-Quantum Cryptography (NIST FIPS 203/204)**: Hybrid ML-KEM + ML-DSA dual signatures protect financial audit logs against Harvest-Now-Decrypt-Later quantum attacks.
2. **Formal Verification (TLA+ & Dafny)**: State machine transitions mathematically proven to guarantee mutual exclusion on invoice pledges across infinite interleavings.
3. **Confidential Computing (AMD SEV-SNP)**: Backend processes run in hardware-encrypted memory enclaves; host rootkit memory dumps yield only ciphertext.
4. **Zero-Knowledge Underwriting (zk-SNARKs via Circom)**: SMEs prove $\text{DAB} \ge \$50,000$ and $\text{DSCR} \ge 1.35x$ without exposing raw customer lists or banking data.
5. **Multi-Party Computation (2-of-3 TSS)**: Private keys split into 3 shards (User Device, Bank HSM, Cold Escrow); no single entity holds a master key.

---

## 6. Phased Sprint Roadmap & Milestone Acceptance Criteria

```
Sprint 1: Deterministic Math Core (services/calculations/)
  • Scope: Cash runway, DAB, DSCR, burn rate in Python decimal.Decimal.
  • Acceptance Criteria: 100% passing pytest suite across 100 benchmark transaction sets.

Sprint 2: Data Ingestion & Privacy Shield (services/ingestion/)
  • Scope: Bank CSV parsing, PDF invoice OCR, Microsoft Presidio PII redaction.
  • Acceptance Criteria: Zero raw phone numbers, IBANs, or tax IDs emitted in test payloads.

Sprint 3: Risk Forecaster & Underwriting Matcher (services/risk/ & services/matcher/)
  • Scope: MAPIE conformal prediction (P10/P50/P90) + PuLP MILP financing optimizer.
  • Acceptance Criteria: 90% empirical coverage on backtests; loans >36% APR flagged as predatory.

Sprint 4: Three-Tier Security Gate & WebAuthn (services/security/)
  • Scope: Staging queue (action_intents) + WebAuthn FIDO2 hardware challenge verifier.
  • Acceptance Criteria: Zero funds execute without valid hardware biometric signature.

Sprint 5: Consortium Blockchain Anchor (contracts/ & services/blockchain/)
  • Scope: InvoiceRegistry.sol on FISCO BCOS + canonical SHA-256 invoice hashing.
  • Acceptance Criteria: Second concurrent pledge reverts with ERR_INVOICE_ALREADY_PLEDGED.

Sprint 6: Next.js Executive Dashboard & Live WebSocket Alerts (frontend/)
  • Scope: Monospace tabular UI, Emil Kowalski spring animations, 4-state component protocol.
  • Acceptance Criteria: Zero layout shift; 100% Lighthouse accessibility compliance.
```
