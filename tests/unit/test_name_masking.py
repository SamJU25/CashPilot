"""Names in text bound for a cloud LLM are replaced with [PARTY_n] and restored in the reply."""

from unittest.mock import patch

import httpx

from services.agent.llm_bridge import query_external_llm
from services.agent.name_masking import NameMasker
from services.agent.schema import LLMConfig


def _masked(text: str) -> tuple[str, NameMasker]:
    masker = NameMasker()
    masker.collect(text)
    return masker.mask(text), masker


def test_person_and_company_names_are_masked():
    out, masker = _masked("Is Acme Corp paying us late? Should I chase John Smith at Northwind Foods?")
    assert "Acme" not in out and "Smith" not in out and "Northwind" not in out
    assert out == "Is [PARTY_1] paying us late? Should I chase [PARTY_2] at [PARTY_3]?"
    assert masker.unmask(out) == "Is Acme Corp paying us late? Should I chase John Smith at Northwind Foods?"


def test_all_caps_bank_description_keeps_transaction_words():
    out, _ = _masked("ACH PAYMENT NORTHWIND FOODS 2026-10-02 4500.00")
    assert out == "ACH PAYMENT [PARTY_1] 2026-10-02 4500.00"


def test_accented_latin_names_and_ampersands_are_masked():
    out, masker = _masked("Wire from José Müller to Smith & Sons; Café Lumière paid.")
    assert "Müller" not in out and "Smith" not in out and "Lumière" not in out
    assert masker.unmask(out) == "Wire from José Müller to Smith & Sons; Café Lumière paid."


def test_same_name_in_other_casing_gets_the_same_placeholder():
    masker = NameMasker()
    masker.collect("Invoice from Northwind Foods")
    assert masker.mask("NORTHWIND FOODS paid") == "[PARTY_1] paid"


def test_cashpilot_vocabulary_is_left_alone():
    text = ("Executive Persona & Tone Standards. Strict Anti-Slop Protocol. HEALTHY LIQUIDITY. "
            "Daily Average Balance and Cash Conversion Cycle. Verified Financial Engine Outputs.")
    out, masker = _masked(text)
    assert out == text
    assert masker.names == {}


def test_unmask_keeps_unknown_placeholders():
    masker = NameMasker()
    masker.collect("Pay Harbor Logistics GmbH")
    assert masker.unmask("[PARTY_1] and [PARTY_9]") == "Harbor Logistics GmbH and [PARTY_9]"


class _FakeResponse:
    status_code = 200

    def __init__(self, reply: str):
        self._reply = reply

    def json(self):
        return {"choices": [{"message": {"content": self._reply}}]}


def test_cloud_payload_carries_no_names_and_reply_is_restored():
    sent = {}

    def fake_post(self, url, *args, **kwargs):
        sent["payload"] = kwargs["json"]
        # Names are numbered in collection order: system instruction, then prompt, then history.
        return _FakeResponse("Chase [PARTY_1] first; [PARTY_2] is on time.")

    config = LLMConfig(provider="openai", api_key="sk-FAKE-DEMO-KEY-not-a-real-secret-000000", model_name="gpt-4o-mini")
    with patch.object(httpx.Client, "post", fake_post):
        reply = query_external_llm(
            prompt="Is Acme Corp late? Should I chase Northwind Foods?",
            system_instruction="Verified Financial Engine Outputs: Northwind Foods owes $12,400.00, 47 days overdue.",
            config=config,
            history=[{"role": "user", "text": "Acme Corp paid last week"}],
        )

    outgoing = " ".join(m["content"] for m in sent["payload"]["messages"])
    assert "Acme" not in outgoing and "Northwind" not in outgoing
    assert "$12,400.00" in outgoing
    assert reply == "Chase Northwind Foods first; Acme Corp is on time."
