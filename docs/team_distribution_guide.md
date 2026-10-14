# SME Finance Copilot: 4-Track Team Distribution & Multi-Phase Workflow Guide

- **Status**: Definitive Team Operational Protocol
- **Date**: 2026-10-14
- **Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)
- **Objective**: Maximize parallel execution, eliminate git merge conflicts, reduce AI token expenditure, and guide each team member through progressive multi-phase sprints.

### Master Documentation Suite:
- 📘 [System Design (`docs/system.md`)](system.md) — Schemas, math models & smart contract specs
- 🏛️ [Architecture Plan (`docs/architecture.md`)](architecture.md) — 6-layer topology & multi-agent squads
- 🛡️ [Security Architecture (`docs/security.md`)](security.md) — 5 Invariants, threat modeling & decadal resilience
- 👥 [Team Distribution Guide (`docs/team_distribution_guide.md`)](team_distribution_guide.md) — 4-track isolated roles & autonomous directives
- ⚡ [Sprint Workflow (`.agent/workflows/sprint-workflow.md`)](../.agent/workflows/sprint-workflow.md) — 5-gate development protocol
- 📜 [Architecture Decision Records (`docs/adr/`)](adr/) — ADR-001 to ADR-007

---

## 1. Role & Capability Mapping (The 4 Disjoint Tracks)

To ensure git merge conflicts are structurally impossible, **each track operates strictly within its designated folder boundary**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ TRACK A: Team Lead & AI Agent Architect                                │
│ • Directory: services/security/, services/llm/, api/                   │
│ • Scope: LiteLLM + Instructor, 3-Tier Gate, WebAuthn challenge, API    │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK B: Frontend & UI/UX Specialist                                   │
│ • Directory: frontend/ (Next.js 14 App Router)                         │
│ • Scope: Visual design, 4-state components, tabular-nums, charts       │
│ • Starter Assets: Pre-built TypeScript types & mock JSON fixtures      │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK C: Financial Calculations & Quantitative Logic Engineer          │
│ • Directory: services/calculations/, services/risk/, services/matcher/ │
│ • Scope: Pure Python decimal.Decimal, MAPIE forecasting, PuLP optimizer│
│ • Starter Assets: Exact math formulas & automated pytest suites        │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK D: Security QA & Consortium Blockchain Engineer                  │
│ • Directory: services/ingestion/, contracts/, tests/security/          │
│ • Scope: CSV parsing, Presidio PII scrubbing, FISCO BCOS contract      │
│ • Starter Assets: Solidity contract template & security attack tests   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Zero-Conflict Git Branching Protocol

Because folder boundaries are mutually exclusive, branch merges execute cleanly without manual conflict resolution:

```
                  ┌──> feat/agent-security-core (Track A - Lead) ────────┐
                  ├──> feat/frontend-dashboard  (Track B - Frontend) ────┼──> main
git checkout main ├──> feat/fintech-engine      (Track C - Calculations) ┤   (Production)
                  └──> feat/blockchain-qa       (Track D - Security/BCOS)┘
```

### Git Branch Setup by Role
1. **Track A (Team Lead)**: `git checkout -b feat/agent-security-core`
2. **Track B (Frontend Specialist)**: `git checkout -b feat/frontend-dashboard`
3. **Track C (Quantitative Engineer)**: `git checkout -b feat/fintech-engine`
4. **Track D (Security & Blockchain Engineer)**: `git checkout -b feat/blockchain-qa`

---

## 3. The Multi-Phase Execution Protocol (The 1-Phase-Per-Turn Rule)

> [!IMPORTANT]
> **Token-Saving Invariant**: Never prompt an agent to build multiple phases in a single turn. Execute **one phase at a time**. Passing multi-phase prompts simultaneously causes context overflow, hallucinations, and broken cross-file imports.

### 3.1 The 4-Step Phase Transition Protocol (Per-Turn Workflow)
Each team member transitions through phases using this 4-step sequence (estimated time: 5-15 minutes per phase):
1. **Submit Turnkey Prompt**: Paste the exact `[TRACK X - PHASE N]` prompt into the coding agent.
2. **Review Plan**: Confirm the agent outputs a bounded 3-step action plan before writing code.
3. **Verify Tests**: Execute the verification command specified in the prompt (`pytest` or `npm test`). Ensure 100% pass rate.
4. **Commit & Reset Context**: Save progress to the branch and clear the agent session:
   ```powershell
   git add .
   git commit -m "feat(track-X): complete phase N"
   ```
   *Always start a fresh conversation or run `/compact` before submitting Phase N+1*. Disk state on the branch serves as the single source of truth; conversational history is not required.

### 3.2 What If a Phase Is Too Large? (Sub-Phase Splitting Rule)
If an agent struggles with a phase, touches more than 3 files, or exceeds 200 lines of changes in one turn, split the phase into decimal sub-phases:
- **Phase N.1 (Data Model & Skeleton)**: Create Pydantic/TypeScript interfaces, stub functions, and base test cases.
- **Phase N.2 (Core Business Logic)**: Implement the pure calculation, service routine, or UI component render logic.
- **Phase N.3 (Edge Cases & Verification)**: Wire error handling, boundary validation, and run full test assertions.

Example Sub-Phase Prompt:
```text
[TRACK C - PHASE 1.1]
Role: Quantitative Logic Engineer | Boundary: services/calculations/
Plan: Output a 3-step action plan to define schemas and test stubs for CFO health ratios in tests/unit/test_calculations.py.
Build: Create test fixtures for Runway, DAB, and DSCR with known input/output pairs.
Verify: Run pytest tests/unit/test_calculations.py and confirm tests fail as expected (Red state).
```

### 3.3 What If Additional Phases Are Needed? (Phase N Creation Formula)
When introducing work beyond the 4 base phases (such as Phase 5 or Phase 6), format the instruction using this exact template:
```text
[TRACK <A/B/C/D> - PHASE <N>]
Role: <Role Title> | Boundary: <designated_folder>/
Plan: Output a 3-step action plan to implement <feature_name> in <target_file> per docs/<spec>.md.
Build: <Concrete implementation requirements, types, and constraints>.
Verify: <Exact terminal command, e.g. pytest tests/<target_test>.py or npm test>.
```

---

## 4. Autonomous Goal-Driven Track Briefs & Agent Kickoff Prompts

Instead of rigid, hardcoded phase scripts, each track operates under an **Autonomous Goal-Driven Model**:
1. The agent reads the master documentation (`docs/system.md`, `docs/architecture.md`, `docs/security.md`).
2. The agent inspects existing starter backbones within its assigned directory boundary.
3. The agent proposes its own incremental implementation plan.
4. The agent writes tests and implements features iteratively, enforcing engineering invariants (0% LLM math, strict types, Three-Tier Gate).

---

### Track A: Team Lead & AI Agent Architect
- **Branch**: `feat/agent-security-core`
- **Assigned Directory Boundary**: `services/security/`, `services/llm/`, `api/`
- **Master References**: `docs/security.md` (Section 1 & 4), `docs/system.md` (Section 4 & 5)
- **Starter Backbones**: `services/security/three_tier_gate.py`, `api/main.py`, `tests/security/test_invariants.py`
- **Core Mission**: Build the Three-Tier Security Gate, LiteLLM + Instructor structured gateway, WebAuthn FIDO2 challenge verifier, and FastAPI REST/WebSocket endpoints.

#### Autonomous Agent Kickoff Prompt:
```text
[TRACK A DIRECTIVE — Security Gate & AI Agentic Gateway]
Role: Team Lead & AI Agent Architect
Boundary: services/security/, services/llm/, api/
Git Branch: feat/agent-security-core
Master Specs: docs/security.md Section 1, docs/system.md Section 4 & 5
Starter Backbone: services/security/three_tier_gate.py, api/main.py

Directive:
1. Plan: Inspect the master specs and existing files in the assigned boundary. Formulate a 3-step action plan to implement the next high-priority capability (e.g. MockLLMGateway with LiteLLM/Instructor in services/llm/, WebAuthn biometric verifier, or mounting /api/v1/runway routes).
2. Build: Implement strictly within the assigned boundary. Enforce Pydantic v2 strict typing (extra="forbid") and ensure high-stakes financial intents require biometric confirmation.
3. Verify: Author pytest test cases in tests/security/ and run pytest to achieve 100% green verification.
```

---

### Track B: Frontend & UI/UX Specialist
- **Branch**: `feat/frontend-dashboard`
- **Assigned Directory Boundary**: `frontend/` (Next.js 14 App Router)
- **Master References**: `docs/system.md` (Section 3 & 4), `docs/architecture.md` (Section 1.1 Form Factor)
- **Starter Backbones**: `frontend/src/types/api.ts`, `frontend/src/mocks/financial_data.json`
- **Core Mission**: Build an executive financial dashboard with monospace tabular numbers (`tabular-nums`), 4-state component handling (Loading, Empty, Error, Populated), interactive Recharts conformal cash corridors, real-time alert drawers, and WebAuthn biometric modals.

#### Autonomous Agent Kickoff Prompt:
```text
[TRACK B DIRECTIVE — Responsive Next.js Executive Dashboard]
Role: Frontend & UI/UX Specialist
Boundary: frontend/
Git Branch: feat/frontend-dashboard
Master Specs: docs/system.md Section 3 & 4, docs/architecture.md Section 1.1
Starter Backbone: frontend/src/types/api.ts, frontend/src/mocks/financial_data.json

Directive:
1. Plan: Inspect frontend/src/types/api.ts and the mock data. Formulate an action plan to implement the dashboard UI components (e.g. Cash Runway Card, 90-Day Conformal Forecast chart, or Live Cash Alert drawer).
2. Build: Implement inside frontend/ using Next.js 14 App Router, Tailwind CSS, and Lucide icons. Enforce monospace tabular formatting (tabular-nums), 4 component states (Loading, Empty, Error, Populated), and Emil Kowalski spring animations (<=280ms).
3. Verify: Verify components render cleanly with zero layout shift (CLS = 0) and execute npm run build or npm test.
```

---

### Track C: Financial Calculations & Quantitative Logic Engineer
- **Branch**: `feat/fintech-engine`
- **Assigned Directory Boundary**: `services/calculations/`, `services/risk/`, `services/matcher/`
- **Master References**: `docs/system.md` (Section 2 - Mathematical Formulations)
- **Starter Backbones**: `services/calculations/runway.py`, `tests/unit/test_calculations.py`
- **Core Mission**: Implement pure Python `decimal.Decimal` financial metrics (Runway, Burn, DAB, DSCR), MAPIE conformal cash forecasting (P10/P50/P90 corridors), Kaplan-Meier DSO hazard modeling, and PuLP MILP liquidity optimization with predatory APR detection (>36%).

#### Autonomous Agent Kickoff Prompt:
```text
[TRACK C DIRECTIVE — Deterministic Quantitative Engine]
Role: Quantitative Logic & Financial Calculations Engineer
Boundary: services/calculations/, services/risk/, services/matcher/
Git Branch: feat/fintech-engine
Master Specs: docs/system.md Section 2 (Math Formulations)
Starter Backbone: services/calculations/runway.py, tests/unit/test_calculations.py

Directive:
1. Plan: Inspect docs/system.md Section 2 and existing code in services/calculations/runway.py. Formulate a 3-step action plan to implement the next mathematical engine (e.g. MAPIE conformal forecaster in services/risk/forecaster.py or PuLP MILP optimizer in services/matcher/liquidity_matcher.py).
2. Build: Implement pure Python decimal.Decimal logic with ROUND_HALF_UP (0% LLM math). Never use floats for monetary values. Flag any facility exceeding 36% APR as predatory.
3. Verify: Author comprehensive pytest test cases in tests/unit/ asserting exact decimal precision and boundary conditions. Run pytest and achieve 100% pass rate.
```

---

### Track D: Security QA & Consortium Blockchain Engineer
- **Branch**: `feat/blockchain-qa`
- **Assigned Directory Boundary**: `services/ingestion/`, `contracts/`, `tests/security/`
- **Master References**: `docs/system.md` (Section 1.2 & 6.1), `docs/security.md` (Section 2 & 5)
- **Starter Backbones**: `services/ingestion/csv_parser.py`, `contracts/InvoiceRegistry.sol`, `tests/security/test_invariants.py`
- **Core Mission**: Bank CSV parsing with Microsoft Presidio PII scrubbing, canonical invoice SHA-256 hashing, FISCO BCOS smart contract integration, and automated adversarial penetration tests (SQLi, IDOR, parameter tampering).

#### Autonomous Agent Kickoff Prompt:
```text
[TRACK D DIRECTIVE — Ingestion, Consortium Blockchain, & Security QA]
Role: Security QA & Consortium Blockchain Engineer
Boundary: services/ingestion/, contracts/, tests/security/
Git Branch: feat/blockchain-qa
Master Specs: docs/system.md Section 1.2 & 6.1, docs/security.md Section 2 & 5
Starter Backbone: services/ingestion/csv_parser.py, contracts/InvoiceRegistry.sol

Directive:
1. Plan: Inspect docs/system.md and docs/security.md. Formulate a 3-step action plan to implement or verify ingestion privacy, smart contract double-pledge prevention, or penetration attack simulations in tests/security/.
2. Build: Implement within the assigned boundary. Ensure all PII (IBANs, phone numbers) is scrubbed before storage, canonical invoice hashes are deterministic, and smart contracts revert duplicate pledge attempts.
3. Verify: Author pytest security test cases asserting PII leakage prevention and invariant defense. Run pytest tests/security/ and achieve 100% pass rate.
```

---

## 5. Branch Integration & Final Security Certification Gate

When all 4 tracks complete their 4 phases:
1. **Ordered Integration Sequence**:
   - Step 1: Merge Track C (`feat/fintech-engine`) into `main`. Run `pytest`.
   - Step 2: Merge Track D (`feat/blockchain-qa`) into `main`. Run `pytest`.
   - Step 3: Merge Track A (`feat/agent-security-core`) into `main`. Run `pytest`.
   - Step 4: Merge Track B (`feat/frontend-dashboard`) into `main`. Disable mock mode (`USE_MOCK_API=false`).
2. **Final System Security Certification**:
   Execute the automated security test suite:
   ```powershell
   pytest tests/security/
   cmd /c "python -m graphify update ."
   ```
   *Passing Criteria*: 100% tests green, zero merge conflicts, zero PII leaks, zero float rounding errors.
