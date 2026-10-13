---
name: doubt-driven-development
description: Subjects every non-trivial decision to a fresh-context adversarial review before it stands. Use when you want every assumption cross-examined before proceeding, when stress-testing a plan for hidden failure modes, when correctness matters more than speed, when working in unfamiliar code, when stakes are high (production auth, security-sensitive logic, a high-stakes migration, irreversible operations), or any time a confident output would be cheaper to verify now than to debug later.
---

# Doubt-Driven Development

## Overview
A confident answer is not a correct one. Long sessions accumulate context that quietly turns assumptions into "facts" without anyone noticing. Doubt-driven development is the discipline of cross-examining non-trivial decisions with an adversarial mindset — biased to **disprove**, not approve — before any high-stakes code stands.

## When to Use
A decision is **non-trivial** when at least one of these is true:
- It introduces or modifies branching or security logic.
- It crosses a module or service boundary.
- It asserts a property the type system or compiler cannot verify (thread safety, idempotence, ordering, invariants).
- Its correctness depends on hidden assumptions.
- Its blast radius is irreversible (production deploy, data migration, public API change).

**When NOT to use:**
- Mechanical operations (renaming, formatting, file moves).
- Following a clear, unambiguous user instruction.
- One-line changes with obvious correctness.

## The Process
1. **CLAIM:** Explicitly state the architectural claim in 2-3 lines:
   `CLAIM: "The token bucket is thread-safe under concurrent requests."`
   `WHY THIS MATTERS: "A race condition will corrupt balances and breach rate limits."`
2. **EXTRACT:** Isolate the artifact (code diff or schema) and contract, stripped of rationalizations.
3. **DOUBT (Adversarial Review):**
   - Look for unstated assumptions.
   - Look for edge cases not handled.
   - Look for hidden coupling or shared state.
   - Look for failure modes under unexpected input.
4. **RECONCILE:** Classify every finding and fix any discovered flaws.
5. **STOP:** Loop stops when all doubts are reconciled or verified by tests.
