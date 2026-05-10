"""Unit tests for ``decisionlab.knowledge.canonicalize``.

Six scenarios cover the public API:

1. Canonical-only extraction → identity (no KG/Sonnet calls).
2. Strong-match MERGE → existing slug propagated to siblings + relations.
3. Weak-match (below τ) → mint via ``slugify``, no Sonnet call.
4. Strong-match but verify-merge says ``MINT_NEW`` → mint.
5. ``StructuredOutputError`` from verify-merge → degrade to mint.
6. ``__NEW__`` Postulate prefix rewrite + relation endpoint remap.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from decisionlab.knowledge import canonicalize as canon
from decisionlab.knowledge.canonicalize import canonicalize_extraction
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.structured import StructuredOutputError

# ---- helpers ---------------------------------------------------------------


def _kg_returning(rows: list[dict]) -> AsyncMock:
    kg = AsyncMock()
    kg.query = AsyncMock(return_value=rows)
    return kg


def _embeddings_with_vector(vec: list[float] | None = None) -> AsyncMock:
    emb = AsyncMock()
    emb.embed_query = AsyncMock(return_value=vec or [0.1] * 1024)
    return emb


def _client() -> AsyncMock:
    """Anthropic client placeholder; never invoked directly because we
    monkeypatch ``call_structured`` at the canonicalize-module level."""
    return AsyncMock()


def _paradigm_node(slug: str, name: str, description: str = "") -> NodeSpec:
    return NodeSpec(
        label="Paradigm",
        properties={"slug": slug, "name": name, "description": description},
        natural_key=slug,
    )


def _variable_node(name: str, paradigm_slug: str) -> NodeSpec:
    return NodeSpec(
        label="Variable",
        properties={"name": name, "paradigm_slug": paradigm_slug},
        natural_key=name,
    )


def _postulate_node(pid: str, paradigm_slug: str) -> NodeSpec:
    return NodeSpec(
        label="Postulate",
        properties={
            "id": pid,
            "statement": "x",
            "falsifiable": True,
            "paradigm_slug": paradigm_slug,
        },
        natural_key=pid,
    )


def _extraction(
    nodes: list[NodeSpec],
    relations: list[RelationSpec] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        nodes=nodes,
        relations=relations or [],
        facts=[],
        stage="researcher",
        run_id="r1",
    )


# ---- 1. canonical-only extraction → identity -------------------------------


@pytest.mark.asyncio
async def test_canonical_only_extraction_is_identity(monkeypatch):
    """No ``__NEW__`` anywhere → cheap exit, no KG/Sonnet calls."""
    extraction = _extraction(
        [
            _paradigm_node("reinforcement-learning", "RL", "."),
            _variable_node("reward", "reinforcement-learning"),
        ]
    )
    kg = AsyncMock()
    kg.query = AsyncMock()
    embeddings = _embeddings_with_vector()
    called = {"verify": 0}

    async def _fake_call_structured(**_kwargs):
        called["verify"] += 1
        raise AssertionError("call_structured must not run for canonical-only")

    monkeypatch.setattr(canon, "call_structured", _fake_call_structured)

    result = await canonicalize_extraction(
        extraction, kg=kg, embeddings=embeddings, client=_client()
    )
    assert result is extraction
    kg.query.assert_not_awaited()
    embeddings.embed_query.assert_not_awaited()
    assert called["verify"] == 0


# ---- 2. strong-match MERGE -------------------------------------------------


@pytest.mark.asyncio
async def test_strong_match_merge_propagates_to_siblings(monkeypatch):
    """ANN returns a hit at 0.92; verify-merge says MERGE → canonical slug
    is rewritten on the Paradigm AND propagated to the sibling Variable
    that was scoped to ``__NEW__``."""
    extraction = _extraction(
        [
            _paradigm_node("__NEW__", "TD eligibility traces", "TD(λ) traces."),
            _variable_node("eligibility", "__NEW__"),
        ],
        [
            RelationSpec(
                from_label="Variable",
                from_key_value="eligibility",
                to_label="Paradigm",
                to_key_value="__NEW__",
                rel_type="USED_IN",
            ),
        ],
    )
    kg = _kg_returning(
        [
            {
                "slug": "reinforcement-learning",
                "name": "RL",
                "description": "Action-value learning.",
                "score": 0.92,
            }
        ]
    )

    class _Verdict:
        decision = "MERGE"
        canonical_slug = "reinforcement-learning"
        reasoning = "TD is an RL variant."

    fake = AsyncMock(return_value=_Verdict())
    monkeypatch.setattr(canon, "call_structured", fake)

    result = await canonicalize_extraction(
        extraction,
        kg=kg,
        embeddings=_embeddings_with_vector(),
        client=_client(),
    )

    paradigm = next(n for n in result.nodes if n.label == "Paradigm")
    variable = next(n for n in result.nodes if n.label == "Variable")
    assert paradigm.properties["slug"] == "reinforcement-learning"
    assert paradigm.natural_key == "reinforcement-learning"
    assert variable.properties["paradigm_slug"] == "reinforcement-learning"
    # Relation endpoint also remapped
    assert result.relations[0].to_key_value == "reinforcement-learning"
    fake.assert_awaited_once()


# ---- 3. weak-match → mint, no Sonnet ---------------------------------------


@pytest.mark.asyncio
async def test_weak_match_mints_without_verify(monkeypatch):
    """ANN top hit at 0.70 < τ=0.85 → mint via slugify, never call verify-merge."""
    extraction = _extraction(
        [_paradigm_node("__NEW__", "Bounded Rationality", "Herb Simon's BR.")]
    )
    kg = _kg_returning(
        [
            {
                "slug": "expected-utility-theory",
                "name": "EUT",
                "description": "Rational choice.",
                "score": 0.70,
            }
        ]
    )

    async def _fake_call_structured(**_kwargs):
        raise AssertionError("verify-merge must not run below τ")

    monkeypatch.setattr(canon, "call_structured", _fake_call_structured)

    result = await canonicalize_extraction(
        extraction,
        kg=kg,
        embeddings=_embeddings_with_vector(),
        client=_client(),
    )
    paradigm = next(n for n in result.nodes if n.label == "Paradigm")
    assert paradigm.properties["slug"] == "bounded-rationality"
    assert paradigm.natural_key == "bounded-rationality"


# ---- 4. strong-match but verdict says MINT_NEW -----------------------------


@pytest.mark.asyncio
async def test_strong_match_but_mint_new_verdict_mints(monkeypatch):
    """ANN at 0.90 (≥τ); verify-merge says MINT_NEW → mint via slugify."""
    extraction = _extraction(
        [_paradigm_node("__NEW__", "SARSA", "On-policy TD control.")]
    )
    kg = _kg_returning(
        [
            {
                "slug": "q-learning",
                "name": "Q-learning",
                "description": "Off-policy TD control.",
                "score": 0.90,
            }
        ]
    )

    class _Verdict:
        decision = "MINT_NEW"
        canonical_slug = None
        reasoning = "Siblings under RL, not the same paradigm."

    fake = AsyncMock(return_value=_Verdict())
    monkeypatch.setattr(canon, "call_structured", fake)

    result = await canonicalize_extraction(
        extraction,
        kg=kg,
        embeddings=_embeddings_with_vector(),
        client=_client(),
    )
    paradigm = next(n for n in result.nodes if n.label == "Paradigm")
    assert paradigm.properties["slug"] == "sarsa"
    fake.assert_awaited_once()


# ---- 5. verify-merge raises StructuredOutputError → mint -------------------


@pytest.mark.asyncio
async def test_verify_merge_structured_output_error_mints(monkeypatch, caplog):
    """Sonnet schema violation degrades to mint without raising out."""
    extraction = _extraction(
        [_paradigm_node("__NEW__", "Active Inference", "Free-energy active inference.")]
    )
    kg = _kg_returning(
        [
            {
                "slug": "free-energy-principle",
                "name": "FEP",
                "description": "Helmholtz-style FEP.",
                "score": 0.93,
            }
        ]
    )

    async def _raise_struct(**_kwargs):
        raise StructuredOutputError("schema violation", raw=None)

    monkeypatch.setattr(canon, "call_structured", _raise_struct)

    with caplog.at_level("WARNING"):
        result = await canonicalize_extraction(
            extraction,
            kg=kg,
            embeddings=_embeddings_with_vector(),
            client=_client(),
        )
    paradigm = next(n for n in result.nodes if n.label == "Paradigm")
    assert paradigm.properties["slug"] == "active-inference"
    assert any("verify-merge failed" in rec.message for rec in caplog.records)


# ---- 6. __NEW__ Postulate prefix rewrite -----------------------------------


@pytest.mark.asyncio
async def test_postulate_prefix_remapped_to_canonical(monkeypatch):
    """Postulate.id ``__NEW__:P1`` → ``<canonical>:P1`` after MERGE; relation
    endpoint and natural_key follow."""
    extraction = _extraction(
        [
            _paradigm_node(
                "__NEW__", "Predictive coding", "Hierarchical prediction error."
            ),
            _postulate_node("__NEW__:P1", "__NEW__"),
        ],
        [
            RelationSpec(
                from_label="Postulate",
                from_key_value="__NEW__:P1",
                to_label="Paradigm",
                to_key_value="__NEW__",
                rel_type="POSTULATED_BY",
            ),
        ],
    )
    kg = _kg_returning(
        [
            {
                "slug": "free-energy-principle",
                "name": "FEP",
                "description": "Free-energy principle.",
                "score": 0.91,
            }
        ]
    )

    class _Verdict:
        decision = "MERGE"
        canonical_slug = "free-energy-principle"
        reasoning = "Predictive coding is a mechanism under FEP."

    monkeypatch.setattr(canon, "call_structured", AsyncMock(return_value=_Verdict()))

    result = await canonicalize_extraction(
        extraction,
        kg=kg,
        embeddings=_embeddings_with_vector(),
        client=_client(),
    )

    postulate = next(n for n in result.nodes if n.label == "Postulate")
    paradigm = next(n for n in result.nodes if n.label == "Paradigm")
    assert paradigm.properties["slug"] == "free-energy-principle"
    assert postulate.properties["id"] == "free-energy-principle:P1"
    assert postulate.natural_key == "free-energy-principle:P1"
    assert postulate.properties["paradigm_slug"] == "free-energy-principle"
    rel = result.relations[0]
    assert rel.from_key_value == "free-energy-principle:P1"
    assert rel.to_key_value == "free-energy-principle"
