---
trigger: model_decision
description: Stress-test requirements using structured grilling rounds and enforce ubiquitous domain vocabulary in code.
---

# Domain Alignment & Grilling Protocol

Scope: Antigravity and Claude coding assistants.

## 1. Grilling Rounds
- Identify unsettled decisions and group them into a single round.
- Format each item with question title, context, and a recommended default.
- Never make arbitrary assumptions on architectural trade-offs without grilling first.

## 2. Ubiquitous Vocabulary
- Ensure symbol names in TypeScript/Node directly match terms in `docs/GLOSSARY.md`.
- Create ADRs in `docs/adr/` for structural deviations or library additions.
