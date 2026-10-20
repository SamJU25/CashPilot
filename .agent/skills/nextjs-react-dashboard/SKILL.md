---
name: nextjs-react-dashboard
description: "Best practices for building the CashPilot executive dashboard in Next.js 14/15 and React. Use when building App Router pages, Server Components, reactive cash flow charts (Recharts), financial metric cards, and streaming real-time alerts."
---

# Next.js & React Dashboard Craft

High-density, accessible, modern fintech dashboard development adhering to the 4-pillar design protocol.

## 1. App Router Architecture

```
src/app/
├── layout.tsx                # Root layout with providers & theme
├── (dashboard)/
│   ├── layout.tsx            # App sidebar, executive navigation, tier-status pill
│   ├── page.tsx              # Executive Overview: Runway gauge, Cash balance, Alerts
│   ├── cashflow/page.tsx     # 30-day forecast, burn rate waterfall, DSO trend
│   ├── invoices/page.tsx     # B2B Invoice ledger, factoring pre-qualifier, FISCO status
│   └── financing/page.tsx    # Credit options comparison (revolving vs factoring)
└── components/
    ├── charts/               # Recharts components ("use client")
    ├── ui/                   # High-contrast buttons, badges, data tables
    └── copilot/              # Streaming chat sidebar with action proposals
```

## 2. Visual & Interaction Invariants

- **Purpose Gate (Antislop)**: Avoid gratuitous neon glow, excessive cards-in-cards, and floating gradients. Use high-contrast tabular figures (`font-mono tracking-tight`).
- **Client vs Server Boundary**: Data fetching happens in Server Components (`page.tsx`). Interactive charts (`Recharts`, `Chart.js`) and chat forms are isolated into explicit `"use client"` leaf components.
- **Financial Status Colors**:
  - Danger (Runway < 15 days, Negative OCF): Amber-red `#E11D48`
  - Warning (DSO > 45 days, Staged action): Amber-yellow `#F59E0B`
  - Healthy (Runway > 60 days, Positive cash): Emerald-green `#10B981`
- **Action Approval Modals**: Always render Tier 3 executions inside an explicit, high-friction confirmation modal displaying exact dollar amounts, counterparty, and 2FA input.
