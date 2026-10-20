# Frontend Design: SME Finance Copilot

Status: approved in conversation 2026-10-19. Built against mock fixtures that mirror the backend response shapes; wiring to the API comes later without changing components.

## Intent

A small-business owner downloads a bank statement, drops it in, and within a minute knows (1) when cash runs out, (2) why, and (3) what the copilot has already prepared to fix it. The copilot is a financial participant, not a chatbot: it runs the whole analysis on every upload and stops at the step that would involve a lender: it prepares the request and the owner sends it.

Contest rubric this design serves (FinTechathon 2026 Topic E): task completion 40%, security and governance 30%, innovation 30%.

## Goals

- Answer "am I OK?" in two seconds: a dated sentence, not a dashboard of numbers.
- Every number explains itself: formula, inputs, source rows.
- Show the agent's work as a receipt, never as a show.
- Honest lending: true APR, predatory offers flagged and never hidden.
- Visible privacy: where data lives, which model runs, what the model sees.

## Non-goals (this pass)

- Real API calls and auth flow.
- Chinese/English toggle (planned next; IBM Plex has a CJK sibling for this reason).
- Command palette, mobile PWA install.

## Anti-goals

- Agent node graphs, glowing gradients, fake typing, bouncing numbers.
- Internal names in UI (`LiquiditySubagent`, `tool_calculate_dscr`).
- Any rate or status that pretends to be live when it is a fallback.

## Visual system (my calls)

- Color: page `#F3F5F4`, surface `#FFFFFF`, ink `#0F1A17`, secondary ink `#4B5753`, hairline `#E1E5E3`, brand ledger green `#0F5241` (existing `brand-600`). Dark mode: page `#0C1110`, surface `#131A18`, ink `#E6ECE9`.
- Status (dataviz reference, fixed): good `#0CA30C`, warning `#FAB219`, serious `#EC835A`, critical `#D03B3B`, always with icon + label.
- Account series: dataviz categorical slots in fixed order (blue `#2A78D6`, orange `#EB6834`, aqua `#1BAF7A`, yellow `#EDA100`); Total line in primary ink; forecast dashed.
- Type: IBM Plex Sans for everything including figures (tabular in tables and axes), IBM Plex Mono only inside formula receipts.
- Layout: narrow left rail, quiet top bar with environment and AI badges. Sections separated by space and hairlines, not cards inside cards. One elevated surface: the runway chart.
- Motion: per `.agent/skills/motion-craft/SKILL.md`. One orchestrated moment on Overview (chart draws once); everything else answers user actions.
- The memorable element: the hero sentence ("Cash runs short on Oct 28") sitting directly over the forecast line that shows the payroll drop causing it.

## Screens

| Route | Job |
|---|---|
| `/` Overview | Hero sentence, runway chart (Total / By account), what-if levers, key figures, pending approval, latest run |
| `/statements` | Upload or use sample company, accounts detected (rename, months connected, gaps), rejected rows, own-account transfers excluded |
| `/receivables` | Ageing buckets, customers who owe you, draft payment reminder |
| `/funding` | Liquidity score, lender comparison with true APR and predatory flag |
| `/activity` | Agent runs as receipts, newest first |
| `/approvals` | Staged actions, prepare request or dismiss, audit trail |
| `/assistant` | Chat with a receipt under every answer |
| `/settings` | AI provider, privacy (what the AI sees, delete data), preferences |

Every data view ships loading, empty, error and populated states.

## Backend handoff (for the backend team)

1. `GET /analyze/series`: per-account daily balances and forecast points (`[{account_id, display_name, currency, points:[{date, balance}]}]`, money as strings).
2. `steps` on `/agent/chat` responses (`label, detail, inputs, output, duration_ms`), later streamed. Each step also carries (see `RunStep` in `lib/types.ts`):
   - `agent`: `supervisor` | `liquidity` | `credit` | `risk` (maps to the supervisor, `LiquiditySubagent`, `CreditSubagent`, `RiskManagerSubagent`);
   - `tool`: the function actually called, by its real name (e.g. `tool_calculate_predictive_cash`, `FastEmbedSemanticRouter`);
   - `card`: `{ file, title, slug }` for a knowledge card used, i.e. the `## section` of `knowledge/cards/<file>`;
   - `tech`: optional free text for the technical view (intent and cosine similarity, policy file used).
   The first step of every reply should be the router's decision (`intent/sub_intent` and similarity). New tool names need a friendly label added under `tool.<name>` in `lib/i18n/*`; unknown names fall back to the raw identifier.
3. `GET /events`: one feed for the header activity panel, newest first. Event kinds: `run` (trigger, outcome, tier), `alert` (`critical` | `warning` | `info`, title, body, link target; e.g. shortfall projected, invoice now N days late, statement month missing), and `decision` (action approved or rejected, with timestamp and approver). Pending approvals come from `/actions`.
4. Mixed-currency uploads converted to a home currency, returning rate, source and timestamp.
5. `GET /fx/rate?from=&to=` exposing `source` and `is_live_market`.
6. Account display names (guessed from filename) instead of `Account_N`; `quoted_as` on financing options (e.g. factor rate) so true APR can be shown beside the lender's own wording.
7. Model reasoning is not shown in the UI (decided 2026-10-19): not every provider exposes it, and figures must come from the calculation receipt. The chat shows a "Thinking" indicator for every model while the reply is pending, so the backend can keep stripping `<think>`/`<thought>` blocks in `sanitize_cfo_reply`. Streaming the reply (or a pending/done status) would let the indicator end exactly when text starts.
8. Raise chat `max_new_tokens` (300 in `services/agent/supervisor.py` local branch) to roughly 1,024 to 2,048: with thinking enabled the reasoning spends the budget first, and an unclosed `<think>` block is discarded, leaving an empty or canned reply. Context itself is not a constraint: MiniCPM5-2B supports 131,072 tokens and each chat turn sends about 1.5k to 3k (last 6 messages plus rolling summary).
9. Passkey approval removed from the frontend (decided 2026-10-19). CashPilot runs on uploaded statements with no bank or lender connection, so no action moves money and a passkey adds friction without protecting anything. A drafted action now ends in **Prepare request** (a pre-filled request the owner copies or downloads and sends themselves) or **Dismiss**. Done the same day across the backend: `PREPARED` status, `POST /actions/{id}/prepare` and `/reject`, with the execute route, WebAuthn library, passkey registry and passkey wording in prompts, cards and training data all removed.

## Left to the builder

Component structure, mock data values, copy details within the voice above (plain verbs, sentence case, no filler, no arrows on buttons).
