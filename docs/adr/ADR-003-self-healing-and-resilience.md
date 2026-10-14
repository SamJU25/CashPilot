# ADR-003: Automated Self-Healing & Cryptographic State Reconstruction

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Security Guardian, Systems Architect, Lead Orchestrator
- **Scope**: Fault tolerance, crash recovery, ledger state reconstruction, and circuit breaking.

---

## 1. Context & Threat Scenario

If an adversary successfully attacks a component (e.g., poisons an LLM conversation context, corrupts a local table, exhausts memory via API flood, or compromises a single node), the system must detect, isolate, and heal itself automatically without human engineering intervention.

Traditional systems fail under attack because:
1. Mutable records (`UPDATE balances SET amount = ...`) leave no verifiable trail of the pre-attack state.
2. Long-lived stateful AI agents accumulate adversarial context drift.
3. Cascading failures take down the entire platform when a single service degrades.

---

## 2. Decision: 4-Layer Self-Healing Architecture

```
[ Attack / Anomaly Occurs ]
             │
             ▼
  ┌────────────────────────────────────────────────────────┐
  │ LAYER 1: Worker Isolation & Instant Context Flush      │ -> Reboots agent runtime in <50ms
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │ LAYER 2: Circuit Breakers (Fail-Closed Quarantine)     │ -> Freezes write paths, preserves read access
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │ LAYER 3: Append-Only Event Sourcing (No Overwrites)   │ -> Instant state rollback via reverse events
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │ LAYER 4: Consortium Consensus State Reconstruction     │ -> Rebuilds local DB from FISCO BCOS peers
  └────────────────────────────────────────────────────────┘
```

---

## 3. Self-Healing Mechanisms

### Layer 1: Stateless Ephemeral Agents (Context Poisoning Recovery)
- **Problem**: An attacker feeds prompt injection text to manipulate the agent's internal reasoning.
- **Healing Action**:
  - Subagents run as stateless, ephemeral execution units.
  - If schema validation fails or an anomaly guard triggers, the worker process is terminated immediately.
  - Conversation context is flushed to zero. The worker re-spawns from clean, verified database state in under 50 milliseconds.

### Layer 2: Circuit Breakers & Automated Quarantine
- **Problem**: An attacker triggers rapid-fire errors or tries to exhaust backend resources.
- **Healing Action**:
  - Implements the Martin Fowler Circuit Breaker pattern.
  - If error rates exceed 5% within 60 seconds, the circuit transitions from `CLOSED` to `OPEN`.
  - Tier 2 staging and Tier 3 execution paths freeze instantly into read-only quarantine.
  - Dashboards and cash-flow monitoring remain online.
  - After a 30-second cooldown, the circuit enters `HALF-OPEN` and runs a deterministic health probe before resuming writes.

### Layer 3: Append-Only Ledger Rollback (Event Sourcing)
- **Problem**: An invalid or malicious financial record enters the local database.
- **Healing Action**:
  - The database prohibits in-place `UPDATE` and `DELETE` operations on ledger tables.
  - Balances are computed as the sum of immutable event entries (`ledger_entries`).
  - If an audit check flags an inconsistent entry, an automated offsetting entry (`TYPE: REVERSAL`) is inserted.
  - Mathematical integrity is restored within one database transaction tick (0 data loss).

### Layer 4: Consortium Consensus Reconstruction (Catastrophic Local Loss)
- **Problem**: The local server storage is corrupted or completely wiped.
- **Healing Action**:
  - Financial invoice states and pledge commitments live on the FISCO BCOS consortium blockchain.
  - The local recovery worker connects to peer bank nodes, validates cryptographic block hashes (`SHA-256`), and replays smart contract events.
  - The local PostgreSQL database is completely reconstructed to canonical truth automatically.

---

## 4. Verification & Chaos Testing Plan

1. **Agent Kill Test**: Inject malformed payload; verify agent restarts with clean memory in <50ms (`tests/resilience/test_agent_reset.py`).
2. **Circuit Breaker Trip Test**: Simulate 50 consecutive 500 errors; verify writes lock and reads stay active (`tests/resilience/test_circuit_breaker.py`).
3. **Ledger Reversal Test**: Post a bad transaction; verify the system generates an offsetting reversal event within 1 transaction cycle (`tests/resilience/test_event_reversal.py`).
4. **Cold State Rebuild Test**: Drop local ledger tables; verify rebuild from blockchain event logs (`tests/resilience/test_state_reconstruction.py`).
