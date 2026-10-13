# SME Finance Copilot

Autonomous AI CFO and Financial Participant for Small and Medium Enterprises (SMEs).

---

## 1. Quick Start for Teammates

### Step 1: Clone Repository
```bash
git clone <repo-url>
cd "SME Finance Copilot"
```

### Step 2: Install Python Dependencies
```bash
pip install -r requirements.txt
```
This installs the FastAPI backend stack, test frameworks, `graphifyy` (AST knowledge graph engine), and `agent-reach` (read-only internet routing).

### Step 3: Install Frontend Dependencies (Optional / When Building UI)
```bash
npm install
```

---

## 2. Using AI Coding Assistants

### Google Antigravity
- Fully automatic: Antigravity detects [`.agent/`](file:///F:/SME%20Finance%20Copilot/.agent) and [`GEMINI.md`](file:///F:/SME%20Finance%20Copilot/GEMINI.md) immediately on workspace open.
- All 10 architectural rules, 54 execution skills, and 57 subagents activate natively.

### Claude / Claude Code
- Fully automatic: Claude Code reads [`CLAUDE.md`](file:///F:/SME%20Finance%20Copilot/CLAUDE.md) on launch.
- Operates under the identical 10 invariants (Anti-Slop, Ponytail Ladder, ADHD output, 3-Tier Security) and references [`.agent/skills/`](file:///F:/SME%20Finance%20Copilot/.agent/skills) and [`.agent/agents/`](file:///F:/SME%20Finance%20Copilot/.agent/agents).

### Cursor / VS Code / Other Assistants
- Reference [`GEMINI.md`](file:///F:/SME%20Finance%20Copilot/GEMINI.md) or [`CLAUDE.md`](file:///F:/SME%20Finance%20Copilot/CLAUDE.md) as the project instruction file.

---

## 3. Core Developer Commands

| Task | Command |
|---|---|
| Rebuild AST Knowledge Graph | `python -m graphify update .` |
| Run Test Suite | `pytest` |
| Start FastAPI Backend | `uvicorn src.main:app --reload --port 8000` |
| Start Next.js Dashboard | `npm run dev` |
| Check Research Routing | `agent-reach doctor --json` |

---

## 4. Key Documentation Links
- [`AGENTS.md`](file:///F:/SME%20Finance%20Copilot/AGENTS.md): Complete catalog of all 57 subagents across 8 squads and Scenario Routing Matrix.
- [`GEMINI.md`](file:///F:/SME%20Finance%20Copilot/GEMINI.md): Engineering rules, 10 invariants, and 7 SME domain workflows for Google Antigravity.
- [`CLAUDE.md`](file:///F:/SME%20Finance%20Copilot/CLAUDE.md): Operational protocol and invariant enforcement for Claude Code.
- [`GLOSSARY.md`](file:///F:/SME%20Finance%20Copilot/GLOSSARY.md): Ubiquitous domain dictionary (Cash Conversion Cycle, DSCR, WeBank Weiyidai, FISCO BCOS).
- [`graphify-out/wiki/index.md`](file:///F:/SME%20Finance%20Copilot/graphify-out/wiki/index.md): Persistent AST architecture knowledge graph and wiki.
