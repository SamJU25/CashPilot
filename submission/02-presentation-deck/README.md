# CashPilot — Presentation Deck

| File | Use |
|---|---|
| `CashPilot_Presentation.pptx` | Editable deck, 12 slides, 16:9, speaker notes on every slide |
| `CashPilot_Presentation.pdf` | Same deck for upload or for viewers without PowerPoint |
| `build_deck.js` | Generator (`npm install pptxgenjs@3.12.0`, then `node submission/02-presentation-deck/build_deck.js` from the repo root). Uses screenshots from `../03-demo-video/screenshots/` |

**Length:** the speaker notes total about 6 minutes at a normal pace, leaving room for a live demo or pauses inside the 10-minute limit.

**Structure, mapped to the scoring weights:** slides 2–5 task completion (40%), slides 6–7 innovation (30%), slides 8–9 security and compliance (30%), slides 10–11 evidence and roadmap, slide 12 close.

## Speaker script

### Slide 1 — CashPilot (cover)

Hi, we are the CashPilot team: Sampad, Purno, Binoy and Parban. CashPilot is our answer to Topic E: a finance copilot for small-business owners. In one sentence: it reads the bank statements the owner already has, warns them before cash runs out, matches them to the cheapest honest financing, and drafts the request. It is a real financial participant, but by design it can never move money. (30 s)

### Slide 2 — Small businesses run out of cash before they run out of profit

The problem is timing, not profit. A business buys stock on day 0, pays the supplier on day 30, sells on day 45 on 60-day terms and collects on day 105. That is a 75-day gap. Owners discover it when payroll bounces. Banks take weeks; fast lenders hide the cost behind factor rates. And a generic chatbot that guesses numbers cannot be trusted near money. (60 s)

### Slide 3 — CashPilot covers all three Topic E capabilities

Topic E asks for three things, and CashPilot does each from one uploaded statement. One: cash-flow management with alerts, down to the day cash goes negative. Two: financing matching, scored from transaction behaviour the way WeBank-style digital lenders do it, ranked by true APR with predatory offers flagged. Three: business analysis with 25 deterministic engines. (60 s)

### Slide 4 — The owner sees the shortfall date, the gap, and a drafted fix

Here is the product with the built-in sample company. The first thing the owner sees is a date: cash runs short on October 28, when payroll lands. It shows the size of the gap and links straight to a drafted fix: a $7,500 credit-line draw covering the shortfall plus a safety margin. (45 s)

### Slide 5 — Financing ranked by true cost, predatory offers flagged

Funding. The liquidity score comes from transaction behaviour: average daily balance, income steadiness and bounced payments. No audited accounts or property collateral needed. Every offer is converted to a true APR and to a dollar cost for this exact need. The advance quoted as a 1.35 factor rate is really 71.2% APR, so it is flagged predatory and kept out of the defaults. (45 s)

### Slide 6 — The AI explains and drafts; deterministic code does the maths

The core design choice: separate language from arithmetic. Guardrails run first, an embedding router picks the intent, subagents call deterministic Decimal engines, and only then does the model write sentences. If its answer quotes any figure the engine didn't produce, we throw the answer away. It runs on a 2-billion-parameter model on the owner's own computer, so statements never have to leave the machine. (60 s)

### Slide 7 — Six layers, with untrusted reasoning kept away from money

Architecture in six layers. The browser is treated as an untrusted display. The gateway validates every request strictly. The agent layer reasons but holds no credentials. The deterministic engine does all money maths. Storage is owner-only and can be encrypted. The invoice registry blocks double financing. Today it runs as a local simulation, and the Solidity contract is ready for FISCO BCOS. (45 s)

### Slide 8 — Three tiers: the agent drafts, only the owner acts

Security is 30% of the score, and our answer is structural. Tier 1 is read-only and autonomous. Tier 2 lets the agent draft a proposal, but only for a caller with a signed tenant token. Tier 3, anything that moves money, has no execution route at all. The owner gets a pre-filled request and sends it themselves. With no payment credentials in the system, there is nothing for an attacker to steal or trigger. (60 s)

### Slide 9 — We attacked our own agent: every attempt was refused

We did not just design this; we attacked it. Our sandbox replay runs 34 operations against the real API, including forged tokens, cross-tenant access, calling an execute route, smuggling an execute-now field, and a prompt injection asking to wire $50,000 sent with a valid token. Every one was refused, and the logs are in our execution evidence. Our self-assessment also lists 14 known risks openly, such as single-process storage and regex-only name masking. (60 s)

### Slide 10 — Verified, not claimed

Everything here is reproducible. 963 tests pass. The demo video drives the real UI against the live backend and the local model. When we upload a 94-transaction statement, the backend parses, scores and forecasts it in about a tenth of a second. Every claim in our documents points to a test, a log line or a file. (45 s)

### Slide 11 — What is built today, and what comes next

We are explicit about the line between built and planned. Everything on the left runs and is tested today. On the right: deploying the invoice registry on a FISCO BCOS consortium chain so lenders share one source of truth, moving storage to PostgreSQL with row-level security, read-only open-banking feeds, push alerts, and stronger masking and sign-in. (45 s)

### Slide 12 — Closing

To close: CashPilot shows what AI as a financial participant can look like when it is safe. It completes the real tasks of Topic E, it is secure by construction because the agent can never move money, and it is new in how it keeps every number grounded and every policy reviewable. Thank you, we are happy to take questions. (30 s)
