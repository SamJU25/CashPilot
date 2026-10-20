# Frontend to backend wiring: gap map

Status: audited 2026-10-19 against `api/routes/*.py`. Wired the same day: `lib/api.ts` plus `app/api/session/route.ts` (server-side tenant token). Dropping files switches the workspace to `source: 'live'`; "Use the sample company" switches back. Live results sit in sessionStorage (`cashpilot.live.v1`).

Verified against the running backend: statements upload (`/analyze` then `/underwrite`), invoices (`/analyze/invoices`), Funding, Overview figures, chat request and its 180 s timeout, `/actions` 401 without a token. Token issuance plus an authenticated `/actions` call were checked with curl against a backend started with a test enrollment key.

## Ready to wire (endpoint exists, shape close enough)

| Screen / data | Endpoint | Notes |
|---|---|---|
| Statements upload, Overview figures | `POST /api/v1/analyze` (multipart `files`, `X-Session-ID`) | `CashAnalysisResponse` matches `CashAnalysis`. Binds the statement to the chat session. |
| Receivables | `POST /api/v1/analyze/invoices` | `ReceivablesAgeingResponse`. |
| Funding (score, lenders) | `POST /api/v1/underwrite` | Dossier plus financing options. |
| Assistant | `POST /api/v1/agent/chat`, `GET/DELETE /agent/session/{id}` | `reply`, `metrics`, `matched_options`, `staged_action`. |
| Settings: test connection, models | `POST /agent/test-connection`, `/fetch-models`, `/download-model`, `/delete-model` | |
| Approvals list | `GET /api/v1/actions`, `GET /actions/{id}` | |
| Dismiss | `POST /actions/{id}/reject` | Label it Dismissed in the UI. |
| Health badge | `GET /api/v1/health` | |

## Missing on the backend (frontend shows these today from mock data)

1. **Forecast on upload.** `projected_deficit_date`, shortfall, payroll and bridge amount only come back inside chat `metrics`. Overview needs them from `/analyze` (or a `GET /forecast`).
2. **Series for the runway chart.** `GET /analyze/series`: per-account daily balances plus forecast points.
3. **What-if levers.** `calculate_cash_scenario` exists in `services/calculations` but has no route.
4. **Chat `steps`** (agent, tool, card, tech, duration) for the receipt. Without them the receipt can only show the intent.
5. **`GET /events`** for the activity panel (runs, alerts, decisions).
6. ~~Prepare request~~ Done 2026-10-19: `PREPARED` status, `POST /actions/{id}/prepare` and `/reject`; the execute and passkey routes are removed.
7. **Account display names.** `AccountSummary` has `file_name` and `account_id` but no `display_name` or currency per account.
8. **Change detection.** "What changed since the last upload" (new inflows, bills, shortfall date moved). Duplicates are already flagged; the diff is not returned.
9. **FX.** `GET /fx/rate` with `source` and `is_live_market`.

## Production risks found while auditing

- **Tenant fallback.** `resolve_tenant_identity` accepts a client-asserted `X-Tenant-ID` (or `SME-DEFAULT`) when no token is sent, so any browser can read another tenant's session by naming it. Production should require a signed token on every data route.
- **Token issuance needs an enrollment key** (`X-Enrollment-Key`), which a browser must not hold. A sign-in or session-bootstrap endpoint that issues the tenant token server side is needed before a hosted deploy.
- **CORS** reads `ALLOWED_ORIGINS`; the hosted frontend origin must be set there.

## Found while wiring

- Bucket keys differ: the backend sends `CURRENT`, `1_30`, `31_60`, `61_90`, `OVER_90`; `lib/api.ts` maps them to the screen's keys.
- Local model: the first chat failed to load `models/base/MiniCPM5-2B/model-00000-of-00001.safetensors`, then loaded weights and generated for over 3 minutes on this machine. A chat reply needs to finish well inside the 180 s client timeout.
- The backend's English advisory texts (`summary_advisory`, `recommended_actions`, `conditional_proposal`) show as sent; the six-language UI translates only the sample company's.
- In development, React StrictMode runs the upload effect twice, so `/analyze` is called twice per upload. Production builds call it once.
- Prepare and Dismiss both call the ledger (`/prepare`, `/reject`); a failed call leaves the card pending.
- `/underwrite` takes one file, so with several CSVs only the first is scored.

## Frontend work once the gaps close

- Overview chart, what-if levers and the dated shortfall: wire once items 1 to 3 land (live Overview shows `/analyze` figures only).
- Activity feed: wire `/events` (live mode shows only the owner's decisions).
- Chat receipt: replace the single router step with backend `steps`.
