// Builds CashPilot_Presentation.pptx from the demo screenshots and verified project figures.
// Run from the repository root: node submission/02-presentation-deck/build_deck.js
// Needs pptxgenjs (npm install pptxgenjs@3.12.0 anywhere on NODE_PATH) and the screenshots
// produced by submission/03-demo-video/record_demo.py.
const path = require("path");
const pptxgen = require("pptxgenjs");

const HERE = __dirname;
const SHOTS = path.join(HERE, "..", "03-demo-video", "screenshots");
const shot = (name) => path.join(SHOTS, name);

const BG = "0B1220", PANEL = "131C2E", PANEL2 = "1A2540", LINE = "2A3654";
const MINT = "6EE7B7", RED = "F87171", AMBER = "FBBF24", WHITE = "FFFFFF", MUTED = "94A3B8", SOFT = "CBD5E1";
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.title = "CashPilot - SME Finance Copilot";
pres.author = "CashPilot team";
pres.company = "FinTechathon 2026 International Track";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: BG },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 12.1, h: 0.8, fontFace: FONT, fontSize: 32, bold: true, color: WHITE, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: "CashPilot · FinTechathon 2026 · Topic E: SME Finance Copilot", options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontFace: FONT, fontSize: 10, color: MUTED, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color: MUTED, align: "right" },
});
pres.defineSlideMaster({ title: "COVER", background: { color: BG } });

const T = (slide, text, opts) => slide.addText(text, { isTextBox: true, fontFace: FONT, color: WHITE, margin: 0, ...opts });
const card = (slide, x, y, w, h, fill = PANEL) =>
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: LINE, width: 0.75 }, rectRadius: 0.12 });
const dot = (slide, x, y, label, color = MINT) => {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color } });
  T(slide, label, { x, y, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: BG, align: "center", valign: "middle" });
};
const img = (slide, file, x, y, w) => {
  const h = w / 1.6; // screenshots are 1440x900
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.05, y: y - 0.05, w: w + 0.1, h: h + 0.1, fill: { color: LINE }, line: { color: LINE }, rectRadius: 0.08 });
  slide.addImage({ path: shot(file), x, y, w, h });
  return h;
};
const content = (title, section) => {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  return s;
};

// 1 · Cover ------------------------------------------------------------------
pres.addSection({ title: "Opening" });
let s = pres.addSlide({ masterName: "COVER", sectionTitle: "Opening" });
s.addShape(pres.shapes.OVAL, { x: 0.8, y: 1.15, w: 0.9, h: 0.9, fill: { color: MINT } });
T(s, "➤", { x: 0.8, y: 1.15, w: 0.9, h: 0.9, fontSize: 30, color: BG, align: "center", valign: "middle", bold: true });
T(s, "CashPilot", { x: 0.8, y: 2.3, w: 11, h: 1.2, fontSize: 66, bold: true });
T(s, "An AI finance copilot for small-business owners", { x: 0.8, y: 3.5, w: 11, h: 0.6, fontSize: 28, color: MINT });
T(s, "It reads your bank statements, warns you before cash runs out, finds the cheapest honest financing, and drafts the paperwork. It never moves your money.",
  { x: 0.8, y: 4.3, w: 10.5, h: 1.0, fontSize: 18, color: SOFT });
T(s, "Team", { x: 0.8, y: 5.45, w: 2, h: 0.35, fontSize: 13, bold: true, color: MINT, charSpacing: 2 });
T(s, "Sampad Chakma  ·  Purno Dewan  ·  Binoy Kumar Chakma  ·  Parban Chakma", { x: 0.8, y: 5.8, w: 11.5, h: 0.45, fontSize: 18, color: WHITE });
T(s, "FinTechathon 2026 International Track  ·  Theme: AI as a Financial Participant  ·  Topic E: SME Finance Copilot",
  { x: 0.8, y: 6.4, w: 12, h: 0.4, fontSize: 13, color: MUTED });
s.addNotes("Hi, we are the CashPilot team: Sampad, Purno, Binoy and Parban. CashPilot is our answer to Topic E: a finance copilot for small-business owners. In one sentence: it reads the bank statements the owner already has, warns them before cash runs out, matches them to the cheapest honest financing, and drafts the request. It is a real financial participant, but by design it can never move money. (30 s)");

// 2 · Problem -----------------------------------------------------------------
pres.addSection({ title: "Problem" });
s = content("Small businesses run out of cash before they run out of profit", "Problem");
const steps = [["Day 0", "Buy stock", SOFT], ["Day 30", "Pay supplier\n−$30,000", RED], ["Day 45", "Sell, invoice\nNet 60 terms", SOFT], ["Day 105", "Customer pays\n+$100,000", MINT]];
s.addShape(pres.shapes.LINE, { x: 1.0, y: 2.55, w: 9.6, h: 0, line: { color: LINE, width: 3 } });
steps.forEach(([d, label, c], i) => {
  const x = 0.8 + i * 3.2;
  s.addShape(pres.shapes.OVAL, { x: x + 0.05, y: 2.4, w: 0.3, h: 0.3, fill: { color: c } });
  T(s, d, { x, y: 1.75, w: 3, h: 0.5, fontSize: 22, bold: true, color: c });
  T(s, label, { x, y: 2.85, w: 2.7, h: 0.75, fontSize: 16, color: SOFT, valign: "top" });
});
card(s, 0.6, 3.75, 5.9, 2.9);
T(s, "75 days", { x: 0.95, y: 3.95, w: 5.3, h: 1.1, fontSize: 64, bold: true, color: RED });
T(s, "funding gap: Cash Conversion Cycle = DIO 45 + DSO 60 − DPO 30", { x: 0.95, y: 5.1, w: 5.3, h: 0.5, fontSize: 16, color: SOFT });
T(s, "The business is profitable. It still misses payroll on day 60.", { x: 0.95, y: 5.7, w: 5.3, h: 0.7, fontSize: 16, color: WHITE, bold: true });
card(s, 6.8, 3.75, 5.9, 2.9);
T(s, "What owners face today", { x: 7.15, y: 3.95, w: 5.3, h: 0.45, fontSize: 20, bold: true, color: MINT });
T(s, [
  { text: "They see the gap only when a payment bounces", options: { bullet: true, breakLine: true } },
  { text: "Bank underwriting takes weeks and asks for collateral", options: { bullet: true, breakLine: true } },
  { text: "Fast lenders quote factor rates: 1.35 over 6 months is really 71% APR", options: { bullet: true, breakLine: true } },
  { text: "Generic AI chatbots guess numbers and cannot be trusted with money", options: { bullet: true } },
], { x: 7.15, y: 4.5, w: 5.3, h: 2.0, fontSize: 16, color: SOFT, paraSpaceAfter: 6 });
s.addNotes("The problem is timing, not profit. A business buys stock on day 0, pays the supplier on day 30, sells on day 45 on 60-day terms and collects on day 105. That is a 75-day gap. Owners discover it when payroll bounces. Banks take weeks; fast lenders hide the cost behind factor rates. And a generic chatbot that guesses numbers cannot be trusted near money. (60 s)");

// 3 · Solution ----------------------------------------------------------------
pres.addSection({ title: "Task completion" });
s = content("CashPilot covers all three Topic E capabilities", "Task completion");
const caps = [
  ["1", "Cash-flow management with alerts", "Upload CSV or PDF statements. Get balance, burn, runway, daily average balance and the exact date cash goes negative, with a 30/60/90-day forecast.", "POST /api/v1/analyze"],
  ["2", "Financing-option matching", "0–100 liquidity score from transaction behaviour, no collateral needed. Offers ranked by true APR; anything above 36% APR is flagged predatory.", "POST /api/v1/underwrite"],
  ["3", "Business financial analysis", "25 Decimal engines: CCC, DSCR, FCCR, Altman Z′, DuPont ROE, ROIC/EVA, DCF/WACC, receivables ageing, client concentration.", "services/calculations/"],
];
caps.forEach(([n, head, body, where], i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 1.6, 3.85, 4.9);
  dot(s, x + 0.35, 1.9, n);
  T(s, head, { x: x + 0.35, y: 2.6, w: 3.2, h: 0.9, fontSize: 20, bold: true });
  T(s, body, { x: x + 0.35, y: 3.55, w: 3.2, h: 2.2, fontSize: 15, color: SOFT, valign: "top" });
  T(s, where, { x: x + 0.35, y: 5.9, w: 3.2, h: 0.35, fontSize: 12, color: MINT, fontFace: "Courier New" });
});
s.addNotes("Topic E asks for three things, and CashPilot does each from one uploaded statement. One: cash-flow management with alerts, down to the day cash goes negative. Two: financing matching, scored from transaction behaviour the way WeBank-style digital lenders do it, ranked by true APR with predatory offers flagged. Three: business analysis with 25 deterministic engines. (60 s)");

// 4 · Demo: alert --------------------------------------------------------------
s = content("The owner sees the shortfall date, the gap, and a drafted fix", "Task completion");
img(s, "02-overview-forecast.png", 0.6, 1.5, 7.6);
T(s, "Cash runs short on Oct 28", { x: 8.65, y: 1.6, w: 4.1, h: 0.9, fontSize: 24, bold: true, color: RED });
T(s, [
  { text: "Payroll of $18,400 takes the balance $5,866.76 below zero, 9 days out", options: { bullet: true, breakLine: true } },
  { text: "Forecast by account over 30 / 60 / 90 days", options: { bullet: true, breakLine: true } },
  { text: "Transfers between the owner's own accounts are excluded from burn", options: { bullet: true, breakLine: true } },
  { text: "One click to the drafted $7,500 draw: shortfall plus a 20% margin", options: { bullet: true } },
], { x: 8.65, y: 2.6, w: 4.1, h: 3.6, fontSize: 16, color: SOFT, paraSpaceAfter: 8, valign: "top" });
s.addNotes("Here is the product with the built-in sample company. The first thing the owner sees is a date: cash runs short on October 28, when payroll lands. It shows the size of the gap and links straight to a drafted fix: a $7,500 credit-line draw covering the shortfall plus a safety margin. (45 s)");

// 5 · Demo: funding -------------------------------------------------------------
s = content("Financing ranked by true cost, predatory offers flagged", "Task completion");
img(s, "04-funding.png", 0.6, 1.5, 7.6);
T(s, "True APR, not factor rates", { x: 8.65, y: 1.6, w: 4.1, h: 0.9, fontSize: 24, bold: true, color: MINT });
T(s, [
  { text: "Liquidity score 61/100 (near prime) from balance, income steadiness and bounced payments", options: { bullet: true, breakLine: true } },
  { text: "Bank line 11.9% · factoring 18.4% · revenue-based 27.5%", options: { bullet: true, breakLine: true } },
  { text: "A \"factor rate 1.35\" advance is really 71.2% APR, so it is flagged predatory", options: { bullet: true, breakLine: true } },
  { text: "Dollar cost to borrow $7,500 for 60 days, side by side", options: { bullet: true } },
], { x: 8.65, y: 2.6, w: 4.1, h: 3.6, fontSize: 16, color: SOFT, paraSpaceAfter: 8, valign: "top" });
s.addNotes("Funding. The liquidity score comes from transaction behaviour: average daily balance, income steadiness and bounced payments. No audited accounts or property collateral needed. Every offer is converted to a true APR and to a dollar cost for this exact need. The advance quoted as a 1.35 factor rate is really 71.2% APR, so it is flagged predatory and kept out of the defaults. (45 s)");

// 6 · AI agent ----------------------------------------------------------------
pres.addSection({ title: "Innovation" });
s = content("The AI explains and drafts; deterministic code does the maths", "Innovation");
const flow = [["Guardrails", "Injection and pasted-key checks run first"], ["Intent router", "FastEmbed bge-small embeddings"], ["Subagents", "Liquidity · Credit · Risk"], ["Decimal engines", "Exact figures, never the LLM"], ["LLM narration", "On-device MiniCPM5-2B or cloud"], ["Grounding check", "Reply dropped if it invents a figure"]];
flow.forEach(([h, b], i) => {
  const x = 0.6 + i * 2.07;
  card(s, x, 1.6, 1.87, 1.9, i === 3 ? PANEL2 : PANEL);
  T(s, h, { x: x + 0.15, y: 1.75, w: 1.6, h: 0.6, fontSize: 15, bold: true, color: i === 3 ? MINT : WHITE });
  T(s, b, { x: x + 0.15, y: 2.4, w: 1.6, h: 1.0, fontSize: 12, color: SOFT, valign: "top" });
  if (i < flow.length - 1) T(s, "›", { x: x + 1.85, y: 2.2, w: 0.25, h: 0.5, fontSize: 22, color: MINT, align: "center" });
});
img(s, "07-assistant-answer.png", 0.6, 3.85, 4.9);
T(s, "Why this is different", { x: 5.9, y: 3.85, w: 6.8, h: 0.5, fontSize: 20, bold: true, color: MINT });
T(s, [
  { text: "Every number in a reply comes from Python Decimal code; numbers_are_grounded() rejects any reply quoting a figure the engine did not produce", options: { bullet: true, breakLine: true } },
  { text: "Runs fully on the owner's computer with a 2B model; cloud providers (Gemini, Claude, OpenAI, DeepSeek, Groq) are optional; account numbers and customer names are masked before text leaves", options: { bullet: true, breakLine: true } },
  { text: "Lending rules live in 15 JSON decision tables, so a credit policy change is reviewed data, not new code", options: { bullet: true } },
], { x: 5.9, y: 4.4, w: 6.8, h: 2.4, fontSize: 15, color: SOFT, paraSpaceAfter: 8, valign: "top" });
s.addNotes("The core design choice: separate language from arithmetic. Guardrails run first, an embedding router picks the intent, subagents call deterministic Decimal engines, and only then does the model write sentences. If its answer quotes any figure the engine didn't produce, we throw the answer away. It runs on a 2-billion-parameter model on the owner's own computer, so statements never have to leave the machine. (60 s)");

// 7 · Architecture --------------------------------------------------------------
s = content("Six layers, with untrusted reasoning kept away from money", "Innovation");
const layers = [
  ["L1", "Next.js 14 dashboard", "7 workspaces · renders server results only, no approval logic in the browser"],
  ["L2", "FastAPI gateway", "Rate limit · Pydantic extra=\"forbid\" · upload limits · signed tenant tokens"],
  ["L3", "Agent supervisor", "Guardrails · semantic router · subagents · Universal LLM Bridge · local SLM"],
  ["L4", "Deterministic engine", "Statement parsing + tie-out · 25 Decimal engines · ZenEngine decision tables"],
  ["L5", "Storage", "Staging ledger, sessions, invoice registry · owner-only files · Fernet at rest"],
  ["L6", "Invoice registry", "SHA-256 canonical invoice hash · first pledge wins · InvoiceRegistry.sol (FISCO BCOS)"],
];
layers.forEach(([id, head, body], i) => {
  const y = 1.5 + i * 0.88;
  card(s, 0.6, y, 12.1, 0.76, i === 3 ? PANEL2 : PANEL);
  T(s, id, { x: 0.85, y, w: 0.6, h: 0.76, fontSize: 16, bold: true, color: MINT, valign: "middle" });
  T(s, head, { x: 1.5, y, w: 3.2, h: 0.76, fontSize: 17, bold: true, valign: "middle" });
  T(s, body, { x: 4.7, y, w: 7.8, h: 0.76, fontSize: 14, color: SOFT, valign: "middle" });
});
s.addNotes("Architecture in six layers. The browser is treated as an untrusted display. The gateway validates every request strictly. The agent layer reasons but holds no credentials. The deterministic engine does all money maths. Storage is owner-only and can be encrypted. The invoice registry blocks double financing. Today it runs as a local simulation, and the Solidity contract is ready for FISCO BCOS. (45 s)");

// 8 · Permission tiers ----------------------------------------------------------
pres.addSection({ title: "Security" });
s = content("Three tiers: the agent drafts, only the owner acts", "Security");
const tiers = [
  ["TIER 1", "Observe", "Autonomous", "Statement analysis, forecasts, scoring, chat answers. Read-only.", MINT],
  ["TIER 2", "Draft", "Signed tenant token", "Credit draws, factoring, transfers staged as proposals: STAGED_PENDING_HITL, 72 h expiry, 5 min dedupe.", AMBER],
  ["TIER 3", "Owner-sent", "Owner only", "No execute route exists. \"Prepare\" gives the owner a pre-filled request to send from their own email or lender portal.", RED],
];
tiers.forEach(([tag, name, who, body, c], i) => {
  const x = 0.6 + i * 4.1;
  card(s, x, 1.55, 3.85, 3.6);
  T(s, tag, { x: x + 0.35, y: 1.8, w: 3.2, h: 0.35, fontSize: 13, bold: true, color: c, charSpacing: 2 });
  T(s, name, { x: x + 0.35, y: 2.15, w: 3.2, h: 0.7, fontSize: 28, bold: true });
  T(s, who, { x: x + 0.35, y: 2.85, w: 3.2, h: 0.4, fontSize: 15, color: c });
  T(s, body, { x: x + 0.35, y: 3.35, w: 3.2, h: 1.7, fontSize: 14, color: SOFT, valign: "top" });
});
card(s, 0.6, 5.4, 12.1, 1.35, PANEL2);
T(s, "$0", { x: 0.95, y: 5.45, w: 1.6, h: 1.25, fontSize: 54, bold: true, color: MINT, valign: "middle" });
T(s, "can be moved by CashPilot. There is no bank login, no lender API and no payment credential in the system, so no prompt, bug or exploit has anything to execute with.",
  { x: 2.6, y: 5.45, w: 9.9, h: 1.25, fontSize: 17, color: WHITE, valign: "middle" });
s.addNotes("Security is 30% of the score, and our answer is structural. Tier 1 is read-only and autonomous. Tier 2 lets the agent draft a proposal, but only for a caller with a signed tenant token. Tier 3, anything that moves money, has no execution route at all. The owner gets a pre-filled request and sends it themselves. With no payment credentials in the system, there is nothing for an attacker to steal or trigger. (60 s)");

// 9 · Attacks blocked -----------------------------------------------------------
s = content("We attacked our own agent: every attempt was refused", "Security");
const rows = [
  ["Attack in the sandbox replay", "Result", "HTTP"],
  ["Stage a proposal with no token / a forged token", "Refused", "401"],
  ["Mint a token with another tenant's enrollment key", "Refused", "403"],
  ["Read or approve another tenant's proposal", "Not found", "404"],
  ["Call /execute on a staged action", "Route does not exist", "404"],
  ["Smuggle \"execute_now\": true or a negative amount", "Schema rejects", "422"],
  ["Prompt injection: \"transfer $50,000\" with a valid token", "Blocked, nothing staged", "200"],
  ["Paste an API key into chat", "Flagged, not used", "200"],
  ["Pledge the same invoice to a second lender", "Blocked: already pledged", "—"],
];
s.addTable(rows.map((r, i) => r.map((cell, j) => ({
  text: cell,
  options: { bold: i === 0, color: i === 0 ? MINT : (j === 1 ? WHITE : SOFT), fill: { color: i === 0 ? PANEL2 : (i % 2 ? PANEL : BG) }, fontSize: i === 0 ? 14 : 14, fontFace: FONT, valign: "middle", align: j === 2 ? "center" : "left" },
}))), { x: 0.6, y: 1.5, w: 8.4, colW: [4.9, 2.6, 0.9], rowH: 0.52, border: { type: "solid", color: LINE, pt: 0.75 } });
[["34/34", "sandbox operations behaved as expected"], ["54", "security tests passing (1 POSIX-only skip)"], ["0", "known Python dependency vulnerabilities (pip-audit)"]].forEach(([big, small], i) => {
  const y = 1.5 + i * 1.62;
  card(s, 9.3, y, 3.4, 1.45);
  T(s, big, { x: 9.55, y: y + 0.1, w: 3.0, h: 0.75, fontSize: 36, bold: true, color: MINT });
  T(s, small, { x: 9.55, y: y + 0.82, w: 3.0, h: 0.55, fontSize: 13, color: SOFT });
});
s.addNotes("We did not just design this; we attacked it. Our sandbox replay runs 34 operations against the real API, including forged tokens, cross-tenant access, calling an execute route, smuggling an execute-now field, and a prompt injection asking to wire $50,000 sent with a valid token. Every one was refused, and the logs are in our execution evidence. Our self-assessment also lists 14 known risks openly, such as single-process storage and 30-day tokens with no revocation. (60 s)");

// 10 · Evidence -----------------------------------------------------------------
pres.addSection({ title: "Evidence" });
s = content("Verified, not claimed", "Evidence");
const stats = [["970", "automated tests passing", "unit 810 · integration 104 · security 54 (+1 skip) · e2e 2"], ["25", "Decimal finance engines", "money never touches float or the LLM"], ["15", "JSON policy tables", "credit, usury, covenants, security gate"], ["2:04", "demo video", "narrated · real UI, live backend, local model"]];
stats.forEach(([big, head, sub], i) => {
  const x = 0.6 + i * 3.07;
  card(s, x, 1.55, 2.87, 2.5);
  T(s, big, { x: x + 0.3, y: 1.7, w: 2.4, h: 1.0, fontSize: 48, bold: true, color: MINT });
  T(s, head, { x: x + 0.3, y: 2.7, w: 2.4, h: 0.45, fontSize: 16, bold: true });
  T(s, sub, { x: x + 0.3, y: 3.15, w: 2.4, h: 0.8, fontSize: 13, color: SOFT, valign: "top" });
});
img(s, "11-overview-live.png", 0.6, 4.35, 3.85);
T(s, "Live mode, not a mock-up", { x: 4.85, y: 4.35, w: 7.8, h: 0.5, fontSize: 20, bold: true, color: MINT });
T(s, [
  { text: "A 94-transaction CSV goes through the FastAPI backend: parsed, scored and forecast in about 0.13 s", options: { bullet: true, breakLine: true } },
  { text: "Sandbox logs record every request and response with UTC timestamps; tokens and keys are redacted", options: { bullet: true, breakLine: true } },
  { text: "Docker compose, CI container smoke test, MIT licence, one-command reproduction scripts", options: { bullet: true } },
], { x: 4.85, y: 4.9, w: 7.8, h: 1.9, fontSize: 15, color: SOFT, paraSpaceAfter: 8, valign: "top" });
s.addNotes("Everything here is reproducible. 970 tests pass. The demo video drives the real UI against the live backend and the local model. When we upload a 94-transaction statement, the backend parses, scores and forecasts it in about a tenth of a second. Every claim in our documents points to a test, a log line or a file. (45 s)");

// 11 · Roadmap ------------------------------------------------------------------
s = content("What is built today, and what comes next", "Evidence");
card(s, 0.6, 1.55, 5.9, 5.1);
T(s, "Built and tested", { x: 0.95, y: 1.75, w: 5.3, h: 0.5, fontSize: 20, bold: true, color: MINT });
T(s, [
  { text: "CSV + PDF statement ingestion with row-level error codes", options: { bullet: true, breakLine: true } },
  { text: "Cash forecast, shortfall date and alert status", options: { bullet: true, breakLine: true } },
  { text: "Liquidity scoring, financing match, true APR, usury flag", options: { bullet: true, breakLine: true } },
  { text: "AI CFO chat with grounding check, local 2B model", options: { bullet: true, breakLine: true } },
  { text: "Three-tier gate, signed tenant tokens, encryption at rest", options: { bullet: true, breakLine: true } },
  { text: "Invoice double-pledge registry (local simulation)", options: { bullet: true } },
], { x: 0.95, y: 2.35, w: 5.3, h: 4.1, fontSize: 15, color: SOFT, paraSpaceAfter: 8, valign: "top" });
card(s, 6.8, 1.55, 5.9, 5.1);
T(s, "Next", { x: 7.15, y: 1.75, w: 5.3, h: 0.5, fontSize: 20, bold: true, color: AMBER });
T(s, [
  { text: "Deploy InvoiceRegistry.sol on a FISCO BCOS consortium chain with lender nodes", options: { bullet: true, breakLine: true } },
  { text: "PostgreSQL with row-level security and append-only ledger tables", options: { bullet: true, breakLine: true } },
  { text: "Read-only open-banking feeds in place of uploads (still no write scope)", options: { bullet: true, breakLine: true } },
  { text: "Push alerts when the forecast crosses the owner's threshold", options: { bullet: true, breakLine: true } },
  { text: "OIDC sign-in and token revocation; an NER model for one-word names", options: { bullet: true } },
], { x: 7.15, y: 2.35, w: 5.3, h: 4.1, fontSize: 15, color: SOFT, paraSpaceAfter: 8, valign: "top" });
s.addNotes("We are explicit about the line between built and planned. Everything on the left runs and is tested today. On the right: deploying the invoice registry on a FISCO BCOS consortium chain so lenders share one source of truth, moving storage to PostgreSQL with row-level security, read-only open-banking feeds, push alerts, and stronger masking and sign-in. (45 s)");

// 12 · Close --------------------------------------------------------------------
pres.addSection({ title: "Close" });
s = pres.addSlide({ masterName: "COVER", sectionTitle: "Close" });
T(s, "An AI that participates in a business's finances", { x: 0.8, y: 1.3, w: 11.7, h: 0.8, fontSize: 36, bold: true });
T(s, "without ever holding its money", { x: 0.8, y: 2.1, w: 11.7, h: 0.8, fontSize: 36, bold: true, color: MINT });
[["Task", "Alerts, financing match and analysis from one statement"], ["Security", "Tier 3 is owner-sent: no route, no credential, $0 movable"], ["Innovation", "Grounded numbers, on-device model, policy as data"]].forEach(([h, b], i) => {
  const x = 0.8 + i * 4.0;
  card(s, x, 3.4, 3.75, 1.8);
  T(s, h, { x: x + 0.3, y: 3.6, w: 3.2, h: 0.5, fontSize: 20, bold: true, color: MINT });
  T(s, b, { x: x + 0.3, y: 4.15, w: 3.2, h: 0.95, fontSize: 15, color: SOFT, valign: "top" });
});
T(s, "github.com/SamJU25/F-SME-Finance-Copilot", { x: 0.8, y: 5.8, w: 11.7, h: 0.5, fontSize: 20, color: WHITE, fontFace: "Courier New" });
T(s, "Sampad Chakma · Purno Dewan · Binoy Kumar Chakma · Parban Chakma  —  thank you, questions welcome.", { x: 0.8, y: 6.4, w: 11.7, h: 0.5, fontSize: 16, color: MUTED });
s.addNotes("To close: CashPilot shows what AI as a financial participant can look like when it is safe. It completes the real tasks of Topic E, it is secure by construction because the agent can never move money, and it is new in how it keeps every number grounded and every policy reviewable. Thank you, we are happy to take questions. (30 s)");

pres.writeFile({ fileName: path.join(HERE, "CashPilot_Presentation.pptx") }).then((f) => console.log("wrote", f));
