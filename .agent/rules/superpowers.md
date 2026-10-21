---
trigger: always_on
description: "Auto-apply Superpowers engineering methodology: spec alignment before code, root-cause debugging, and fresh verification before completion."
---

# Superpowers Engineering Methodology

Scope: Antigravity and Claude coding assistants.

## 1. Intent & Spec Gate
- Before writing code for new features or modifying behavior, confirm intent with the user.
- State assumptions and proposed approach clearly; avoid premature implementation.
- Classify task type: Spike (throwaway feasibility check), Bounded (scoped change to existing flow), Architectural (new subsystem or interface change).

## 2. Root Cause Debugging Invariant
- Never propose a fix before completing root cause investigation.
- Read complete error messages and trace data flow to the origin.
- Grep all sibling callers and fix the shared logic once.

## 3. Verification Invariant
- Run the full verification command (`npm run typecheck`, test suite, or build) before claiming completion.
- State status with concrete terminal output evidence. Never use "should work" or "assumed fixed".
