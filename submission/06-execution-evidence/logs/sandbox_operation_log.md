# CashPilot Sandbox Operation Log

- Run at (UTC): 2026-10-20T13:43:04.854+00:00 to 2026-10-20T13:43:56.025+00:00
- Host: Windows 11, Python 3.14.7
- Target: real `api.main:app` in-process (FastAPI TestClient), sandbox stores in a temp dir
- Tenants: `SME-COFFEE-001`, `SME-ACME-002` (sandbox enrollment keys, redacted below)
- Result: **34/34 operations behaved as expected**
- Money moved: **$0.00**. No bank, lender or payment endpoint exists in the system.

| # | Tier | Step | Request | HTTP | Check |
|---|---|---|---|---|---|
| 1 | Public | Health probe and active invariants | `GET /api/v1/health` | 200 | PASS |
| 2 | Tier 1 | Analyze synthetic operating statement (CSV) | `POST /api/v1/analyze` | 200 | PASS |
| 3 | Tier 1 | Analyze statement heading into a cash deficit | `POST /api/v1/analyze` | 200 | PASS |
| 4 | Tier 1 | Analyze multi-currency EUR statement | `POST /api/v1/analyze` | 200 | PASS |
| 5 | Tier 1 | Reject malformed upload with row-level provenance | `POST /api/v1/analyze` | 200 | PASS |
| 6 | Tier 1 | Underwrite statement and match financing options | `POST /api/v1/underwrite` | 200 | PASS |
| 7 | Tier 1 | AI CFO chat: cash runway question with statement | `POST /api/v1/agent/chat` | 200 | PASS |
| 8 | Tier 1 | AI CFO chat: financing question with statement | `POST /api/v1/agent/chat` | 200 | PASS |
| 9 | Enrollment | Token issuance refused without enrollment key | `POST /api/v1/auth/token` | 403 | PASS |
| 10 | Enrollment | Token issuance refused for wrong tenant key | `POST /api/v1/auth/token` | 403 | PASS |
| 11 | Enrollment | Issue signed tenant token for SME-COFFEE-001 | `POST /api/v1/auth/token` | 200 | PASS |
| 12 | Enrollment | Issue signed tenant token for SME-ACME-002 | `POST /api/v1/auth/token` | 200 | PASS |
| 13 | Tier 2 | Anonymous staging refused | `POST /api/v1/actions/stage` | 401 | PASS |
| 14 | Tier 2 | Forged bearer token refused | `POST /api/v1/actions/stage` | 401 | PASS |
| 15 | Tier 2 | Stage $25,000 credit-line draw proposal | `POST /api/v1/actions/stage` | 201 | PASS |
| 16 | Tier 2 | Identical instruction inside dedupe window reuses proposal | `POST /api/v1/actions/stage` | 201 | PASS |
| 17 | Tier 2 | Agent chat stages a factoring proposal (signed tenant) | `POST /api/v1/agent/chat` | 200 | PASS |
| 18 | Tier 2 | Anonymous chat cannot stage | `POST /api/v1/agent/chat` | 200 | PASS |
| 19 | AI guardrail | Prompt injection with valid token and staging params is blocked | `POST /api/v1/agent/chat` | 200 | PASS |
| 20 | AI guardrail | Pasted API key is flagged, not processed | `POST /api/v1/agent/chat` | 200 | PASS |
| 21 | Tier 2 | List tenant's staged proposals | `GET /api/v1/actions` | 200 | PASS |
| 22 | Isolation | Cross-tenant read of proposal returns 404 | `GET /api/v1/actions/intent-11cf0a233720` | 404 | PASS |
| 23 | Isolation | Cross-tenant prepare of proposal returns 404 | `POST /api/v1/actions/intent-11cf0a233720/prepare` | 404 | PASS |
| 24 | Tier 3 | No execute route exists for Tier 3 | `POST /api/v1/actions/intent-11cf0a233720/execute` | 404 | PASS |
| 25 | Tier 3 | Owner prepares request to send themselves | `POST /api/v1/actions/intent-11cf0a233720/prepare` | 200 | PASS |
| 26 | Tier 3 | Prepared proposal cannot be prepared twice | `POST /api/v1/actions/intent-11cf0a233720/prepare` | 409 | PASS |
| 27 | Tier 2 | Stage $5,000 transfer proposal | `POST /api/v1/actions/stage` | 201 | PASS |
| 28 | Tier 3 | Owner dismisses transfer proposal | `POST /api/v1/actions/intent-95df01b8033f/reject` | 200 | PASS |
| 29 | Type boundary | Parameter smuggling rejected by schema | `POST /api/v1/actions/stage` | 422 | PASS |
| 30 | Type boundary | Negative amount rejected by schema | `POST /api/v1/actions/stage` | 422 | PASS |
| 31 | Operator | Decision-table reload refused without operator key | `POST /api/v1/decision/reload` | 503 | PASS |
| 32 | Tier 2 | Compute canonical SHA-256 invoice hash | `SERVICE calculate_canonical_invoice_hash` | - | PASS |
| 33 | Tier 2 | Pledge invoice to lender 1 | `SERVICE invoice_registry.pledge_invoice(lender_id=1)` | - | PASS |
| 34 | Tier 2 | Second pledge of same invoice to lender 2 is blocked | `SERVICE invoice_registry.pledge_invoice(lender_id=2)` | - | PASS |

Full request/response bodies: `sandbox_operation_log.jsonl`. Ledger after the run: `sandbox_final_state.json`.
