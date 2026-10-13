# SME Finance Copilot — AI Agents & Optimized Skills Registry

This workspace is engineered specifically for building the **Autonomous AI Agent SME Finance Copilot** (FinTechathon 2026 Topic E: AI as a Financial Participant).

To deliver institutional software reliability and support beginners who need **deep domain research and first-principles guidance**, the workspace combines:
- **10 Core Engineering Rules** (`.agent/rules/`).
- **57 Specialized Subagents** across 8 categorized suites (`.agent/agents/`).
- **54 Mission-Critical Skills** across 6 specialized functional domains (`.agent/skills/`).

---

## 1. Multi-Agent Operating Model & Hierarchy Matrix

Antigravity operates as the **Lead Orchestrator**, coordinating high-level architecture through 12 Global Specialists while delegating specialized domain tasks to 45 Project FinTech Specialists:

```
                            LEAD ORCHESTRATOR (Antigravity)
                                           │
  ┌────────────────────────────────────────┴────────────────────────────────────────┐
  ▼                                                                                 ▼
[ 0-global-specialists ]                                                  [ 1 to 7 Project Suites ]
12 Macro Governance Agents                                                45 FinTech Domain Agents
─────────────────────────                                                ─────────────────────────
• research-scout        • qa-verifier                                    • Suite 1: Agentic Orchestration (7)
• agentic-architect     • code-reviewer                                  • Suite 2: FinTech Engine (6)
• systems-architect     • code-optimizer                                 • Suite 3: Backend Platform (6)
• frontend-craft-eng    • prompt-engineer                                • Suite 4: Frontend Dashboard (4)
• security-guardian     • technical-writer                               • Suite 5: Security & QA (7)
• cross-platform-eng    • penetration-tester                             • Suite 6: Product & Pitch (6)
                                                                         • Suite 7: Research Intelligence (9)
```

---

## 2. Complete Skills Registry (54 Curated Skills)

### Category A: Global Engineering Governance & Methodologies (18 Skills)
Governs how every task is planned, reasoned about, communicated, and verified:
1. [`i-have-adhd`](file:///F:/SME%20Finance%20Copilot/.agent/skills/i-have-adhd): ADHD-friendly output: lead with action, number multi-step tasks, restate state, suppress tangents, 5-item lists, zero pleasantries.
2. [`karpathy-guidelines`](file:///F:/SME%20Finance%20Copilot/.agent/skills/karpathy-guidelines): Behavioral guidelines to reduce common LLM mistakes (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution).
3. [`using-superpowers`](file:///F:/SME%20Finance%20Copilot/.agent/skills/using-superpowers): Establishes skill invocation discipline before coding, debugging, or planning.
4. [`writing-plans`](file:///F:/SME%20Finance%20Copilot/.agent/skills/writing-plans): Multi-step implementation planning before touching code.
5. [`brainstorming`](file:///F:/SME%20Finance%20Copilot/.agent/skills/brainstorming): Explores intent, user requirements, and technical trade-offs before creative work.
6. [`grill-me`](file:///F:/SME%20Finance%20Copilot/.agent/skills/grill-me): Stress-tests requirements and design decisions through structured interview rounds.
7. [`doubt-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/doubt-driven-development): Subjects non-trivial architectural decisions to adversarial cross-examination.
8. [`test-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/test-driven-development): Enforces strict Red-Green-Refactor development cycles.
9. [`systematic-debugging`](file:///F:/SME%20Finance%20Copilot/.agent/skills/systematic-debugging): Root-cause investigation before proposing any bug fixes.
10. [`verification-before-completion`](file:///F:/SME%20Finance%20Copilot/.agent/skills/verification-before-completion): Requires fresh terminal command execution and evidence inspection before claiming done.
11. [`source-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/source-driven-development): Grounds every implementation choice in authoritative, official documentation.
12. [`agent-reach`](file:///F:/SME%20Finance%20Copilot/.agent/skills/agent-reach): Autonomous internet research, upstream repository inspection, and zero-config routing.
13. [`graphify`](file:///F:/SME%20Finance%20Copilot/.agent/skills/graphify): Knowledge graph querying, dependency mapping, and automated update synchronization.
14. [`antislop`](file:///F:/SME%20Finance%20Copilot/.agent/skills/antislop): Purpose-gate filtering across UI, copy, and code comments.
15. [`taste-skill`](file:///F:/SME%20Finance%20Copilot/.agent/skills/taste-skill): Anti-slop frontend styling avoiding generic templates.
16. [`impeccable`](file:///F:/SME%20Finance%20Copilot/.agent/skills/impeccable): Design engineering engine for craft, typography, layout, and finish.
17. [`domain-modeling`](file:///F:/SME%20Finance%20Copilot/.agent/skills/domain-modeling): Maintains ubiquitous domain vocabulary, GLOSSARY.md, and ADRs.
18. [`codebase-design`](file:///F:/SME%20Finance%20Copilot/.agent/skills/codebase-design): Designs domain-centric folder structures and decoupled interfaces.

### Category B: Global Specialist Capabilities (12 Skills)
Specialized engineering execution skills:
19. [`research-scout`](file:///F:/SME%20Finance%20Copilot/.agent/skills/research-scout): Autonomous internet research and upstream repo evaluation.
20. [`agentic-architect`](file:///F:/SME%20Finance%20Copilot/.agent/skills/agentic-architect): Designing AI agent graphs, MCP tools, cognitive loops, and memory.
21. [`systems-architect`](file:///F:/SME%20Finance%20Copilot/.agent/skills/systems-architect): Backend systems, schema design, query plans, zero-downtime migrations.
22. [`frontend-craft-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/frontend-craft-engineer): Modern responsive UI, motion physics, and accessible components.
23. [`security-guardian`](file:///F:/SME%20Finance%20Copilot/.agent/skills/security-guardian): Zero-trust defense, authentication, secret sanitization, OWASP mitigation.
24. [`qa-verifier`](file:///F:/SME%20Finance%20Copilot/.agent/skills/qa-verifier): Deterministic quality assurance, reality-check gates, test suites.
25. [`code-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/code-reviewer): Static code review, cognitive complexity reduction, surgical diffs.
26. [`code-optimizer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/code-optimizer): Profiling, hot-path acceleration, memory leak reduction.
27. [`prompt-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/prompt-engineer): 5-pillar prompt design, behavioral contracts, prompt evals.
28. [`technical-writer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/technical-writer): Clear developer docs, API references, tutorials, runnable snippets.
29. [`cross-platform-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/cross-platform-engineer): Desktop (Tauri/Electron) and mobile app engineering.
30. [`penetration-tester`](file:///F:/SME%20Finance%20Copilot/.agent/skills/penetration-tester): Red-team testing, attack surface mapping, exploit validation.

### Category C: Financial Research & Deep-Dive Learning (10 Skills)
Enables beginners to research, explore, and comprehend complex market concepts:
31. [`earnings-analysis`](file:///F:/SME%20Finance%20Copilot/.agent/skills/earnings-analysis): Analyzes corporate earnings releases and financial statements.
32. [`sector-overview`](file:///F:/SME%20Finance%20Copilot/.agent/skills/sector-overview): Deep-dive SME sector dynamics, credit supply, and industry tailwinds.
33. [`competitive-analysis`](file:///F:/SME%20Finance%20Copilot/.agent/skills/competitive-analysis): Competitor feature matrices and pricing models (Brex, Ramp, WeBank).
34. [`comps-analysis`](file:///F:/SME%20Finance%20Copilot/.agent/skills/comps-analysis): Peer multiples and comparative financial benchmarking.
35. [`deal-screening`](file:///F:/SME%20Finance%20Copilot/.agent/skills/deal-screening): Evaluates SME eligibility against bank underwriting criteria.
36. [`dcf-model`](file:///F:/SME%20Finance%20Copilot/.agent/skills/dcf-model): Teaches and calculates discounted cash flow valuations and projections.
37. [`audit-xls`](file:///F:/SME%20Finance%20Copilot/.agent/skills/audit-xls): Audits spreadsheet formulas for mathematical logic errors.
38. [`xlsx-author`](file:///F:/SME%20Finance%20Copilot/.agent/skills/xlsx-author): Generates clean Excel financial models with live formulas.
39. [`pptx-author`](file:///F:/SME%20Finance%20Copilot/.agent/skills/pptx-author): Generates PowerPoint presentation decks and briefing outlines.
40. [`kyc-doc-parse`](file:///F:/SME%20Finance%20Copilot/.agent/skills/kyc-doc-parse): Extracts structured data from commercial registrations and business tax IDs.

### Category D: FinTech Engine & Underwriting Math (5 Skills)
Executes deterministic financial calculations:
41. [`3-statement-model`](file:///F:/SME%20Finance%20Copilot/.agent/skills/3-statement-model): Three-statement financial models linking Cash Flow, Balance Sheet, and P&L.
42. [`clean-data-xls`](file:///F:/SME%20Finance%20Copilot/.agent/skills/clean-data-xls): Ingests and normalizes raw bank transaction exports and POS CSVs.
43. [`gl-recon`](file:///F:/SME%20Finance%20Copilot/.agent/skills/gl-recon): Reconciles General Ledger bank receipts against customer invoices.
44. [`unit-economics`](file:///F:/SME%20Finance%20Copilot/.agent/skills/unit-economics): Calculates monthly burn rate, cash runway, and Cash Conversion Cycle.
45. [`kyc-rules`](file:///F:/SME%20Finance%20Copilot/.agent/skills/kyc-rules): Automated KYC/AML verification rules and underwriting pre-qualification.

### Category E: Full-Stack Web & Payment Engineering (4 Skills)
Builds production-grade microservices and dashboard interfaces:
46. [`fastapi-backend-craft`](file:///F:/SME%20Finance%20Copilot/.agent/skills/fastapi-backend-craft): Asynchronous FastAPI routers, Pydantic v2 schemas, and dependency injection.
47. [`nextjs-react-dashboard`](file:///F:/SME%20Finance%20Copilot/.agent/skills/nextjs-react-dashboard): Next.js App Router, React Server Components, and Recharts financial charts.
48. [`postgres-db-design`](file:///F:/SME%20Finance%20Copilot/.agent/skills/postgres-db-design): PostgreSQL relational schemas, transaction atomicity, and index strategy.
49. [`stripe-payments-integration`](file:///F:/SME%20Finance%20Copilot/.agent/skills/stripe-payments-integration): Idempotent payment webhooks, payout handling, and fee calculations.

### Category F: Security, QA & Tooling (5 Skills)
Guarantees institutional safety and verification:
50. [`three-tier-security-gate`](file:///F:/SME%20Finance%20Copilot/.agent/skills/three-tier-security-gate): Enforces Tier 1 Observation -> Tier 2 Staging -> Tier 3 HITL 2FA Execution.
51. [`prompt-injection-defense`](file:///F:/SME%20Finance%20Copilot/.agent/skills/prompt-injection-defense): Defends against malicious user inputs in invoices or document text.
52. [`pytest-financial-testing`](file:///F:/SME%20Finance%20Copilot/.agent/skills/pytest-financial-testing): PyTest test suites with exact decimal assertions for cash flow edge cases.
53. [`mcp-builder`](file:///F:/SME%20Finance%20Copilot/.agent/skills/mcp-builder): Exposes financial engines to LLMs via Model Context Protocol tools.
54. [`subagent-catalog`](file:///F:/SME%20Finance%20Copilot/.agent/skills/subagent-catalog): Dynamic discovery tool to search and fetch any external specialist on-demand.

---

## 3. Subagent Suites Directory (57 Specialized Subagents)

### Suite 0: Global Governance Specialists (`.agent/agents/0-global-specialists/`)
- [`research-scout`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/research-scout.md): Upstream documentation discovery and external research.
- [`agentic-architect`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/agentic-architect.md): AI multi-agent workflows, state schemas, and cognitive architectures.
- [`systems-architect`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/systems-architect.md): Backend systems design, database schemas, and API contracts.
- [`frontend-craft-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/frontend-craft-engineer.md): Accessible, animated, high-craft web interfaces.
- [`security-guardian`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/security-guardian.md): Zero-trust security defense, secret hygiene, and permission enforcement.
- [`qa-verifier`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/qa-verifier.md): Deterministic test execution and completion certification.
- [`code-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/code-reviewer.md): Static code review, architectural alignment, and surgical diffs.
- [`code-optimizer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/code-optimizer.md): Performance benchmarking, query tuning, and latency reduction.
- [`prompt-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/prompt-engineer.md): 5-pillar prompt contracts and eval suites.
- [`technical-writer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/technical-writer.md): Documentation, guides, and runnable API specifications.
- [`cross-platform-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/cross-platform-engineer.md): Desktop and mobile application packaging and bridges.
- [`penetration-tester`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/penetration-tester.md): Offensive red-team attack simulation and vulnerability audits.

### Suite 1: Agentic AI Orchestration (`.agent/agents/1-agentic-orchestration/`)
- [`workflow-orchestrator`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/workflow-orchestrator.md): Coordinates end-to-end task flows across subagent squads.
- [`multi-agent-coordinator`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/multi-agent-coordinator.md): Manages parallel agent handoffs and context routing.
- [`llm-architect`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/llm-architect.md): Designs model selection, prompt pipelines, and token budgeting.
- [`copilot-prompt-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/copilot-prompt-engineer.md): Authors XML-bounded prompts and domain copilot guardrails.
- [`mcp-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/mcp-developer.md): Implements Model Context Protocol servers and tool schemas.
- [`context-manager`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/context-manager.md): Compresses memory, summaries, and prevents context saturation.
- [`ai-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/1-agentic-orchestration/ai-engineer.md): Implements core AI agent reasoning loops and fallback logic.

### Suite 2: FinTech Engine & Blockchain (`.agent/agents/2-fintech-engine/`)
- [`sme-cfo-diagnostician`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/sme-cfo-diagnostician.md): Calculates financial health, DAB, and Cash Conversion Cycle.
- [`risk-manager`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/risk-manager.md): Detects cash deficits, overdraft likelihood, and revenue volatility.
- [`credit-options-matcher`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/credit-options-matcher.md): Matches pre-qualified financing options and converts factor rates to APR.
- [`fintech-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/fintech-engineer.md): Implements deterministic Decimal calculation routines.
- [`payment-integration`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/payment-integration.md): Integrates payment gateway rails, webhooks, and ledger entries.
- [`blockchain-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/blockchain-developer.md): Implements SHA-256 invoice hashing and FISCO BCOS on-chain logic.

### Suite 3: Backend Platform (`.agent/agents/3-backend-platform/`)
- [`fastapi-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/fastapi-developer.md): Asynchronous API development and request validation.
- [`backend-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/backend-developer.md): Application services and business logic orchestration.
- [`api-designer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/api-designer.md): OpenAPI contract design and response schema specification.
- [`auth-integration-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/auth-integration-engineer.md): JWT tokens, session lifecycle, and RBAC middleware.
- [`postgres-pro`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/postgres-pro.md): PostgreSQL table designs, indexing, and connection pooling.
- [`database-optimizer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/database-optimizer.md): Query optimization, EXPLAIN ANALYZE tuning, and locking minimization.

### Suite 4: Frontend Dashboard (`.agent/agents/4-frontend-dashboard/`)
- [`nextjs-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/4-frontend-dashboard/nextjs-developer.md): Next.js App Router and server-rendered dashboards.
- [`react-specialist`](file:///F:/SME%20Finance%20Copilot/.agent/agents/4-frontend-dashboard/react-specialist.md): Reusable interactive React components with 4-state handling.
- [`ui-designer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/4-frontend-dashboard/ui-designer.md): Clean typography, monospace tabular numbers, and design token consistency.
- [`websocket-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/4-frontend-dashboard/websocket-engineer.md): Real-time streaming for live cash alerts and agent status.

### Suite 5: Security, Compliance & QA (`.agent/agents/5-security-qa/`)
- [`three-tier-security-gatekeeper`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/three-tier-security-gatekeeper.md): Enforces Tier 1 Observation $\to$ Tier 2 Staging $\to$ Tier 3 HITL 2FA.
- [`security-auditor`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/security-auditor.md): Codebase-wide vulnerability scans and secret hygiene audits.
- [`compliance-auditor`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/compliance-auditor.md): Truth-in-lending compliance, APR disclosure, and data privacy.
- [`architect-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/architect-reviewer.md): Structural boundary reviews and architectural integrity.
- [`qa-expert`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/qa-expert.md): Quality assurance strategy and test plan definition.
- [`test-automator`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/test-automator.md): Automated pytest suites and API integration testing.
- [`debugger`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/debugger.md): Root-cause diagnosis and reproduction of runtime errors.

### Suite 6: Product & Hackathon Pitch (`.agent/agents/6-product-pitch/`)
- [`product-manager`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/product-manager.md): Hackathon evaluation rubric alignment (40% Task, 30% Security, 30% Innovation).
- [`first-principles-thinking`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/first-principles-thinking.md): Deconstructs SME business problems to core mathematical truths.
- [`project-idea-validator`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/project-idea-validator.md): Validates feature feasibility and commercial viability.
- [`docker-expert`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/docker-expert.md): Multi-stage container builds and compose deployment.
- [`product-docs-writer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/product-docs-writer.md): Clean documentation, 30-second setup guide, and pitch specs.
- [`pitch-agent`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/pitch-agent.md): Authors pitch slide outlines and demonstration walkthroughs.

### Suite 7: Research & Intelligence Squad (`.agent/agents/7-research-intelligence/`)
*Dedicated support squad for beginners to investigate, understand, and learn finance:*
- [`research-analyst`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/research-analyst.md): Synthesizes complex topics into clear, beginner-friendly explanations.
- [`statement-auditor`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/statement-auditor.md): Breaks down 3-statement accounting, working capital, and cash conversion.
- [`market-researcher`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/market-researcher.md): Researches SME demographics, credit demand, and banking trends.
- [`competitive-analyst`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/competitive-analyst.md): Evaluates competitor products (Brex, Ramp, WeBank) and fee structures.
- [`earnings-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/earnings-reviewer.md): Analyzes commercial revenue streams and quarterly disclosures.
- [`data-researcher`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/data-researcher.md): Curates benchmark datasets and transactional sample feeds.
- [`search-specialist`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/search-specialist.md): Discovers authoritative technical and financial sources.
- [`scientific-literature-researcher`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/scientific-literature-researcher.md): Researches academic literature on credit scoring and AI agents.
- [`trend-analyst`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/trend-analyst.md): Tracks fintech industry shifts and regulatory guidelines.

---

## 4. Andrej Karpathy × Superpowers Decision Engine (When to Use Which Agent, Skill & Rule)

Every engineering action in this repository is governed by the synthesis of **Andrej Karpathy's 4 Coding Principles** and the **Superpowers 5-Gate Engineering Workflow**. Use this decision table to determine the exact agent, skill, and rule combination for any development state:

### 4.1 Gate-by-Gate Engineering Decision Matrix

| Workflow Gate | Karpathy Principle | When to Use Which Agent | When to Use Which Skill | Optimized Rules Enforced | Gate Exit Condition |
|---|---|---|---|---|---|
| **Gate 1: Intent & Spec Alignment** | **1. Think Before Coding**:<br>• Don't assume.<br>• Don't hide confusion.<br>• Surface trade-offs upfront. | • [`prompt-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/prompt-engineer.md): Refines vague, informal prompts into testable specs.<br>• [`research-scout`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/research-scout.md): Surfaces external docs/repos.<br>• [`research-analyst`](file:///F:/SME%20Finance%20Copilot/.agent/agents/7-research-intelligence/research-analyst.md): Explains financial concepts to beginners. | • [`writing-plans`](file:///F:/SME%20Finance%20Copilot/.agent/skills/writing-plans): Multi-step tasks.<br>• [`brainstorming`](file:///F:/SME%20Finance%20Copilot/.agent/skills/brainstorming): New features/UI.<br>• [`karpathy-guidelines`](file:///F:/SME%20Finance%20Copilot/.agent/skills/karpathy-guidelines): Explicitly state assumptions. | • [`superpowers.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/superpowers.md) (Intent Gate)<br>• [`multi-agent-orchestrator.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/multi-agent-orchestrator.md) (Interactive Consultation)<br>• [`agent-reach.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/agent-reach.md) | User confirms structured plan and assumptions before touching code. |
| **Gate 2: Interactive Grilling & Simplicity** | **2. Simplicity First**:<br>• Minimum code that works.<br>• Nothing speculative (YAGNI).<br>• No single-use abstractions. | • [`first-principles-thinking`](file:///F:/SME%20Finance%20Copilot/.agent/agents/6-product-pitch/first-principles-thinking.md): Cuts unnecessary layers.<br>• [`systems-architect`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/systems-architect.md): Evaluates schema simplicity.<br>• [`sme-cfo-diagnostician`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/sme-cfo-diagnostician.md): Grounds metrics in math. | • [`grill-me`](file:///F:/SME%20Finance%20Copilot/.agent/skills/grill-me): Interactive design rounds.<br>• [`doubt-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/doubt-driven-development): Adversarial cross-examination.<br>• [`antislop`](file:///F:/SME%20Finance%20Copilot/.agent/skills/antislop): Eliminates UI/code fluff. | • [`ponytail.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/ponytail.md) (The Ladder: YAGNI, reuse, stdlib)<br>• [`domain-alignment.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/domain-alignment.md)<br>• [`no-ai-slop.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/no-ai-slop.md) | Simplest viable architecture agreed upon with user. |
| **Gate 3: Test-Driven Development (TDD)** | **4. Goal-Driven Execution**:<br>• Transform tasks into verifiable goals.<br>• Write failing tests first. | • [`fintech-engineer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/2-fintech-engine/fintech-engineer.md): Decimal math fixtures.<br>• [`fastapi-developer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/3-backend-platform/fastapi-developer.md): API contract tests.<br>• [`test-automator`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/test-automator.md): PyTest suite authoring. | • [`source-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/source-driven-development): Ground in official docs.<br>• [`test-driven-development`](file:///F:/SME%20Finance%20Copilot/.agent/skills/test-driven-development): Red-Green-Refactor.<br>• [`pytest-financial-testing`](file:///F:/SME%20Finance%20Copilot/.agent/skills/pytest-financial-testing): Edge-case testing. | • [`superpowers.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/superpowers.md)<br>• [`multi-agent-orchestrator.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/multi-agent-orchestrator.md) (Anti-Rationalization Gate) | Failing test committed/executed before writing implementation code. |
| **Gate 4: Root-Cause Debugging & Surgical Edits** | **3. Surgical Changes**:<br>• Touch only what you must.<br>• Fix root cause once; grep all callers.<br>• Match existing style. | • [`debugger`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/debugger.md): Traces stack traces to origin.<br>• [`code-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/code-reviewer.md): Enforces minimal surgical diffs.<br>• [`architect-reviewer`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/architect-reviewer.md): Checks module isolation. | • [`systematic-debugging`](file:///F:/SME%20Finance%20Copilot/.agent/skills/systematic-debugging): 4-phase root cause analysis.<br>• [`code-optimizer`](file:///F:/SME%20Finance%20Copilot/.agent/skills/code-optimizer): Optimizes hot-path loops without changing behavior. | • [`superpowers.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/superpowers.md) (Root Cause Invariant)<br>• [`ponytail.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/ponytail.md) (Shortest working diff wins) | Root cause fixed at source; all sibling callers verified intact. |
| **Gate 5: Terminal Verification & Graph Sync** | **4. Goal-Driven Execution**:<br>• Define success criteria.<br>• Loop until 100% verified. | • [`qa-verifier`](file:///F:/SME%20Finance%20Copilot/.agent/agents/0-global-specialists/qa-verifier.md): Final completion gatekeeper.<br>• [`security-auditor`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/security-auditor.md): Security/auth verification.<br>• [`compliance-auditor`](file:///F:/SME%20Finance%20Copilot/.agent/agents/5-security-qa/compliance-auditor.md): Truth-in-lending check. | • [`verification-before-completion`](file:///F:/SME%20Finance%20Copilot/.agent/skills/verification-before-completion): Live terminal commands.<br>• [`graphify`](file:///F:/SME%20Finance%20Copilot/.agent/skills/graphify): Syncs AST knowledge graph. | • [`superpowers.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/superpowers.md) (Terminal Proof Invariant)<br>• [`graphify.md`](file:///F:/SME%20Finance%20Copilot/.agent/rules/graphify.md) (Mandatory AST sync) | Fresh terminal output (pytest, build) passing 100%; graphify updated. |

---

### 4.2 Dynamic Task Routing Matrix (Scenario-to-Squad Mapping)


When a user request arrives, the Lead Orchestrator routes execution according to this matrix:

| User Task / Scenario | Primary Lead Agent | Supporting Agents | Triggered Skills |
|---|---|---|---|
| **Domain Research & Explanation** ("How does cash flow work?", "Explain WeBank model") | `research-scout` | `research-analyst`, `statement-auditor` | `agent-reach`, `sector-overview`, `deal-screening` |
| **Architectural Planning** ("Design the SME Copilot system") | `systems-architect` | `agentic-architect`, `first-principles-thinking` | `writing-plans`, `grill-me`, `domain-modeling` |
| **Financial Calculations & Ingestion** ("Calculate runway and DSCR from CSV") | `sme-cfo-diagnostician` | `fintech-engineer`, `postgres-pro` | `clean-data-xls`, `unit-economics`, `3-statement-model` |
| **Predictive Cash Crunch Alerting** ("Warn user about payroll deficit in 30 days") | `risk-manager` | `sme-cfo-diagnostician`, `websocket-engineer` | `unit-economics`, `postgres-db-design` |
| **Digital Underwriting & Matching** ("Match SME with best working capital loan") | `credit-options-matcher` | `risk-manager`, `compliance-auditor` | `deal-screening`, `kyc-rules`, `comps-analysis` |
| **3-Tier Permission Gating** ("Submit loan application or disburse funds") | `three-tier-security-gatekeeper` | `security-guardian`, `compliance-auditor` | `three-tier-security-gate`, `prompt-injection-defense` |
| **Blockchain Invoice Verification** ("Prevent invoice double-financing on FISCO BCOS") | `blockchain-developer` | `systems-architect`, `test-automator` | `postgres-db-design`, `pytest-financial-testing` |
| **Backend API Implementation** ("Build FastAPI routes for cash flow analysis") | `fastapi-developer` | `backend-developer`, `qa-verifier` | `fastapi-backend-craft`, `test-driven-development` |
| **Frontend Dashboard Development** ("Build financial chart and alert UI") | `frontend-craft-engineer` | `nextjs-developer`, `ui-designer` | `nextjs-react-dashboard`, `taste-skill`, `antislop` |
| **Code Review & Verification** ("Audit changes and verify test suite") | `qa-verifier` | `code-reviewer`, `debugger` | `verification-before-completion`, `systematic-debugging` |
| **Knowledge Graph Synchronization** ("Sync code relationships after edits") | `systems-architect` | `technical-writer` | `graphify` (`cmd /c "python -m graphify update ."`) |