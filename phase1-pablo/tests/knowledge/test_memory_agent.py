"""Tests for the MemoryAgent orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.models import (
    ExtractionResult,
    IndexResult,
    KGWriteResult,
    MemoryAgentResult,
    NodeSpec,
    RelationSpec,
    ResolutionResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_extraction(stage: str = "researcher", n_nodes: int = 3) -> ExtractionResult:
    return ExtractionResult(
        nodes=[
            NodeSpec(label="Paradigm", properties={"slug": "test"}, natural_key="slug")
        ]
        * n_nodes,
        relations=[
            RelationSpec(
                from_label="Paradigm",
                from_key_value="test",
                to_label="Variable",
                to_key_value="energy",
                rel_type="BELONGS_TO",
            )
        ],
        facts=["fact one", "fact two"],
        stage=stage,
        run_id="run-1",
    )


def _make_kg_result(created: int = 2, merged: int = 1) -> KGWriteResult:
    return KGWriteResult(
        nodes_created=created,
        nodes_merged=merged,
        relations_created=1,
        relations_superseded=0,
    )


def _make_index_result() -> IndexResult:
    return IndexResult(artifacts_indexed=5, facts_indexed=2, total_chunks=7)


def _make_resolution_result(
    created: int = 2, skipped: int = 0, conflicts: int = 0
) -> ResolutionResult:
    return ResolutionResult(
        memories_created=created,
        duplicates_skipped=skipped,
        corroborations=0,
        enrichments=0,
        contradictions=conflicts,
        sonnet_calls=0,
    )


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def mock_kg():
    return MagicMock()


@pytest.fixture
def mock_vectors():
    return MagicMock()


@pytest.fixture
def mock_embeddings():
    return MagicMock()


@pytest.fixture
def mock_db():
    """DatabaseService mock with get_session async context manager."""
    db = MagicMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    async def _get_session():
        yield session

    # Make it work as async context manager
    from contextlib import asynccontextmanager

    db.get_session = asynccontextmanager(_get_session)
    return db


@pytest.fixture
def mock_emit():
    return AsyncMock()


# ---------------------------------------------------------------------------
# Patch targets (all in the memory_agent module namespace)
# ---------------------------------------------------------------------------

_PATCH_BASE = "decisionlab.agents.memory_agent"


def _patch_extract(extraction):
    return patch(
        f"{_PATCH_BASE}.extract", new_callable=AsyncMock, return_value=extraction
    )


def _patch_populate_kg(result):
    return patch(
        f"{_PATCH_BASE}.populate_kg", new_callable=AsyncMock, return_value=result
    )


def _patch_index(result):
    return patch(
        f"{_PATCH_BASE}.index_stage_output",
        new_callable=AsyncMock,
        return_value=result,
    )


def _patch_resolve(result):
    return patch(
        f"{_PATCH_BASE}.resolve_and_store",
        new_callable=AsyncMock,
        return_value=result,
    )


def _patch_canonicalize(result=None):
    """Patch canonicalize so it returns the same extraction it received.

    When ``result`` is None the side effect echoes its first argument back —
    matching the canonicalize contract. Pass a concrete extraction to override.
    """

    async def _echo(extraction, **_kwargs):
        return extraction if result is None else result

    return patch(
        f"{_PATCH_BASE}.canonicalize", new_callable=AsyncMock, side_effect=_echo
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_calls_all_subsystems(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db, mock_emit
):
    """AC1/AC2: A full run calls extract, KG, index, and resolve."""
    from decisionlab.agents.memory_agent import MemoryAgent

    extraction = _make_extraction()
    kg_result = _make_kg_result()
    idx_result = _make_index_result()
    res_result = _make_resolution_result()

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        _patch_extract(extraction) as m_extract,
        _patch_populate_kg(kg_result) as m_kg,
        _patch_index(idx_result) as m_idx,
        _patch_resolve(res_result) as m_resolve,
    ):
        result = await agent.run(
            "researcher", "some output text", "run-1", emit=mock_emit
        )

    m_extract.assert_awaited_once()
    m_kg.assert_awaited_once()
    m_idx.assert_awaited_once()
    m_resolve.assert_awaited_once()

    assert isinstance(result, MemoryAgentResult)
    assert result.nodes_created == 2
    assert result.nodes_merged == 1
    assert result.relations_created == 1
    assert result.facts_stored == 2
    assert result.duplicates_skipped == 0
    assert result.conflicts_resolved == 0
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_run_emits_status_messages(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db, mock_emit
):
    """AC3: WebSocket clients receive working/done status messages."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()),
    ):
        await agent.run("researcher", "text", "run-1", emit=mock_emit)

    calls = [c.args[0] for c in mock_emit.call_args_list]
    assert any(
        m.get("type") == "agent_status" and m.get("status") == "working" for m in calls
    )
    assert any(
        m.get("type") == "agent_status" and m.get("status") == "done" for m in calls
    )


@pytest.mark.asyncio
async def test_skips_kg_when_none(mock_client, mock_vectors, mock_embeddings, mock_db):
    """AC4 partial: KG population skipped when kg=None, but extraction and indexing still run."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=None,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        _patch_extract(_make_extraction()) as m_extract,
        _patch_populate_kg(_make_kg_result()) as m_kg,
        _patch_index(_make_index_result()) as m_idx,
        _patch_resolve(_make_resolution_result()) as m_resolve,
    ):
        result = await agent.run("researcher", "text", "run-1")

    m_extract.assert_awaited_once()
    m_kg.assert_not_awaited()
    m_idx.assert_awaited_once()
    m_resolve.assert_awaited_once()
    assert result.nodes_created == 0
    assert result.nodes_merged == 0


@pytest.mark.asyncio
async def test_skips_indexing_when_vectors_none(mock_client, mock_kg, mock_db):
    """AC4 partial: Indexing skipped when vector_store or embedding_service is None."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=None,
        embedding_service=None,
        db=mock_db,
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()) as m_idx,
        _patch_resolve(_make_resolution_result()) as m_resolve,
    ):
        result = await agent.run("researcher", "text", "run-1")

    m_idx.assert_not_awaited()
    # resolve also requires vector_store and embedding_service
    m_resolve.assert_not_awaited()
    assert result.facts_stored == 0


@pytest.mark.asyncio
async def test_skips_resolve_when_db_none(
    mock_client, mock_kg, mock_vectors, mock_embeddings
):
    """AC4 partial: Resolution skipped when db=None."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=None,
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()) as m_resolve,
    ):
        result = await agent.run("researcher", "text", "run-1")

    m_resolve.assert_not_awaited()
    assert result.facts_stored == 0


@pytest.mark.asyncio
async def test_run_no_emit_callback(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC3: Runs without error when emit is None (CLI mode)."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()),
    ):
        result = await agent.run("researcher", "text", "run-1", emit=None)

    assert isinstance(result, MemoryAgentResult)


@pytest.mark.asyncio
async def test_extract_failure_returns_empty_result(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC5: If extraction raises, MemoryAgent returns zeroed result, doesn't crash."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        patch(
            f"{_PATCH_BASE}.extract",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ),
        _patch_populate_kg(_make_kg_result()) as m_kg,
        _patch_index(_make_index_result()) as m_idx,
        _patch_resolve(_make_resolution_result()) as m_resolve,
    ):
        result = await agent.run("researcher", "text", "run-1")

    # Should not proceed to downstream steps
    m_kg.assert_not_awaited()
    m_idx.assert_not_awaited()
    m_resolve.assert_not_awaited()
    assert result.nodes_created == 0
    assert result.facts_stored == 0


@pytest.mark.asyncio
async def test_kg_failure_does_not_block_indexing(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC5: If KG population fails, indexing still completes (parallel gather catches)."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    extraction = _make_extraction()
    with (
        _patch_extract(extraction),
        patch(
            f"{_PATCH_BASE}.populate_kg",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Neo4j down"),
        ),
        _patch_index(_make_index_result()) as m_idx,
        _patch_resolve(_make_resolution_result()),
    ):
        result = await agent.run("researcher", "text", "run-1")

    # Indexing should still have run
    m_idx.assert_awaited_once()
    # KG results should be zeroed
    assert result.nodes_created == 0
    assert result.nodes_merged == 0


@pytest.mark.asyncio
async def test_all_stages_supported(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """All four pipeline stages work."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    for stage in ("researcher", "formalizer", "reasoner", "builder"):
        with (
            _patch_extract(_make_extraction(stage=stage)),
            _patch_populate_kg(_make_kg_result()),
            _patch_index(_make_index_result()),
            _patch_resolve(_make_resolution_result()),
        ):
            result = await agent.run(stage, f"{stage} output", "run-1")
        assert isinstance(result, MemoryAgentResult)


@pytest.mark.asyncio
async def test_result_aggregates_correctly(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """MemoryAgentResult correctly aggregates from KG + resolution results."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    kg_result = KGWriteResult(
        nodes_created=5, nodes_merged=3, relations_created=2, relations_superseded=1
    )
    res_result = ResolutionResult(
        memories_created=4,
        duplicates_skipped=2,
        corroborations=1,
        enrichments=1,
        contradictions=3,
        sonnet_calls=2,
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(kg_result),
        _patch_index(_make_index_result()),
        _patch_resolve(res_result),
    ):
        result = await agent.run("researcher", "text", "run-1")

    assert result.nodes_created == 5
    assert result.nodes_merged == 3
    assert result.relations_created == 2
    assert result.facts_stored == 4
    assert result.duplicates_skipped == 2
    assert result.conflicts_resolved == 3


@pytest.mark.asyncio
async def test_resolve_failure_preserves_kg_results(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """If resolve_and_store raises, KG results are preserved and facts_stored is 0."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    kg_result = KGWriteResult(
        nodes_created=3, nodes_merged=1, relations_created=2, relations_superseded=0
    )

    with (
        _patch_extract(_make_extraction()),
        _patch_populate_kg(kg_result),
        _patch_index(_make_index_result()),
        patch(
            f"{_PATCH_BASE}.resolve_and_store",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Postgres down"),
        ),
    ):
        result = await agent.run("researcher", "text", "run-1")

    # KG results preserved
    assert result.nodes_created == 3
    assert result.nodes_merged == 1
    assert result.relations_created == 2
    # Resolution zeroed
    assert result.facts_stored == 0
    assert result.duplicates_skipped == 0
    assert result.conflicts_resolved == 0


@pytest.mark.asyncio
async def test_empty_stage_output_skips_all(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """Empty stage output returns zeroed result without calling extract."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with (
        _patch_extract(_make_extraction()) as m_extract,
        _patch_populate_kg(_make_kg_result()) as m_kg,
    ):
        result = await agent.run("researcher", "", "run-1")

    m_extract.assert_not_awaited()
    m_kg.assert_not_awaited()
    assert result.nodes_created == 0
    assert result.facts_stored == 0


@pytest.mark.asyncio
async def test_whitespace_only_stage_output_skips_all(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """Whitespace-only stage output is treated as empty."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    with _patch_extract(_make_extraction()) as m_extract:
        result = await agent.run("researcher", "   \n\t  ", "run-1")

    m_extract.assert_not_awaited()
    assert result.nodes_created == 0


# ---------------------------------------------------------------------------
# P1-003: conditional canonicalize gate (route only __NEW__ extractions through
# the verify-merge step; canonical-slug-only extractions skip it entirely).
# ---------------------------------------------------------------------------


def _extraction_with_slugs(*slugs: str) -> ExtractionResult:
    """Build an extraction whose Paradigm nodes carry the given slugs."""
    return ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"slug": slug, "name": slug, "description": ""},
                natural_key="slug",
            )
            for slug in slugs
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_canonicalize_skipped_when_no_new_slug(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC1: Fully-canonical extractions bypass canonicalize entirely."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    extraction = _extraction_with_slugs("reinforcement-learning", "prospect-theory")

    with (
        _patch_extract(extraction),
        _patch_canonicalize() as m_canon,
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()),
    ):
        await agent.run("researcher", "text", "run-1")

    assert m_canon.call_count == 0


@pytest.mark.asyncio
async def test_canonicalize_runs_when_new_slug_present(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC2: A single ``__NEW__`` slug routes the extraction through canonicalize."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    extraction = _extraction_with_slugs("reinforcement-learning", "__NEW__")

    with (
        _patch_extract(extraction),
        _patch_canonicalize() as m_canon,
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()),
    ):
        await agent.run("researcher", "text", "run-1")

    assert m_canon.call_count == 1


@pytest.mark.asyncio
async def test_canonicalize_skipped_when_only_non_canonicalize_labels(
    mock_client, mock_kg, mock_vectors, mock_embeddings, mock_db
):
    """AC1 corollary: a stray ``slug=__NEW__`` on an unrelated label does not trigger."""
    from decisionlab.agents.memory_agent import MemoryAgent

    agent = MemoryAgent(
        client=mock_client,
        kg=mock_kg,
        vector_store=mock_vectors,
        embedding_service=mock_embeddings,
        db=mock_db,
    )

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paper",
                properties={"slug": "__NEW__", "doi": "10.1/x"},
                natural_key="doi",
            )
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )

    with (
        _patch_extract(extraction),
        _patch_canonicalize() as m_canon,
        _patch_populate_kg(_make_kg_result()),
        _patch_index(_make_index_result()),
        _patch_resolve(_make_resolution_result()),
    ):
        await agent.run("researcher", "text", "run-1")

    assert m_canon.call_count == 0
