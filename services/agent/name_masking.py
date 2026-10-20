"""Reversible masking of counterparty and person names in text sent to cloud LLM providers.

A name is a run of two or more capitalised words in any Latin-script alphabet (Title Case or ALL CAPS, as bank
descriptions use; "José Müller" counts) that contains
at least one word CashPilot itself never uses. CashPilot's vocabulary is harvested from its own prompt code,
engine code, decision tables and knowledge cards, so prompt headings ("Executive Persona", "HEALTHY LIQUIDITY")
and finance terms ("Daily Average Balance") stay readable while "Northwind Foods" or "JOHN SMITH" do not leave
the machine. Each name becomes [PARTY_n] in every outgoing text; unmask() puts the real names back into the reply.

shortcut: a lone capitalised word ("Sarah"), names built only from CashPilot's own words ("Capital Partners") and names
in scripts without letter case (Chinese, Bengali, Devanagari) are not masked; upgrade to a multilingual NER model
if statements commonly carry those.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_VOCAB_SOURCES = (
    ("services/agent", "*.py"),
    ("services/calculations", "*.py"),
    ("services/decision", "**/*.py"),
    ("contracts/decision_tables", "*.json"),
    ("knowledge/cards", "*.md"),
)
# Placeholder company names used in example strings inside the vocabulary sources.
_EXAMPLE_NAMES = {"acme", "globex"}
_EXTRA_GENERIC = {
    "ach", "pos", "atm", "eft", "pmt", "dd", "ref", "inv", "vat", "gst",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
}

_TOKEN = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*\.?")
_JOINER = re.compile(r"\s+|\s*&\s*")
_PLACEHOLDER = re.compile(r"\[?PARTY_(\d+)\]?")


@lru_cache(maxsize=1)
def generic_words() -> frozenset[str]:
    words: set[str] = set(_EXTRA_GENERIC)
    for folder, pattern in _VOCAB_SOURCES:
        for path in (_ROOT / folder).glob(pattern):
            if path.name == "name_masking.py":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Split camelCase and snake_case so identifiers contribute their parts.
            text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ")
            words.update(w.lower() for w in re.findall(r"[A-Za-z]{2,}", text))
    return frozenset(words - _EXAMPLE_NAMES)


def _capitalised_runs(text: str) -> list[list[re.Match]]:
    """Runs of two or more capitalised tokens (any Latin-script letters, e.g. "José Müller") joined by spaces or "&"."""
    runs: list[list[re.Match]] = []
    current: list[re.Match] = []
    for tok in _TOKEN.finditer(text):
        word = tok.group(0).rstrip(".")
        capitalised = len(word) >= 2 and word[0].isupper()
        joined = bool(current) and _JOINER.fullmatch(text[current[-1].end():tok.start()]) is not None
        if capitalised and (joined or not current):
            current.append(tok)
            continue
        if len(current) >= 2:
            runs.append(current)
        current = [tok] if capitalised else []
    if len(current) >= 2:
        runs.append(current)
    return runs


def _name_core(run: list[re.Match], text: str) -> str | None:
    # Only leading words are trimmed ("Is Acme Corp", "ACH PAYMENT NORTHWIND FOODS"); trailing words stay so a
    # name ending in a common word ("Northwind Foods") is masked whole.
    tokens = list(run)
    while tokens and _is_generic(tokens[0].group(0)):
        tokens.pop(0)
    if not tokens or all(_is_generic(t.group(0)) for t in tokens):
        return None
    return text[tokens[0].start():tokens[-1].end()].rstrip(".")


def _is_generic(token: str) -> bool:
    # "&" and hyphenated words ("Anti-Slop") count as generic when every letter run is CashPilot vocabulary.
    generic = generic_words()
    return all(part.lower() in generic for part in re.findall(r"[^\W\d_]+", token))


class NameMasker:
    """One request's name-to-placeholder map, so every outgoing text and the reply use the same placeholders."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def collect(self, text: str | None) -> None:
        text = text or ""
        for run in _capitalised_runs(text):
            name = _name_core(run, text)
            if name and name.lower() not in {n.lower() for n in self.names}:
                self.names[name] = f"[PARTY_{len(self.names) + 1}]"

    def mask(self, text: str | None) -> str | None:
        if not text or not self.names:
            return text
        # Longest first so "Northwind Foods Ltd" is replaced before "Northwind Foods".
        for name in sorted(self.names, key=len, reverse=True):
            text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", self.names[name], text, flags=re.IGNORECASE)
        return text

    def unmask(self, text: str | None) -> str | None:
        if not text or not self.names:
            return text
        by_index = {placeholder[len("[PARTY_"):-1]: name for name, placeholder in self.names.items()}
        return _PLACEHOLDER.sub(lambda m: by_index.get(m.group(1), m.group(0)), text)
