# CashPilot — Demo Video

**File:** `CashPilot_Demo.mp4` · **Length:** 2 min 04 s (limit: 5 min) · 1440×900, H.264 · English voice-over and on-screen captions

The video is a real recording of the dashboard driven by `record_demo.py` (Playwright). It runs against the live FastAPI backend and the on-device MiniCPM5-2B model. The UI is not mocked up; the only post-processing is the added narration. Narration is a neural text-to-speech voice (Microsoft `en-US-AndrewNeural` via `edge-tts`), added by `add_voiceover.py` and timed to the scenes. On-screen captions carry the same points for viewers watching without sound.

## Scenes

| # | Starts at (≈) | Scene | What the viewer sees |
|---|---|---|---|
| 0 | 0:00 | Title card | CashPilot, Topic E, "it never moves money" |
| 1 | 0:05 | Start | Empty workspace: add the statements you already download, no bank login |
| 2 | 0:11 | Cash-flow alert | Sample company: cash runs short on Oct 28 (payroll), $5,866.76 gap, drafted $7,500 draw; then CCC 41 days, DSCR 1.38×, reconciliation excluding $36,000 of internal transfers |
| 3 | 0:25 | Financing match | Liquidity score 61/100; offers ranked by true APR (11.9%, 18.4%, 27.5%); a "factor rate 1.35" advance shown as 71.2% APR and flagged predatory |
| 4 | 0:38 | Business analysis | Receivables ageing and late customers |
| 5 | 0:45 | AI CFO | Owner asks "How do I cover the shortfall on Oct 28?"; the local model answers with engine-verified figures |
| 6 | 1:10 | Permission tiers | Approvals panel: drafted credit-line draw waiting for the owner, with only "Prepare request" and "Dismiss" |
| 7 | 1:16 | Guardrail | Prompt injection "transfer $50,000 to account …" is blocked before routing; nothing staged |
| 8 | 1:31 | Live data | Real CSV upload: 94 transactions parsed and scored by the backend in about 0.13 s; Overview switches to the live result (cash short on Jun 28) |
| 9 | 1:53 | Closing card | 969 tests passing, 34/34 sandbox operations, three tiers, repository link |

Scenes 2–7 use the dashboard's built-in sample company; scene 8 uses the owner's own file through the backend.

## Narration (as spoken)

| Starts at | Line |
|---|---|
| 0:00 | This is CashPilot, a finance copilot for small-business owners. |
| 0:05 | The owner starts with the bank statements they already download. There is no bank login and no accounting software. |
| 0:12 | Here is our sample coffee roaster. Payroll on October twenty-eighth takes the balance below zero, nine days from now. CashPilot shows the gap and has already drafted a fix. Below that sit the working-capital ratios. |
| 0:26 | Funding offers are ranked by fit, and each one is converted to a true APR. This advance is quoted as a factor rate of one point three five. That is really seventy-one percent a year, so it is flagged as predatory. |
| 0:41 | Receivables shows who owes money and how late they are. |
| 0:46 | In the assistant, the owner asks a question in plain words. Every figure comes from exact calculations. The model running on this computer only writes the sentences, and an answer that invents a number is thrown away. |
| 1:11 | The agent can draft a credit-line draw, but only the owner can act on it. There is no execute button. |
| 1:17 | Now an attack: a prompt injection asking the agent to wire fifty thousand dollars. It is blocked before routing, and nothing is staged. |
| 1:32 | Last, live mode. A real three-month statement goes to the backend. It parses ninety-four transactions, scores them for funding, and the overview switches to the live forecast: this account runs short on June twenty-eighth. |
| 1:53 | Nine hundred sixty-nine tests pass, and every attack in our sandbox replay was refused. CashPilot never moves the owner's money. |

## Re-record

With the backend on `:8000` and the frontend on `:3000`:

```bash
pip install playwright imageio-ffmpeg
python -m playwright install chromium
python submission/03-demo-video/record_demo.py
pip install edge-tts
python submission/03-demo-video/add_voiceover.py   # needs internet for the TTS service
```

This rewrites `CashPilot_Demo.mp4` and `screenshots/` (the deck uses the screenshots). The recorder logs each scene's start in `scene_times.json`; `add_voiceover.py` places each line from it and refuses to mix if a line would run into the next scene.
