---
name: motion-craft
description: Motion rules for the SME Finance Copilot frontend using the `motion` package (Framer Motion successor). Use when adding any animation, transition, number ticker, chart entrance, or layout change to a component.
---

# Motion Craft

Motion in a finance tool exists to explain change: a number moved, a panel opened, a row was added. If an animation explains nothing, delete it.

## 1. Import Path

```tsx
'use client';
import { motion, AnimatePresence, MotionConfig, useReducedMotion } from 'motion/react';
```

Never import from `framer-motion`. Motion components are client-only; keep Server Components static and wrap only the animated leaf.

## 2. Spring Presets (single source)

Define once in `lib/motion.ts` and import everywhere. No inline magic numbers in components.

```ts
export const spring = {
  snappy: { type: 'spring', stiffness: 500, damping: 40, mass: 0.8 }, // buttons, toggles, tabs indicator
  smooth: { type: 'spring', stiffness: 300, damping: 34 },            // panels, sheets, cards
  gentle: { type: 'spring', stiffness: 180, damping: 28 },            // number tickers, chart reveals
} as const;

export const fade = { duration: 0.16, ease: [0.16, 1, 0.3, 1] } as const;
```

Settle time must stay under 300ms (CLAUDE.md §2.6). Check with `visualDuration` if a preset is tuned.

## 3. What Animates

| Change | Treatment |
|---|---|
| Panel / sheet / dialog open | `smooth`, translate 8–16px + opacity. Never scale a full panel. |
| Tab or segment switch | Shared `layoutId` underline/pill, `snappy`. Content crossfades with `fade`, no slide. |
| KPI value update | Tick the number (`gentle`), flash the delta color for 600ms, then rest. |
| List row added/removed | `AnimatePresence` + `layout`, height via `layout`, not `height: auto` tweening. |
| First page load | One stagger pass on KPI row only: 30ms per item, max 6 items. Charts draw once. |
| Hover | Color/shadow via CSS `transition`, not motion. Lift max 1px. |
| Loading → populated | Skeleton crossfades out with `fade`. Do not animate the skeleton shimmer faster than 1.5s. |

## 4. Banned (AI-slop tells)

- Bouncy overshoot on data (springs with damping < 20 on numbers or charts).
- Fade-up-on-scroll for every section. Dashboards are not landing pages.
- Infinite pulses, glowing gradients, floating blobs, parallax.
- Rotating/scaling icons on hover.
- Staggering table rows or more than one stagger group per view.
- Animating `width`, `height`, `top`, `left`, `box-shadow` per frame. Use `transform`/`opacity`/`layout`.
- Re-running entrance animations on refetch. Use `initial={false}` on components that re-mount with data.

## 5. Numbers and Money

- Tickers animate the **display string only**. The source value stays a string/Decimal from the API; never round-trip money through animated floats into state that is sent back.
- Format every frame with the same `Intl.NumberFormat` instance and `tabular-nums` so width does not jitter.
- Negative deltas use color + sign + icon, never color alone.

## 6. Charts (Recharts)

- Recharts animates by itself: set `isAnimationActive` on first render only, `animationDuration={400}`, `animationEasing="ease-out"`.
- Disable chart animation on live updates and when reduced motion is on.
- Tooltips: no motion, they must track the cursor instantly.

## 7. Reduced Motion

Wrap the app once:

```tsx
<MotionConfig reducedMotion="user" transition={spring.smooth}>{children}</MotionConfig>
```

With reduced motion: transforms are dropped, opacity fades remain, tickers jump to the final value, charts render static.

## 8. Pre-ship Check

1. Every animation answers "what changed?"
2. Tab through the UI: focus never waits on an animation.
3. DevTools → Rendering → "Emulate prefers-reduced-motion: reduce" → UI still clear.
4. Performance panel: no layout/paint thrash during transitions.
