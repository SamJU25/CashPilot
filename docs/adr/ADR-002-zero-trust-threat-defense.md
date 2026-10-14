# ADR-002: Zero-Trust Threat Defense & Automated Bypass Neutralization

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Security Guardian, Systems Architect, Lead Orchestrator
- **Scope**: All backend services, AI agent pipelines, database access layers, and consortium smart contracts.

---

## 1. Context & Threat Landscape

Automated offensive security tools (e.g., Strix, REA, Burp Suite, SQLmap, Turbo Intruder, Garak, PyRIT) enable adversaries to execute rapid, multi-vector attacks against web applications and autonomous AI agents:

1. **AI Prompt Injection & Jailbreaking**: Injecting adversarial instructions via untrusted invoice text or transaction notes to trick the LLM into initiating unauthorized actions.
2. **API & Injection Fuzzing**: Mutating payloads to trigger SQL injection, buffer overflows, or deserialization vulnerabilities.
3. **Multi-Tenant Data Snooping (IDOR/BOLA)**: Swapping `tenant_id` parameters to view or tamper with competitor financial data.
4. **Concurrency & Race Conditions**: Flooding endpoints with simultaneous requests to double-spend funds or double-pledge invoices.
5. **Reverse Engineering & Client Tampering**: Disassembling frontend code to uncover API secrets or modify client-side approval logic.

Blacklist-based filters (regex string filters, prompt guardrails, WAF rules) fail because the search space of adversarial mutations is infinite.

---

## 2. Decision: Invariant-Driven Zero-Trust Architecture

We reject detection-only security. We enforce structural impossibility via five physical, mathematical, and cryptographic invariants:

```
[ External Adversary / Automated Exploit Tool ]
                     │
                     ▼
  ┌─────────────────────────────────────────────────────────┐
  │ INVARIANT 1: Type Boundary (Pydantic v2 in Rust)        │ -> Drops malformed payloads (422)
  └──────────────────────────┬──────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ INVARIANT 2: Storage Boundary (PostgreSQL RLS)          │ -> Physically blocks cross-tenant access
  └──────────────────────────┬──────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ INVARIANT 3: Air-Gap Boundary (Action Intent Staging)   │ -> LLM has 0 money-moving credentials
  └──────────────────────────┬──────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ INVARIANT 4: Atomicity Boundary (Row Lock + FISCO BCOS) │ -> Blocks race conditions & double-pledging
  └──────────────────────────┬──────────────────────────────┘
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │ INVARIANT 5: Hardware Physical Boundary (WebAuthn/FIDO2)│ -> TouchID/YubiKey required for execution
  └─────────────────────────────────────────────────────────┘
```

---

## 3. The 5 Defensive Invariants

### Invariant 1: Type Boundary & Parameterized Kernel
- **Attacking Tools Neutralized**: SQLmap, NoSQLmap, Burp Suite Active Scanner, REST/JSON fuzzers.
- **Mechanism**:
  - All input payloads pass through strict Pydantic v2 schemas before reaching business logic.
  - Database queries use `asyncpg` binary protocol with prepared statements. Code and data never mix; SQL injection is mathematically impossible.

### Invariant 2: Tenant Isolation via PostgreSQL Row-Level Security (RLS)
- **Attacking Tools Neutralized**: Autorize, Burp Match/Replace, IDOR/BOLA exploiters.
- **Mechanism**:
  - The database connection sets a local session variable: `SET LOCAL app.current_tenant_id = '...'`.
  - PostgreSQL's storage engine enforces `WHERE tenant_id = current_setting('app.current_tenant_id')` on every read and write.
  - Even if application code has a bug or omits a filter, the database engine returns zero rows.

### Invariant 3: Air-Gapped Financial Execution (Three-Tier Gate)
- **Attacking Tools Neutralized**: Strix LLM fuzzer, Garak, PyRIT, prompt jailbreaks, indirect injection via invoice OCR.
- **Mechanism**:
  - The AI agent runtime has no write credentials to payment gateways or bank wire APIs.
  - The agent can only write to a local `action_intents` table with status `STAGED_PENDING_HITL`.
  - Even if an attacker gains 100% control over the LLM output, the LLM produces a text string, not a transaction.

### Invariant 4: Atomicity & Consortium State Machine
- **Attacking Tools Neutralized**: Turbo Intruder, single-packet race condition exploiters, double-pledging syndicates.
- **Mechanism**:
  - PostgreSQL transactions enforce pessimistic locking (`SELECT ... FOR UPDATE`).
  - Invoice financing relies on FISCO BCOS smart contract state transitions (`UNREGISTERED` -> `PLEDGED` -> `SETTLED`).
  - Once an invoice hash is marked `PLEDGED`, any subsequent attempt by any bank node is rejected by PBFT consensus.

### Invariant 5: Hardware-Bound Physical Authorization (WebAuthn / FIDO2)
- **Attacking Tools Neutralized**: Session hijacking, stolen JWT tokens, remote botnet execution.
- **Mechanism**:
  - Moving funds (Tier 3 execution) requires a cryptographic signature generated inside the user's hardware Secure Enclave (Apple TouchID, Windows Hello, YubiKey).
  - The private key never leaves the physical silicon chip. No remote script, AI agent, or network attacker can forge this signature.

---

## 4. Consequences & Verification Plan

- **Positive**: Eliminates entire classes of automated exploits at the architectural level.
- **Audit Verification**:
  1. Pytest suite testing SQL injection payloads against all endpoints (`tests/security/test_injection.py`).
  2. Multi-tenant RLS isolation test verifying 0-row leakage (`tests/security/test_rls.py`).
  3. Race condition stress test sending 100 concurrent pledges for 1 invoice (`tests/security/test_concurrency.py`).
  4. Prompt injection evaluation suite verifying that malicious prompts only produce staged intents (`tests/security/test_prompt_injection.py`).
