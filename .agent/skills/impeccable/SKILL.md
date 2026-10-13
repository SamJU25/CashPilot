---
name: impeccable
description: Design engineering engine for craft, critique, audit, polish, typeset, animate, and layout refinement.
version: 4.5.0
---

# Impeccable Design Engine

Opinionated design guidance, critique, and micro-tuning commands for frontend interfaces.

## Core Commands & Principles

### 1. `polish`
Final pass before shipping: align spacing tokens, verify contrast ratios, tighten borders, ensure visual consistency.

### 2. `typeset`
Fix typography hierarchy: deliberate scale ratios, font-variant tabular numbers for metrics/sensors, and appropriate line heights (`leading-relaxed` for copy, `leading-tight` for display headings).

### 3. `animate`
Purposeful motion:
- Use spring physics (`cubic-bezier(0.16, 1, 0.3, 1)` or CSS variables `var(--spring)`).
- Keep durations short (150ms-250ms for micro-interactions).
- Avoid bouncy or cartoonish easing.
- Always respect `@media (prefers-reduced-motion: reduce)`.

### 4. `critique` & `audit`
Evaluate information architecture, cognitive load, visual balance, and technical quality.

### 5. `bolder` / `quieter`
Calibrate visual volume: amplify muted surfaces or tone down overly saturated elements to balance visual hierarchy.
