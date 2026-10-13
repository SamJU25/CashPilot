---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes.
---

# Systematic Debugging

## The Iron Law
```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

## The Four Phases
1. **Phase 1: Root Cause Investigation**
   - Read error messages, warnings, and stack traces completely.
   - Reproduce the failure reliably with reproducible steps.
   - Trace data flow backward to where the invalid state originated.
2. **Phase 2: Pattern Analysis**
   - Compare broken behavior against working examples in the codebase.
   - Identify every difference without dismissing minor discrepancies.
3. **Phase 3: Hypothesis & Isolation**
   - Formulate a clear hypothesis explaining the failure mechanism.
   - Verify the hypothesis before modifying code.
4. **Phase 4: Shared Fix & Verification**
   - Fix the root cause at the source.
   - Grep all sibling callers to ensure all paths are covered.
