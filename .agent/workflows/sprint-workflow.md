---
name: sprint-workflow
description: Mandatory 6-sprint execution protocol for any AI coding agent working on SME Finance Copilot
---

# Master Sprint Execution Workflow (AI Agent Guardrails)

Scope: Any AI coding agent (Antigravity, Claude Code, Cursor, Windsurf, Copilot, Roo, Aider) working in this repository.

> [!IMPORTANT]
> **Zero Deviation Rule**: Do NOT invent features, do NOT write code outside the active sprint, and do NOT skip the 5-Gate Engineering Lifecycle. Always follow this workflow step-by-step.

---

## 1. Required Reading Before Writing Any Code

Before proposing or editing code, every agent MUST inspect:
1. [`docs/system.md`](../../docs/system.md): System design, math formulas, schemas, APIs, and smart contract specs.
2. [`docs/architecture.md`](../../docs/architecture.md): Macro topology, 1-Supervisor + 4-Squads model, and roadmap.
3. [`docs/security.md`](../../docs/security.md): 5 Invariants, threat defense, self-healing, and decadal security.
4. [`docs/team_distribution_guide.md`](../../docs/team_distribution_guide.md): 4-track isolated roles, turnkey agent prompts & branch protocols.
5. [`docs/adr/`](../../docs/adr/): Architectural Decision Records (ADR-001 to ADR-007).

---

## 2. Parallel Track Sprints (Multi-Agent Operating Model)

Tasks execute in parallel across 4 isolated tracks on independent git branches. Each coding agent reads the master documentation (`docs/system.md`, `docs/architecture.md`, `docs/security.md`), plans its own implementation roadmap for its assigned directory boundary, and adheres to the 5-Gate Development Protocol:

```
┌────────────────────────────────────────────────────────────────────────┐
│ TRACK A (Lead): Security Gate & Agentic Gateway                        │
│ Target: services/security/, services/llm/, api/                        │
│ Scope: 3-Tier Security Gate, WebAuthn FIDO2, LiteLLM gateway, APIs     │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK B (Frontend): Next.js Executive Dashboard                        │
│ Target: frontend/                                                      │
│ Scope: Responsive PWA, 4-state components, tabular-nums, charts        │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK C (Quant): Deterministic Financial Calculations & Risk Engine    │
│ Target: services/calculations/, services/risk/, services/matcher/      │
│ Scope: Decimal health metrics, MAPIE conformal forecasting, PuLP MILP  │
├────────────────────────────────────────────────────────────────────────┤
│ TRACK D (Blockchain & QA): Ingestion, Consortium Ledger, & Security QA │
│ Target: services/ingestion/, contracts/, tests/security/               │
│ Scope: Bank CSV parsing + Presidio PII, InvoiceRegistry.sol FISCO BCOS │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The 5-Gate Development Protocol (Per Task)

Every coding task must strictly pass through these 5 gates:

1. **Gate 1 (Think Before Coding)**: Read the task, trace the real call flow, inspect existing code in `services/`.
2. **Gate 2 (Simplicity First - The Ladder)**: Minimum code that works. Reuse helpers. No unnecessary abstractions.
3. **Gate 3 (Test-Driven Development)**: Write failing pytest assertion FIRST, then write implementation until green.
4. **Gate 4 (Surgical Changes)**: Fix root causes once. Never patch symptoms. Minimal working diff wins.
5. **Gate 5 (Terminal Verification & AST Sync)**: Run `pytest` to verify 100% pass, then execute:
   ```powershell
   cmd /c "python -m graphify update ."
   ```
