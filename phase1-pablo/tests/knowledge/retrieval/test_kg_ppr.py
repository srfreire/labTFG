"""PPR traversal — type-filtered relations + IDF-decayed score."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import kg_retrieval as kg_module
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
async def test_ppr_filters_memory_backed_paths_by_as_of_lifecycle(monkeypatch):
    """Active lifecycle filtering keeps live PG-backed and memoryless paths."""
    checkpoint = datetime(2026, 4, 10, tzinfo=UTC)
    db_session = MagicMock()

    async def fake_select_valid_memory_ids(session, as_of, *, namespace):
        assert session is db_session
        assert as_of == checkpoint
        assert namespace == "kg_relation"
        return ["live-id"]

    monkeypatch.setattr(
        kg_module,
        "select_valid_memory_ids",
        fake_select_valid_memory_ids,
    )

    kg = AsyncMock()
    kg.query = AsyncMock(
        side_effect=[
            [{"id": "el-1", "labels": ["Variable"], "props": {"name": "v"}}],
            [
                {
                    "id": "live",
                    "labels": ["Variable"],
                    "props": {"name": "live"},
                    "hops": 1,
                    "rel_types": ["MEASURES"],
                    "rel_memory_ids": ["live-id"],
                    "degree": 1,
                },
                {
                    "id": "canonical",
                    "labels": ["Paradigm"],
                    "props": {"name": "canonical"},
                    "hops": 1,
                    "rel_types": ["BELONGS_TO"],
                    "rel_memory_ids": [None],
                    "degree": 1,
                },
                {
                    "id": "mixed",
                    "labels": ["Paradigm"],
                    "props": {"name": "mixed"},
                    "hops": 2,
                    "rel_types": ["MEASURES", "BELONGS_TO"],
                    "rel_memory_ids": ["live-id", None],
                    "degree": 1,
                },
                {
                    "id": "expired",
                    "labels": ["Variable"],
                    "props": {"name": "expired"},
                    "hops": 1,
                    "rel_types": ["MEASURES"],
                    "rel_memory_ids": ["expired-id"],
                    "degree": 1,
                },
                {
                    "id": "mixed-expired",
                    "labels": ["Paradigm"],
                    "props": {"name": "mixed-expired"},
                    "hops": 2,
                    "rel_types": ["MEASURES", "BELONGS_TO"],
                    "rel_memory_ids": ["live-id", "expired-id"],
                    "degree": 1,
                },
            ],
        ]
    )

    linked = [_LinkedEntity(node_id="el-1", label="Variable", name="v", confidence=1)]
    result = await _ppr_traverse(
        linked,
        kg,
        intent="variable",
        db_session=db_session,
        as_of=checkpoint,
    )

    node_ids = {node.node_id for node in result}
    assert {"el-1", "live", "canonical", "mixed"} <= node_ids
    assert "expired" not in node_ids
    assert "mixed-expired" not in node_ids

    traversal_call = kg.query.call_args_list[1]
    cypher = traversal_call.args[0]
    params = traversal_call.args[1]
    assert "rel.memory_id IS NULL" in cypher
    assert "rel.memory_id IN $valid_relation_memory_ids" in cypher
    assert set(params["valid_relation_memory_ids"]) == {"live-id"}
    assert params["relation_lifecycle_as_of"] == checkpoint.isoformat()


@pytest.mark.asyncio
async def test_ppr_current_lifecycle_uses_now_when_session_without_as_of(monkeypatch):
    """With a session and no as_of, traversal uses current-knowledge mode."""
    seen: dict[str, object] = {}

    async def fake_select_valid_memory_ids(session, as_of, *, namespace):
        seen["session"] = session
        seen["as_of"] = as_of
        seen["namespace"] = namespace
        return []

    monkeypatch.setattr(
        kg_module,
        "select_valid_memory_ids",
        fake_select_valid_memory_ids,
    )

    kg = AsyncMock()
    kg.query = AsyncMock(
        side_effect=[
            [{"id": "el-1", "labels": ["Variable"], "props": {"name": "v"}}],
            [
                {
                    "id": "canonical",
                    "labels": ["Paradigm"],
                    "props": {"name": "canonical"},
                    "hops": 1,
                    "rel_types": ["BELONGS_TO"],
                    "rel_memory_ids": [None],
                    "degree": 1,
                },
                {
                    "id": "backed",
                    "labels": ["Variable"],
                    "props": {"name": "backed"},
                    "hops": 1,
                    "rel_types": ["MEASURES"],
                    "rel_memory_ids": ["not-current"],
                    "degree": 1,
                },
            ],
        ]
    )
    db_session = MagicMock()

    result = await _ppr_traverse(
        [_LinkedEntity("el-1", "Variable", "v", 1.0)],
        kg,
        intent="variable",
        db_session=db_session,
    )

    assert seen["session"] is db_session
    assert seen["namespace"] == "kg_relation"
    assert isinstance(seen["as_of"], datetime)
    assert seen["as_of"].tzinfo is UTC
    node_ids = {node.node_id for node in result}
    assert "canonical" in node_ids
    assert "backed" not in node_ids
    assert (
        next(
            node for node in result if node.node_id == "canonical"
        ).relation_lifecycle_mode
        == "current"
    )


@pytest.mark.asyncio
async def test_ppr_without_db_preserves_legacy_unfiltered_paths():
    kg = AsyncMock()
    kg.query = AsyncMock(
        side_effect=[
            [{"id": "el-1", "labels": ["Variable"], "props": {"name": "v"}}],
            [
                {
                    "id": "backed",
                    "labels": ["Variable"],
                    "props": {"name": "backed"},
                    "hops": 1,
                    "rel_types": ["MEASURES"],
                    "rel_memory_ids": ["unknown-id"],
                    "degree": 1,
                },
            ],
        ]
    )

    result = await _ppr_traverse(
        [_LinkedEntity("el-1", "Variable", "v", 1.0)],
        kg,
        intent="variable",
    )

    assert {node.node_id for node in result} == {"el-1", "backed"}
    assert kg.query.call_args_list[1].args[1]["valid_relation_memory_ids"] is None


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
    assert "MODULATES" in params["allowed_types"]
    assert "USES_VARIABLE" in params["allowed_types"]
    assert "HAS_PARAMETER" in params["allowed_types"]


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
    assert "MODULATES" in var
    assert "USES_VARIABLE" in var
    assert "HAS_PARAMETER" in var
    # The two intents should be distinct sets.
    assert set(para) != set(var)


def test_types_for_intent_unknown_intent_falls_back_to_paradigm():
    assert _types_for_intent("nonsense") == _types_for_intent("paradigm")
