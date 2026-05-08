"""P1-001: canonical-paradigm injection into extraction prompts.

Snapshots the deterministic shape of the canonical block and asserts
each stage prompt that consumes paradigm slugs (researcher, formalizer,
reasoner) embeds the block verbatim. Builder is asserted unchanged
because it emits ``Model.formulation_id`` rather than a paradigm slug.
"""

from __future__ import annotations

import json
from importlib.resources import files

from decisionlab.knowledge.prompts import (
    _CANONICAL,
    _CANONICAL_DIRECTIVE,
    _CANONICAL_LIST,
    BUILDER_SYSTEM,
    FORMALIZER_SYSTEM,
    REASONER_SYSTEM,
    RESEARCHER_SYSTEM,
)


def test_canonical_constant_loaded_from_packaged_data():
    """AC1+AC2: ``_CANONICAL`` is loaded once at import via
    ``importlib.resources`` and matches the shipped JSON byte-for-byte."""
    raw = (files("decisionlab.data") / "canonical-paradigms.json").read_text()
    expected = json.loads(raw)
    assert expected == _CANONICAL
    assert all({"slug", "name", "definition"} <= entry.keys() for entry in _CANONICAL)


def test_canonical_list_is_deterministic_and_numbered():
    """AC3: list order is the JSON file order (prompt-cache stability)."""
    expected_lines = [
        f"{i}. {p['slug']}: {p['definition']}"
        for i, p in enumerate(_CANONICAL, start=1)
    ]
    assert "\n".join(expected_lines) == _CANONICAL_LIST


def test_directive_contains_reuse_or_new_instruction():
    """The injected block must instruct the LLM to reuse a slug verbatim
    or fall back to ``__NEW__`` — that wording is the contract P1-002+
    relies on at the Literal-validation layer."""
    assert "reuse" in _CANONICAL_DIRECTIVE.lower()
    assert "__NEW__" in _CANONICAL_DIRECTIVE
    assert _CANONICAL_LIST in _CANONICAL_DIRECTIVE


def test_three_extraction_prompts_embed_canonical_block():
    """AC3: researcher/formalizer/reasoner system prompts contain the
    canonical block verbatim."""
    for prompt_name, prompt in (
        ("RESEARCHER_SYSTEM", RESEARCHER_SYSTEM),
        ("FORMALIZER_SYSTEM", FORMALIZER_SYSTEM),
        ("REASONER_SYSTEM", REASONER_SYSTEM),
    ):
        assert _CANONICAL_DIRECTIVE in prompt, (
            f"{prompt_name} missing the canonical-paradigm directive"
        )


def test_builder_prompt_unchanged_by_canonical_injection():
    """Builder emits ``Model.formulation_id``, not a paradigm slug, so
    the canonical list would be noise. Keep it out (per phase spec)."""
    assert _CANONICAL_DIRECTIVE not in BUILDER_SYSTEM


def test_canonical_list_contains_all_known_slugs():
    """Sanity: each fixture slug appears verbatim in the rendered list,
    so a regression that mangles slugs surfaces as a unit-test failure
    rather than at eval time."""
    for entry in _CANONICAL:
        assert entry["slug"] in _CANONICAL_LIST
        assert entry["definition"] in _CANONICAL_LIST
