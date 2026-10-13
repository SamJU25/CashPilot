---
name: antislop
description: Anti-slop multi-surface filter for AI coding agents. Rejects technique without purpose across UI, copy, and code comments.
---

# Antislop Core Filter

A negative filter, not a style guide. Rejects generic AI slop while preserving intentional design.

## Core Directives

### 1. The Purpose Gate
Before introducing any visual technique, decorative badge, or card container, answer: **What does this serve?**
- If the only reason is "it looks AI" or "it fills space", remove or rework it.
- If it supports a verified hierarchy, identity, or readability goal, keep it.

### 2. Evidence Over Claims
- Never invent placeholder stats (e.g. "99.999% uptime", "0.0001ms latency") or fictional founder testimonials.
- Only show verified facts and real system telemetry.

### 3. Craftsmanship Floor
- Every interactive element must be functional.
- Content-driven composition: omit sections that only exist to fill a landing page template.
- State resilience: UI must hold in loading, empty, and error states.
