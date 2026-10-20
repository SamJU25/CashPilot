"""Retrieval of concept cards into model prompts."""

import pytest

from services.agent.knowledge import (
    append_reference_cards,
    load_cards,
    retrieve_cards,
)


def test_load_cards_strips_metadata():
    cards = load_cards()
    assert len(cards) >= 90
    assert all("<!--" not in c.text for c in cards)
    assert any(c.title == "Debt Service Coverage Ratio (DSCR)" for c in cards)


@pytest.mark.parametrize(
    "question,expected_title",
    [
        ("What is DSCR and why do lenders care about it?", "Debt Service Coverage Ratio (DSCR)"),
        ("How does invoice factoring work?", "Invoice Factoring"),
        ("Explain the cash conversion cycle", "Cash Conversion Cycle (CCC)"),
        ("Who sends a transfer the copilot drafts for me?", "Tier 3: Owner-Sent Actions"),
        ("Is a factor rate the same as an interest rate?", "Factor Rate vs APR"),
        ("What does LTV to CAC tell me about my marketing spend?", "LTV to CAC Ratio"),
    ],
)
def test_retrieves_relevant_card(question, expected_title):
    titles = [c.title for c in retrieve_cards(question)]
    assert expected_title in titles, titles


def test_returns_at_most_three_cards():
    assert len(retrieve_cards("How do working capital, receivables and inventory affect my cash?")) <= 3


@pytest.mark.parametrize("question", ["Give me a good pasta recipe", "Who won the football match last night?"])
def test_off_topic_questions_get_no_cards(question):
    assert retrieve_cards(question) == []


def test_append_reference_cards_adds_notes_and_keeps_directive():
    directive = "BASE DIRECTIVE"
    out = append_reference_cards(directive, "What is DSCR?")
    assert out.startswith(directive)
    assert "Reference notes" in out
    assert "Debt Service Coverage Ratio (DSCR)" in out


def test_append_reference_cards_unchanged_when_nothing_matches():
    assert append_reference_cards("BASE DIRECTIVE", "Give me a good pasta recipe") == "BASE DIRECTIVE"


def test_advisory_prompt_includes_reference_cards():
    """The model writing a cash diagnostic reply receives the matching concept cards."""
    from unittest.mock import patch

    from services.agent.schema import AgentChatRequest, LLMConfig
    from services.agent.supervisor import run_copilot_supervisor

    csv = (
        "transaction_id,posted_on,amount,currency,description,closing_balance\n"
        "tx_001,2026-01-01,1000.00,USD,Client Invoice,10000.00\n"
        "tx_002,2026-01-05,-1500.00,USD,Supplier,8500.00\n"
        "tx_003,2026-01-10,-2000.00,USD,Rent,6500.00\n"
    )
    captured = {}

    def fake_llm(prompt, system_instruction, config, history=None):
        captured["system"] = system_instruction
        return None

    with patch("services.agent.supervisor.query_external_llm", side_effect=fake_llm):
        run_copilot_supervisor(
            AgentChatRequest(message="How long will our cash runway last?", csv_content=csv),
            llm_config=LLMConfig(provider="gemini", model_name="gemini-2.0-flash", api_key="test-key"),
        )

    assert "Reference notes" in captured.get("system", "")
    assert "Cash Runway" in captured["system"]


@pytest.mark.parametrize(
    "acronym,expected_title",
    [
        ("DIO", "Days Inventory Outstanding (DIO)"),
        ("WCR", "Working Capital Requirement (WCR)"),
        ("FCCR", "Fixed Charge Coverage Ratio (FCCR)"),
        ("CCC", "Cash Conversion Cycle (CCC)"),
        ("DSO", "Days Sales Outstanding (DSO)"),
        ("EVA", "Economic Value Added (EVA)"),
        ("WACC", "Weighted Average Cost of Capital (WACC)"),
    ],
)
def test_acronym_exact_match_boost(acronym, expected_title):
    cards = retrieve_cards(acronym)
    assert len(cards) >= 1
    assert cards[0].title == expected_title


def test_multiturn_contextual_retrieval():
    turn2_query = "What if our business falls below that threshold?"
    # Without history, anaphoric query misses the DSCR card
    cards_no_history = retrieve_cards(turn2_query)
    assert not any("DSCR" in c.title for c in cards_no_history)

    # With history mentioning DSCR, contextual resolution accurately retrieves DSCR as #1
    history = [{"role": "user", "text": "What is the DSCR benchmark for commercial loans?"}]
    cards_with_history = retrieve_cards(turn2_query, history=history)
    assert len(cards_with_history) >= 1
    assert "Debt Service Coverage Ratio (DSCR)" in cards_with_history[0].title
