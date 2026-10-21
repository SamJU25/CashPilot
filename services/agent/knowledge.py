"""
Concept-card retrieval for model prompts.

Cards in knowledge/cards/*.md (one "## " section per concept) are embedded once with the
FastEmbed model the semantic router already holds, so no second ONNX model is loaded.
Retrieved cards supply definitions and context only; business figures in a reply must
still come from the deterministic engine output (see prompts.numbers_are_grounded).
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from services.agent import trace

logger = logging.getLogger(__name__)

CARDS_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "cards"
TOP_K = 3
# Below this cosine similarity a card is unrelated to the question: with bge-small, off-topic
# questions ("pasta recipe", "hello") top out at 0.43-0.50 while concept questions hit 0.70-0.83.
MIN_SIMILARITY = 0.6
_METADATA_LINE = re.compile(r"^<!--.*?-->\s*", re.DOTALL)
_TOOLS_FIELD = re.compile(r"tools:\s*([\w, ]+?)\s*(?:\||-->)")

# Missing-input calculation key (as passed to get_missing_param_guidance) -> engine tool.
# Cards name tools in their metadata, which is how a question is matched to a calculation.
CALCULATION_TOOLS = {
    "ALTMAN_Z_SCORE": "tool_calculate_altman_z_score",
    "AMORTIZATION": "tool_calculate_loan_amortization",
    "ATTRITION": "tool_calculate_revenue_attrition_impact",
    "BREAK_EVEN": "tool_calculate_break_even",
    "BRIDGE_PLAN": "tool_build_bridge_plan",
    "BREAK_EVEN_UNITS": "tool_calculate_break_even_units",
    "CAC_PAYBACK": "tool_calculate_cac_payback",
    "CASH_DRAG": "tool_calculate_cash_drag",
    "CASH_SCENARIO": "tool_run_cash_scenario",
    "CONCENTRATION": "tool_calculate_client_concentration",
    "CURRENCY_CONVERSION": "tool_convert_currency",
    "CURRENT_RATIO": "tool_calculate_current_ratio",
    "DCF_VALUATION": "tool_calculate_dcf_valuation",
    "DEBT_CAPACITY": "tool_calculate_prudent_debt_capacity",
    "DEBT_SERVICE_BURDEN": "tool_calculate_debt_service_burden",
    "DEBT_TO_EQUITY": "tool_calculate_debt_to_equity",
    "DEFENSIVE_INTERVAL": "tool_calculate_defensive_interval",
    "DSCR": "tool_calculate_dscr",
    "DUPONT_ROE": "tool_calculate_dupont_roe",
    "ENTERPRISE_VALUE": "tool_calculate_enterprise_value",
    "EVA": "tool_calculate_eva",
    "FACTORING": "tool_calculate_factoring_proceeds",
    "FCCR": "tool_calculate_fccr",
    "FCFF": "tool_calculate_free_cash_flow",
    "FX_EXPOSURE": "tool_calculate_fx_exposure",
    "INTEREST_COVERAGE": "tool_calculate_interest_coverage",
    "INVOICE_HASH": "tool_verify_invoice_hash",
    "LEASE_VS_BUY": "tool_calculate_lease_vs_buy",
    "LTV_CAC": "tool_calculate_ltv_cac",
    "NET_DEBT_TO_EBITDA": "tool_calculate_net_debt_to_ebitda",
    "NRR": "tool_calculate_nrr",
    "OCF_RATIO": "tool_calculate_operating_cash_flow_ratio",
    "OUTFLOW_BREAKDOWN": "tool_analyze_outflow_breakdown",
    "QUICK_RATIO": "tool_calculate_quick_ratio",
    "RECEIVABLES_AGEING": "tool_analyze_receivables_ageing",
    "ROA": "tool_calculate_roa",
    "ROIC": "tool_calculate_roic",
    "TRADE_CREDIT": "tool_calculate_trade_credit_apr",
    "WACC": "tool_calculate_wacc",
    "WCR": "tool_calculate_wcr",
    "WORKING_CAPITAL": "tool_calculate_ccc",
}


@dataclass(frozen=True)
class Card:
    title: str
    area: str
    text: str
    tools: tuple[str, ...] = ()


def load_cards(cards_dir: Path = CARDS_DIR) -> list[Card]:
    cards = []
    for path in sorted(cards_dir.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
            title, _, body = block.partition("\n")
            body = body.strip()
            tools_match = _TOOLS_FIELD.search(body.split("\n", 1)[0])
            tools = tuple(t.strip() for t in tools_match.group(1).split(",")) if tools_match else ()
            cards.append(Card(title=title.strip(), area=path.stem, text=_METADATA_LINE.sub("", body), tools=tools))
    return cards


def _cards_mtime(cards_dir: Path = CARDS_DIR) -> float:
    mtimes = [p.stat().st_mtime for p in cards_dir.glob("*.md")]
    return max(mtimes) if mtimes else 0.0


class _CardIndex:
    _instance: Optional["_CardIndex"] = None
    _lock = threading.Lock()

    def __init__(self, mtime: float = 0.0) -> None:
        from services.agent.dynamic_router import FastEmbedSemanticRouter

        self._mtime = mtime
        router = FastEmbedSemanticRouter.get_instance()
        self._model = router._model if router._ready else None
        self.cards = load_cards()
        self._norms = None
        self._card_acronyms: list[set[str]] = []
        for c in self.cards:
            acrs = {a.upper() for a in re.findall(r"\(([A-Za-z0-9/'-]{2,10})\)", c.title)}
            self._card_acronyms.append(acrs)
        if self._model is not None and self.cards:
            passages = [f"{c.title}. {c.text.replace('**', '')}" for c in self.cards]
            embeds = np.array(list(self._model.passage_embed(passages)))
            self._norms = embeds / np.linalg.norm(embeds, axis=1, keepdims=True)

    @classmethod
    def get(cls) -> "_CardIndex":
        with cls._lock:
            current_mtime = _cards_mtime()
            if cls._instance is None or cls._instance._mtime < current_mtime:
                cls._instance = _CardIndex(mtime=current_mtime)
            return cls._instance

    def search(self, query: str, k: int, min_similarity: float) -> list[Card]:
        if self._norms is None or not query.strip():
            return []
        q = np.array(list(self._model.query_embed([query.strip()])))[0]
        sims = self._norms @ (q / np.linalg.norm(q))

        # Acronym exact match boost: if user query explicitly mentions a card's exact acronym,
        # boost by +0.35 so acronym queries never drop below threshold.
        q_tokens = {w.upper().strip("(),.?!\"'") for w in query.split()}
        for i, acrs in enumerate(self._card_acronyms):
            if acrs and acrs.intersection(q_tokens):
                sims[i] += 0.35

        order = np.argsort(sims)[::-1][:k]
        picked = [i for i in order if sims[i] >= min_similarity]
        for i in picked:
            trace.record("card", self.cards[i].title, trace.now_ms(), 0.0, file=f"{self.cards[i].area}.md", score=f"{float(sims[i]):.2f}")
        return [self.cards[i] for i in picked]


def resolve_retrieval_query(query: str, history: Optional[list] = None) -> str:
    """
    Expands anaphoric or elliptical follow-up questions with recent user context.
    For example: 'What if it falls below that?' with history mentioning DSCR
    expands to include the prior user question so retrieval finds the correct card.
    """
    if not history:
        return query
    recent_user_messages = []
    for item in history:
        role = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None) or "user"
        text = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None) or ""
        if str(role).lower() in ("user", "human") and text.strip():
            recent_user_messages.append(text.strip())

    if recent_user_messages:
        last_turn = recent_user_messages[-1]
        if last_turn.lower() not in query.lower():
            return f"{last_turn} {query}"
    return query


def retrieve_cards(
    query: str,
    k: int = TOP_K,
    min_similarity: float = MIN_SIMILARITY,
    history: Optional[list] = None,
) -> list[Card]:
    try:
        resolved = resolve_retrieval_query(query, history=history)
        return _CardIndex.get().search(resolved, k, min_similarity)
    except Exception as exc:
        logger.warning("Concept card retrieval unavailable: %s", exc)
        return []


def format_reference_cards(sys_directive: str, cards: list[Card]) -> str:
    if not cards:
        return sys_directive
    notes = "\n\n".join(f"### {c.title}\n{c.text}" for c in cards)
    return (
        f"{sys_directive}\n\n"
        "Reference notes (use for definitions and context; figures about this business must come "
        "only from the verified engine outputs or the owner's message):\n\n"
        f"{notes}"
    )


def append_reference_cards(
    sys_directive: str,
    query: str,
    k: int = TOP_K,
    history: Optional[list] = None,
) -> str:
    return format_reference_cards(sys_directive, retrieve_cards(query, k=k, history=history))


def select_concept_card(cards: list[Card], calculation: Optional[str]) -> tuple[Card, bool]:
    """
    Picks the card to summarise for a missing-input question and whether the calculation's
    "how to calculate" steps belong in the reply.

    The sub-intent router can pick the wrong calculation ("Explain the cash conversion cycle"
    lands on cash drag), so steps are kept only when a retrieved card names that calculation's
    tool. Calculations no card covers keep their steps, since relevance cannot be judged.
    """
    tool = CALCULATION_TOOLS.get(calculation or "")
    if tool is None:
        return cards[0], True
    matching = next((c for c in cards if tool in c.tools), None)
    if matching is not None:
        return matching, True
    covered = any(tool in c.tools for c in _CardIndex.get().cards)
    return cards[0], not covered


def card_summary(card: Card) -> str:
    """The card's definition and importance as plain prose, used when no model is available."""
    parts = []
    for label in ("What it is:", "Why it matters:"):
        match = re.search(rf"\*\*{re.escape(label)}\*\*\s*(.+)", card.text)
        if match:
            parts.append(match.group(1).strip())
    return " ".join(parts)
