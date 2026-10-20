# CashPilot — FinTechathon 2026 Submission Package

**Track:** International · **Theme:** AI as a Financial Participant · **Topic:** E — SME Finance Copilot  
**Repository:** https://github.com/SamJU25/F-SME-Finance-Copilot  
**Package date:** 2026-10-20 (deadline 23:59 Beijing time / 15:59 UTC)

## Team

| Member | GitHub |
|---|---|
| Sampad Chakma | [@SamJU25](https://github.com/SamJU25) |
| Purno Dewan | [@coderx86](https://github.com/coderx86) |
| Binoy Kumar Chakma | [@binoy-kumar-changmha](https://github.com/binoy-kumar-changmha) |
| Parban Chakma | [@Parban1527](https://github.com/Parban1527) |

This folder holds every item on the competition's submission checklist. Product source code lives in the repository root and is not duplicated here.

## Submission checklist

| # | Required item | Rule text | Deliverable | Status |
|---|---|---|---|---|
| 01 | **Technical documentation** | System architecture, core algorithm description, security design | [`01-technical-documentation/TECHNICAL_DOCUMENTATION.pdf`](01-technical-documentation/TECHNICAL_DOCUMENTATION.pdf) (+ `.md` source) | Ready |
| 02 | **Presentation deck** | Final presentation no longer than 10 minutes | [`02-presentation-deck/CashPilot_Presentation.pptx`](02-presentation-deck/CashPilot_Presentation.pptx) and `.pdf`; 12 slides, speaker script in [`README`](02-presentation-deck/README.md) (~6 min of narration) | Ready |
| 03 | **Demo video** (optional) | No longer than 5 minutes | [`03-demo-video/CashPilot_Demo.mp4`](03-demo-video/CashPilot_Demo.mp4), 2:04, narrated, real UI against the live backend | Ready |
| 04 | **Source code** | README, GitHub repository link, deployment instructions, test cases | Repository root [`README.md`](../README.md); reviewer guide [`04-source-code/SOURCE_CODE.md`](04-source-code/SOURCE_CODE.md) | Ready; the repository must be pushed so reviewers see this folder |
| 05 | **Security self-assessment report** | Permission-tier implementation and known-risk list | [`05-security-self-assessment/SECURITY_SELF_ASSESSMENT.pdf`](05-security-self-assessment/SECURITY_SELF_ASSESSMENT.pdf) (+ `.md`, `evidence/`) | Ready |
| 06 | **Execution evidence** | Non-on-chain topics: simulated-account / sandbox operation logs and demo video | [`06-execution-evidence/`](06-execution-evidence/README.md): 34-operation sandbox log (`.md` + `.jsonl`), final ledger state, full test log; video in `03-demo-video/` | Ready |

## Verified numbers used across the package

| Figure | Source |
|---|---|
| 970 tests passed, 1 skipped | `06-execution-evidence/logs/pytest_full_run.log` (2026-10-20) |
| 54 security tests passed, 1 skipped | `05-security-self-assessment/evidence/pytest_security_suite.log` |
| 34/34 sandbox operations as expected, $0.00 moved | `06-execution-evidence/logs/sandbox_operation_log.md` |
| 0 known Python dependency vulnerabilities | `05-security-self-assessment/evidence/pip_audit_requirements.txt` |
| 13 frontend advisories, critical one disabled in config | `05-security-self-assessment/evidence/npm_audit_production.txt`, risk R9 |

## Folder layout

```
submission/
├── README.md                       this index & checklist
├── 01-technical-documentation/     architecture, algorithms, security design (.pdf & .md)
├── 02-presentation-deck/           presentation slides (.pptx & .pdf) + speaker script
├── 03-demo-video/                  narrated demo video (.mp4) + scene script
├── 04-source-code/                 repository guide, deployment, test-case map (.md)
├── 05-security-self-assessment/    tier implementation, 14-item risk register, audit evidence
└── 06-execution-evidence/          sandbox operation logs, final state, full test logs
```
