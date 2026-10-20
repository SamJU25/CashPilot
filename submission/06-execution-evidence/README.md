# Execution Evidence — Simulated-Account / Sandbox Operation Logs

CashPilot is a Topic E (non-on-chain) entry, so its execution evidence is **sandbox operation logs plus the demo video**. No real bank, lender or payment system is involved. The system has no execution route and no payment credentials, so a sandbox run exercises exactly the code a production run would.

## What is here

| File | Content |
|---|---|
| `logs/sandbox_operation_log.md` | Readable table of all 34 operations with tier, request, HTTP status and verdict |
| `logs/sandbox_operation_log.jsonl` | One JSON record per operation: UTC timestamp, request (auth redacted), status, full response body, verdict |
| `logs/sandbox_final_state.json` | Staging ledger and invoice registry after the run |
| `logs/pytest_full_run.log` | Full test suite: **969 passed, 1 skipped** |
| `logs/runner_console.log` | Runner summary line |
| `run_sandbox_evidence.py` | The runner. It replays the journey against the real `api.main:app` |
| `../03-demo-video/CashPilot_Demo.mp4` | Demo video of the same flows in the dashboard |

## Latest run

- **When:** 2026-10-20 13:43:04 → 13:43:56 UTC
- **Host:** Windows 11, Python 3.14.7, local MiniCPM5-2B model on GPU
- **Simulated accounts:** two sandbox tenants, `SME-COFFEE-001` (coffee roastery) and `SME-ACME-002` (attacker / second tenant), each with its own enrollment key
- **Input data:** sample statements from `data/samples/` (USD operating account, a declining 3-month account, a EUR account) and one deliberately malformed CSV
- **Result:** **34/34 operations behaved as expected. $0.00 moved.**

Final ledger state:

| Intent | Action | Final status | How it got there |
|---|---|---|---|
| `intent-11cf0a233720` | `DRAW_CREDIT_LINE` $25,000 | `PREPARED` | Staged via REST → owner prepared the request to send it themselves |
| `intent-b52a16a0e82a` | `FACTOR_INVOICE` $12,000 | `STAGED_PENDING_HITL` | Staged by the AI agent through chat; waiting for the owner |
| `intent-95df01b8033f` | `TRANSFER` $5,000 | `REJECTED` | Staged → owner dismissed it |

Invoice registry: one invoice pledged to lender 1; the second pledge to lender 2 was refused with `ERR_INVOICE_ALREADY_PLEDGED`.

## Operation sequence

| # | Group | Operations |
|---|---|---|
| 1 | Health | Service health and active invariants |
| 2–6 | Tier 1 analysis | Analyze USD, deficit and EUR statements; malformed row rejected with `INVALID_DATE`; underwriting with matched offers |
| 7–8 | AI agent | Chat routes to `CASH_DIAGNOSTIC` and `CREDIT_UNDERWRITING` with verified figures |
| 9–14 | Identity | Token refused without key / with another tenant's key; tokens issued; anonymous and forged-token staging refused |
| 15–18 | Tier 2 drafting | Proposal staged; duplicate deduped; agent stages via chat; anonymous chat cannot stage |
| 19–20 | AI guardrails | Prompt injection with valid token and `TRANSFER` params blocked; pasted API key flagged |
| 21–28 | Isolation and Tier 3 | Cross-tenant read/prepare → 404; `/execute` → 404; owner prepares; second decision → 409; transfer staged then dismissed |
| 29–31 | Boundaries | Smuggled `execute_now` → 422; negative amount → 422; operator reload refused without key → 503 |
| 32–34 | Double financing | Canonical SHA-256 hash; first pledge accepted; second pledge refused |

## Reproduce

From the repository root, with `requirements.txt` installed:

```bash
python submission/06-execution-evidence/run_sandbox_evidence.py
```

The runner uses a fresh temporary directory for all state, sandbox-only keys, and never reads `.env`. It exits non-zero if any operation does not behave as expected. The local model is optional; without it, chat replies fall back to the deterministic summary with the same figures.

## Notes for reviewers

- Tokens, enrollment keys and the sandbox signing secret are redacted in the logs. The API key in operation 20 is a deliberately fake string used to trigger the detector.
- Invoice `tx_hash` and `block_number` values come from the local registry simulation, not a live chain. Topic E does not require on-chain transactions; deployment to FISCO BCOS is on the roadmap (see the security self-assessment, R5).
