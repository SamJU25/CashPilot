# ADR-001: Runtime Multi-Agent Topology & Isolation Protocol

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Agentic Architect, Systems Architect, Lead Orchestrator
- **Scope**: Multi-agent orchestration, state schema, subagent runtime isolation.

---

## 1. Context & Problem Statement

The workspace defines 57 specialized developer agents across 7 suites. Running dozens of independent LLM agents concurrently in production introduces:
1. Severe token overhead and latency (>15 seconds per turn).
2. Coordination deadlocks and circular conversational loops.
3. Expanded attack surface for prompt injection and hallucinated calculations.

---

## 2. Decision: 1 Supervisor + 4 Deterministic Squads

We adopt a hub-and-spoke topology with strict role separation:
- **Lead Supervisor**: Context routing, user dialogue, plan explanation.
- **Squad 1: Ingestion & Privacy**: Presidio PII stripping, schema validation.
- **Squad 2: CFO Diagnostics**: Python `decimal.Decimal` financial ratios (runway, burn, DSCR, DAB). No LLM calculations allowed.
- **Squad 3: Risk & Conformal Forecasting**: MAPIE conformal prediction (P10/P50/P90), DSO hazard models.
- **Squad 4: Liquidity Matching & Underwriting**: PuLP Mixed-Integer Linear Programming optimizer, Truth-in-Lending APR validation.
- **Security Gatekeeper**: Three-Tier Permission Matrix, staging ledger, FISCO BCOS contract calls.

---

## 3. Communication Contract

1. All inter-agent data transfer uses typed Pydantic v2 schemas (`ActionIntent`, `CashRunwayReport`, `LoanOfferMatch`).
2. Free-form text generation is restricted to the Lead Supervisor when presenting recommendations to the human user.
3. Mathematical calculations execute strictly in deterministic Python runtime code.
