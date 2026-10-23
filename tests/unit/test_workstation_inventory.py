"""The workstation map draws the system's inventory from constants in model.ts; fail when the backend outgrows them."""

import re
from pathlib import Path

from services.decision.types import DecisionDomain

ROOT = Path(__file__).resolve().parents[2]
MODEL = (ROOT / "src/components/workstation/model.ts").read_text(encoding="utf8")


def _block(name: str) -> str:
    return MODEL[MODEL.index(name) :].split("] as const" if "FILES" in name else "};", 1)[0]


def test_knowledge_files_match_cards_folder():
    drawn = set(re.findall(r"'([\w.]+\.md)'", _block("KNOWLEDGE_FILES")))
    on_disk = {p.name for p in (ROOT / "knowledge/cards").glob("*.md")}
    assert drawn == on_disk


def test_agent_tool_counts_match_subagent_imports():
    for agent, module in [("liquidity", "liquidity"), ("credit", "credit"), ("risk", "risk")]:
        src = (ROOT / f"services/agent/subagents/{module}_subagent.py").read_text(encoding="utf8")
        tools = set(re.findall(r"\btool_\w+", src))
        entry = re.search(rf"{agent}: {{ count: (\d+), examples: \[([^\]]*)\]", _block("AGENT_TOOLS"))
        assert entry, agent
        assert int(entry.group(1)) == len(tools), agent
        assert set(re.findall(r"'(tool_\w+)'", entry.group(2))) <= tools, agent


def test_decision_domain_count():
    assert f"DECISION_DOMAINS = {len(DecisionDomain)};" in MODEL
