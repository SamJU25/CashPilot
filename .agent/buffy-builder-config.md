---
name: buffy-builder-config
description: Buffy (Freebuff Desktop) runtime binding for this repo's 57 subagents, 56 skills, and 2 workflows.
---

# Buffy Builder Config — CashPilot

How I (Buffy on Freebuff Desktop) use this repo's builder setup. Read with `AGENTS.md`
(precedence + routing matrix) and `.agent/workflows/sprint-workflow.md` (execution lifecycle).

## 1. Subagents (57 files in `.agent/agents/`, 8 suites)

Counts verified: 0-global 12, 1-orchestration 7, 2-fintech 6, 3-backend 6,
4-frontend 4, 5-security-qa 7, 6-product 6, 7-research 9. All have `name:` + `description:` frontmatter.

Execution mode on this host:
- **Direct Persona Adoption (default):** read the agent's `.md`, adopt its mission/protocols/skills inline.
  This is the only mode for the 57 repo personas — Freebuff `spawn_agents` here exposes
  only `researcher-web`, not repo personas, so never try to spawn e.g. `qa-verifier` by name.
- **Delegation (parallel research only):** use `spawn_agents` with `researcher-web` for independent
  web lookups (max 3 parallel). Repo personas are not spawn targets.
- Routing: follow `AGENTS.md` §3 matrix (task → primary lead + supporting agents + trigger skills).

Known quirk (do not mass-fix): agent files link skills as `.agent/skills/<x>` (repo-root-relative),
so resolve from repo root, not relative to the agent file.

## 2. Skills (56 dirs in `.agent/skills/`, each with `SKILL.md`)

Rule (per `AGENTS.md` §0): before using a skill, read its exact `SKILL.md` and resolve
referenced resources relative to that skill directory. Account-synced skills
(`C:\Users\Sam\.config\freebuff-desktop\account-skills\...`) may live outside this checkout —
never assume they mirror `.agent/skills/`; prefer the repo copy when both exist.

Always-on skills for builder work:
- `verification-before-completion` — no "done/fixed/passing" claim without fresh command output.
- `qa-verifier` — pytest is the completion gate; mock external network/LLM calls, never live-call.
- `doubt-driven-development` — adversarial review before high-stakes/security/cross-boundary decisions.
- `systematic-debugging`, `test-driven-development` — red-green cycle per sprint-workflow §2.
- `source-driven-development` — verify library APIs against official docs, not memory.

## 3. Workflows (`.agent/workflows/`)

- `sprint-workflow.md` — the lifecycle: clean `git status` → bounded 1-2-3 plan → TDD red/green →
  `pytest -q` (823 baseline) + `npm run type-check`/`build` for frontend → graphify sync for Python edits.
- `graphify.md` — AST knowledge graph sync (`python -m graphify update .`); docs-only edits skip rebuild.

## 4. Rules (`.agent/rules/`)

`multi-agent-orchestrator.md` is the orchestration blueprint (12 governance leads, SPEC→PLAN→
EXECUTE→VERIFY→REPAIR loop, 5-cycle circuit breaker, anti-rationalization gate).
`agent-reach.md` constrains research to read-only upstream channels.
