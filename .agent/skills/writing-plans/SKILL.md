---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code.
---

# Writing Plans

## Overview
Decompose implementation into bite-sized, checkable tasks adhering to DRY, YAGNI, and TDD.

## Structure
1. **Goal & Architecture:** 1-2 sentence summary of purpose and technical approach.
2. **File Map:** Files created or modified with designated responsibilities.
3. **Task Decomposition:** Each task carries its own test cycle and clear deliverable.
4. **Step Granularity:**
   - Write failing test.
   - Run test to verify failure.
   - Write minimal code to pass.
   - Run tests to verify pass.
   - Commit / checkpoint.
