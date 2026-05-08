"""PPR traversal — type-filtered relations + IDF-decayed score."""

from unittest.mock import AsyncMock

import pytest

from decisionlab.knowledge.retrieval.kg_retrieval import (
    _LinkedEntity,
    _ppr_traverse,
    _score_node,
    _types_for_intent,
)


@pytest.mark.asyncio
async def test_ppr_passes_allowed_types_for_paradigm_intent():
    """Paradigm intent should restrict traversal to paradigm-relevant
    relation types (SUPPORTS, CONTRADICTS, EXTENDS, BELONGS_TO)."""
    kg = AsyncMock()
    # First call: seed lookup. Second call: traversal.
    kg.query = AsyncMock(
        side_effect=[
            [{"id": "el-1", "labels": ["Paradigm"], "props": {"slug": "rl"}}],
            [],  # no neighbors
        ]
    )

    linked = [
        _LinkedEntity(node_id="el-1", label="Paradigm", name="RL", confidence=1.0)
    ]
    await _ppr_traverse(linked, kg, intent="paradigm")

    # Find the traversal call (second call) — its params should include
    # allowed_types covering paradigm-intent relation types.
    traversal_call = kg.query.call_args_list[1]
    cypher = traversal_call.args[0]
    params = traversal_call.args[1] if len(traversal_call.args) > 1 else {}

    assert "allowed_types" in params
    assert "EXTENDS" in params["allowed_types"]
    assert "BELONGS_TO" in params["allowed_types"]
    # Cypher should reference the parameter for filtering relation types.
    assert "$allowed_types" in cypher


@pytest.mark.asyncio
async def test_ppr_passes_variable_intent_types():
    kg = AsyncMock()
    kg.query = AsyncMock(
        side_effect=[
            [{"id": "el-1", "labels": ["Variable"], "props": {"name": "v"}}],
            [],
        ]
    )
    linked = [_LinkedEntity(node_id="el-1", label="Variable", name="v", confidence=1.0)]
    await _ppr_traverse(linked, kg, intent="variable")

    params = kg.query.call_args_list[1].args[1]
    assert "MEASURES" in params["allowed_types"]


def test_score_damps_high_degree_more_than_low_degree():
    """log-degree dampening: a hub with 200 connections should score
    lower than a leaf with 2."""
    high = _score_node(confidence=1.0, hops=1, degree=200)
    low = _score_node(confidence=1.0, hops=1, degree=2)
    assert low > high


def test_score_decays_with_hops():
    """Each extra hop multiplies score by 0.85 (PPR decay)."""
    s1 = _score_node(confidence=1.0, hops=1, degree=10)
    s2 = _score_node(confidence=1.0, hops=2, degree=10)
    assert s1 > s2
    assert s2 == pytest.approx(s1 * 0.85, rel=1e-6)


def test_types_for_intent_known_intents():
    para = _types_for_intent("paradigm")
    var = _types_for_intent("variable")
    assert "EXTENDS" in para
    assert "MEASURES" in var
    # The two intents should be distinct sets.
    assert set(para) != set(var)


def test_types_for_intent_unknown_intent_falls_back_to_paradigm():
    assert _types_for_intent("nonsense") == _types_for_intent("paradigm")
