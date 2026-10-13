---
name: domain-modeling
description: Build and maintain ubiquitous vocabulary, GLOSSARY.md, and Architecture Decision Records (ADRs).
---

# Domain Modeling

Actively construct and maintain the project's domain model. Every domain concept in code should reflect an agreed ubiquitous term.

## 1. Glossary (`GLOSSARY.md`)
- Create and maintain `GLOSSARY.md` at project root.
- Document domain entities, core states, and technical definitions.
- Code variable names, interfaces, and file names must match glossary entries exactly.

## 2. Architecture Decision Records (`docs/adr/`)
- When making substantial architectural choices (frameworks, storage, protocols, state management), document them in `docs/adr/NNNN-<decision-slug>.md`.
- Include: Context, Decision, Consequences (Pros & Cons), and Status (Accepted/Superseded).
