---
name: codebase-design
description: Design domain-centric folder structures, clear module boundaries, and decoupled interfaces.
---

# Codebase Design

## Principles
1. **Domain-Centric Grouping:** Group code by domain responsibility and feature cohesion, not technical layers.
2. **Explicit Interfaces:** Expose clear public contract boundaries and keep internal implementations private to the module.
3. **Decoupled State:** Isolate persistence and external services behind contract interfaces to facilitate testing and refactoring.
