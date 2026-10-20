# Thinking on or off for Solvavion-2B

Decided 2026-10-19: **off by default** (`LOCAL_ENABLE_THINKING=0`), from a measured comparison rather than a guess.

## How it was measured

- `python scripts/eval_model.py --engine production --thinking on|off` on all 100 cases of `dataset/eval_set.jsonl`.
- Production path: `LocalTransformersEngine`, MiniCPM5-2B in 4-bit plus the Solvavion-2B LoRA adapter, RTX 4050 Laptop GPU (6 GB), `max_new_tokens=400`, replies cleaned by `sanitize_cfo_reply` as the supervisor does.
- Sampling runs at temperature 0.1. The per-case seed used Python's `hash()`, which is salted per process, so the two runs did not share seeds; per-case flips therefore include some sampling noise. (Fixed afterwards: seeds now use `zlib.crc32`.)
- Decision rule fixed before the run: keep thinking only if it raises the pass rate by 5 points or more, or cuts invented figures, without adding empty replies; per-suite use if one suite gains 10 points or more.

## Results

| | Thinking on | Thinking off |
|---|---:|---:|
| Pass rate, all 100 | 40.0% | 39.0% |
| Pass rate, without the stale tier-3 suite | 44.4% | 43.3% |
| Mean reply time | 28.4 s | 15.5 s |
| p90 reply time | 33.4 s | 20.5 s |
| Tokens generated per reply | 150 | 64 |
| Replies with invented figures | 14 | 10 |
| Replies missing required figures | 31 | 30 |
| Empty or cut-off replies | 0 | 0 |

| Suite | On | Off |
|---|---:|---:|
| cash_runway | 60.0% | 55.0% |
| working_capital_financing | 35.0% | 40.0% |
| concept_explanations | 25.0% | 35.0% |
| multi_turn_followup | 13.3% | 6.7% |
| off_topic_safety | 93.3% | 80.0% |
| tier3_governance | 0.0% | 0.0% |

10 cases passed only with thinking and 9 only without, which is noise-level, and partly sampling noise given the seed issue above.

## Why off

- No overall gain (+1.1 points against a +5 bar) and more invented figures with thinking on.
- The one suite that gained, off-topic refusals (2 of 15 cases), never reaches the model in the app: the supervisor answers off-topic questions with a fixed refusal first (`is_off_topic_query`).
- Replies take about half the time.

## Found along the way

- With thinking on, the chat template opens `<think>` in the prompt, so the reply carried the reasoning plan up to an orphan `</think>` and the sanitizer kept it. Fixed in `sanitize_cfo_reply` (`ORPHAN_THOUGHT_CLOSE_PATTERN`), with a test.
- The absolute pass rate (about 40%) is the bigger issue than thinking. Most failures are missing required figures (30) and missing domain terms (20 to 25), so the next gain is in training data or prompts, not this switch. Some gates are strict wording checks (for example "0 NSF" against "no NSF events"), and `tier3_governance` still expects the removed passkey notice, so the set needs a refresh too.
