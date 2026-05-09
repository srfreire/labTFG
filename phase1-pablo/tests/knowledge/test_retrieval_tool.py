"""Tests for the unified retrieve_knowledge tool (P3-005 + P5-001)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    create_retrieve_knowledge,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_RUN_ID = "run-abc123"
_STAGE = "researcher"
_SENTINEL = object()


def _result(text: str, score: float, source: str, **meta: object) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata=dict(meta))


def _make_handler(
    *,
    kg: object | None = _SENTINEL,
    vector_store: object | None = _SENTINEL,
    embedding_service: object | None = _SENTINEL,
    search_adapter: object | None = _SENTINEL,
    client: object | None = _SENTINEL,
    run_id: str = _RUN_ID,
    stage: str = _STAGE,
    db: object | None = _SENTINEL,
):
    return create_retrieve_knowledge(
        kg=MagicMock() if kg is _SENTINEL else kg,
        vector_store=MagicMock() if vector_store is _SENTINEL else vector_store,
        embedding_service=MagicMock()
        if embedding_service is _SENTINEL
        else embedding_service,
        search_adapter=MagicMock() if search_adapter is _SENTINEL else search_adapter,
        client=AsyncMock() if client is _SENTINEL else client,
        run_id=run_id,
        stage=stage,
        db=MagicMock() if db is _SENTINEL else db,
    )


_TOOL_MODULE = "decisionlab.knowledge.retrieval.tool"


@pytest.fixture(autouse=True)
def _reset_usage_counters():
    """Drop the runtime counter singleton between tests so per-test
    assertions on `ner.skipped` / `ner.evaluated` don't pick up state
    from earlier tests in the same process."""
    from decisionlab.runtime import usage as usage_module

    usage_module.reset()
    yield
    usage_module.reset()


@contextmanager
def _patch_pipeline(*, crag_result=None, fused=None):
    """Patch all four retrieval pipeline functions with sensible defaults.

    Yields a dict of mocks keyed by short name: kg, vec, fuse, crag.
    """
    default_crag = crag_result or CRAGResult(results=[], action="pass_through")
    with (
        patch(f"{_TOOL_MODULE}.kg_retrieve", new_callable=AsyncMock) as mock_kg,
        patch(f"{_TOOL_MODULE}.vector_retrieve", new_callable=AsyncMock) as mock_vec,
        patch(f"{_TOOL_MODULE}.fuse_and_rerank", new_callable=AsyncMock) as mock_fuse,
        patch(f"{_TOOL_MODULE}.evaluate_results", new_callable=AsyncMock) as mock_crag,
    ):
        mock_kg.return_value = []
        mock_vec.return_value = ([], [])
        mock_fuse.return_value = fused or default_crag.results
        mock_crag.return_value = default_crag
        yield {"kg": mock_kg, "vec": mock_vec, "fuse": mock_fuse, "crag": mock_crag}


def _mock_db_with_session(session: object) -> object:
    db = MagicMock()
    db.get_session = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return db


# ---------------------------------------------------------------------------
# AC1: Valid Anthropic tool definition
# ---------------------------------------------------------------------------


class TestAC1_ToolSchema:
    def test_schema_has_required_keys(self):
        assert "name" in RETRIEVE_KNOWLEDGE_SCHEMA
        assert "description" in RETRIEVE_KNOWLEDGE_SCHEMA
        assert "input_schema" in RETRIEVE_KNOWLEDGE_SCHEMA

    def test_schema_name(self):
        assert RETRIEVE_KNOWLEDGE_SCHEMA["name"] == "retrieve_knowledge"

    def test_input_schema_is_object(self):
        schema = RETRIEVE_KNOWLEDGE_SCHEMA["input_schema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_namespace_enum(self):
        ns = RETRIEVE_KNOWLEDGE_SCHEMA["input_schema"]["properties"]["namespace"]
        assert "enum" in ns
        assert set(ns["enum"]) == {
            "paradigm",
            "formulation",
            "model",
            "simulation",
            "meta",
        }

    def test_top_k_property(self):
        tk = RETRIEVE_KNOWLEDGE_SCHEMA["input_schema"]["properties"]["top_k"]
        assert tk["type"] == "integer"


# ---------------------------------------------------------------------------
# AC2: Formatted results with source attributions
# ---------------------------------------------------------------------------


class TestAC2_FormattedResults:
    @pytest.mark.asyncio
    async def test_returns_formatted_text_with_sources(self):
        crag = CRAGResult(
            results=[
                _result(
                    "Q-learning converges under certain conditions.",
                    0.92,
                    "kg",
                    paper_title="Watkins 1992",
                    source_stage="researcher",
                    run_id="old-run",
                ),
                _result(
                    "Dense retrieval passage about RL.",
                    0.87,
                    "dense",
                    namespace="formulation",
                    source_stage="formalizer",
                    run_id="old-run-2",
                ),
            ],
            action="pass_through",
            evaluations=[],
            web_results_used=0,
        )

        with _patch_pipeline(crag_result=crag):
            handler = _make_handler()
            result = await handler({"query": "Q-learning convergence"})

        assert "Retrieved Knowledge" in result
        assert "Result 1" in result
        assert "Result 2" in result
        assert "Q-learning converges" in result
        assert "kg" in result
        assert "0.92" in result


# ---------------------------------------------------------------------------
# AC3: Namespace filtering
# ---------------------------------------------------------------------------


class TestAC3_NamespaceFilter:
    @pytest.mark.asyncio
    async def test_namespace_passed_to_vector_retrieve(self):
        with _patch_pipeline() as mocks:
            handler = _make_handler()
            await handler({"query": "test", "namespace": "paradigm"})

        filters = mocks["vec"].call_args.kwargs.get("filters")
        assert filters is not None
        assert filters.get("namespace") == "paradigm"


# ---------------------------------------------------------------------------
# AC4: Self-retrieval prevention
# ---------------------------------------------------------------------------


class TestAC4_SelfRetrieval:
    @pytest.mark.asyncio
    async def test_exclude_run_id_in_filters(self):
        with _patch_pipeline() as mocks:
            handler = _make_handler(run_id="my-run-id")
            await handler({"query": "test"})

        filters = mocks["vec"].call_args.kwargs.get("filters")
        assert filters is not None
        assert filters.get("exclude_run_id") == "my-run-id"


# ---------------------------------------------------------------------------
# AC5: Graceful degradation when infrastructure unavailable
# ---------------------------------------------------------------------------


class TestAC5_GracefulDegradation:
    @pytest.mark.asyncio
    async def test_all_none_returns_graceful_message(self):
        handler = _make_handler(
            kg=None,
            vector_store=None,
            embedding_service=None,
            search_adapter=None,
        )
        result = await handler({"query": "anything"})
        assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_partial_infra_still_works(self):
        """When only vector_store is available but kg is None, pipeline still runs."""
        with _patch_pipeline():
            handler = _make_handler(kg=None)
            result = await handler({"query": "test"})

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# AC6: top_k limits results
# ---------------------------------------------------------------------------


class TestAC6_TopK:
    @pytest.mark.asyncio
    async def test_top_k_limits_output(self):
        many_results = [
            _result(f"Result {i}", 0.9 - i * 0.05, "dense") for i in range(10)
        ]
        crag = CRAGResult(
            results=many_results,
            action="pass_through",
            evaluations=[],
            web_results_used=0,
        )

        with _patch_pipeline(crag_result=crag):
            handler = _make_handler()
            result = await handler({"query": "test", "top_k": 3})

        assert "Result 1" in result
        assert "Result 2" in result
        assert "Result 3" in result
        assert "Result 4" not in result


# ---------------------------------------------------------------------------
# AC7: Memory access tracking
# ---------------------------------------------------------------------------


def _memory_result(mem_id: str) -> RetrievalResult:
    return _result(
        "A memory passage.",
        0.9,
        "dense",
        entity_id=mem_id,
        collection="memories_dense",
    )


class TestAC7_MemoryAccessTracking:
    @pytest.mark.asyncio
    async def test_touch_memory_called_with_batched_ids(self):
        """All memory-backed results funnel into one batched touch_memory call."""
        mem_id_1, mem_id_2 = str(uuid.uuid4()), str(uuid.uuid4())
        memory_results = [_memory_result(mem_id_1), _memory_result(mem_id_2)]
        crag = CRAGResult(
            results=memory_results,
            action="pass_through",
            evaluations=[],
            web_results_used=0,
        )

        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with (
            _patch_pipeline(crag_result=crag, fused=memory_results),
            patch(f"{_TOOL_MODULE}.touch_memory", new_callable=AsyncMock) as mock_touch,
            patch(
                f"{_TOOL_MODULE}._fetch_confidences",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            handler = _make_handler(db=mock_db)
            await handler({"query": "test"})

        mock_touch.assert_called_once()
        # touch_memory(session, [id1, id2]) — verify list of UUIDs passed positionally
        passed_ids = mock_touch.call_args[0][1]
        assert list(passed_ids) == [uuid.UUID(mem_id_1), uuid.UUID(mem_id_2)]

    @pytest.mark.asyncio
    async def test_web_results_not_touched(self):
        """Web results (no entity_id) should NOT trigger touch_memory."""
        web_result = _result("Web passage.", 0.8, "web", url="https://example.com")
        crag = CRAGResult(
            results=[web_result],
            action="web_fallback",
            evaluations=[],
            web_results_used=1,
        )

        with (
            _patch_pipeline(crag_result=crag, fused=[web_result]),
            patch(f"{_TOOL_MODULE}.touch_memory", new_callable=AsyncMock) as mock_touch,
        ):
            handler = _make_handler()
            await handler({"query": "test"})

        mock_touch.assert_not_called()

    @pytest.mark.asyncio
    async def test_track_memory_access_one_batched_update_plus_one_commit(self):
        """AC1: one batched access-meta UPDATE + one commit on the session.

        After P3-001, per-id confidence boosts go through `update_memory_confidence`
        (patched out here). The session still issues exactly one batched UPDATE
        for `last_accessed_at` / `access_count` and one commit per call.
        """
        from decisionlab.knowledge.retrieval.tool import _track_memory_access
        from shared import pipeline_memories as shared_memories

        mem_results = [_memory_result(str(uuid.uuid4())) for _ in range(5)]
        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with patch.object(
            shared_memories,
            "update_memory_confidence",
            new_callable=AsyncMock,
        ):
            await _track_memory_access(mem_results, mock_db)

        assert mock_session.execute.await_count == 1
        assert mock_session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_track_memory_access_logs_batch_size(self, caplog):
        """AC4: emits `touch_memory.batch_size=N` telemetry log."""
        import logging

        from decisionlab.knowledge.retrieval.tool import _track_memory_access
        from shared import pipeline_memories as shared_memories

        mem_results = [_memory_result(str(uuid.uuid4())) for _ in range(3)]
        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with (
            patch.object(
                shared_memories,
                "update_memory_confidence",
                new_callable=AsyncMock,
            ),
            caplog.at_level(logging.INFO, logger=_TOOL_MODULE),
        ):
            await _track_memory_access(mem_results, mock_db)

        assert any(
            "touch_memory.batch_size=3" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_track_memory_access_skips_when_no_memory_ids(self):
        """No execute, no commit, no log when there are no memory-backed hits."""
        web_only = [_result("Web passage.", 0.8, "web", url="https://example.com")]
        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        from decisionlab.knowledge.retrieval.tool import _track_memory_access

        await _track_memory_access(web_only, mock_db)

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_track_memory_access_skips_simulation_results(self):
        """Phase 2 ``simulation_observations`` rows have no last_accessed_at —
        ``_track_memory_access`` must filter them out via ``source_kind``.
        """
        from decisionlab.knowledge.retrieval.tool import _track_memory_access

        pipeline_id = str(uuid.uuid4())
        sim_id = str(uuid.uuid4())
        results = [
            _result(
                "pipeline result", 0.9, "dense",
                entity_id=pipeline_id,
                collection="memories_dense",
                source_kind="pipeline",
            ),
            _result(
                "simulation result", 0.85, "dense",
                entity_id=sim_id,
                collection="memories_dense",
                source_kind="simulation",
            ),
        ]

        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with (
            patch(f"{_TOOL_MODULE}.touch_memory", new_callable=AsyncMock) as mock_touch,
            patch(f"{_TOOL_MODULE}.shared") as mock_shared,
        ):
            mock_shared.db = mock_db
            await _track_memory_access(results)

        mock_touch.assert_called_once()
        passed_ids = mock_touch.call_args[0][1]
        assert list(passed_ids) == [uuid.UUID(pipeline_id)], (
            "simulation result must not be touched"
        )


class TestSourceKindOf:
    """Direct unit tests for ``_source_kind_of`` payload classification."""

    @pytest.mark.parametrize(
        "metadata,expected",
        [
            ({"source_kind": "pipeline"}, "pipeline"),
            ({"source_kind": "simulation"}, "simulation"),
            # Legacy points without ``source_kind`` fall back to namespace.
            ({"namespace": "simulation"}, "simulation"),
            ({"namespace": "paradigm"}, "pipeline"),
            ({"namespace": "formulation"}, "pipeline"),
            ({"namespace": "model"}, "pipeline"),
            ({"namespace": "meta"}, "pipeline"),
            # No hints at all → default to pipeline (the older write path).
            ({}, "pipeline"),
            # Junk value in source_kind falls through to the namespace fallback.
            ({"source_kind": "garbage", "namespace": "simulation"}, "simulation"),
            ({"source_kind": "garbage", "namespace": "paradigm"}, "pipeline"),
        ],
    )
    def test_source_kind_of_classification(self, metadata, expected):
        from decisionlab.knowledge.retrieval.tool import _source_kind_of

        assert _source_kind_of(metadata) == expected


# ---------------------------------------------------------------------------
# P3-002 / AC2: confidence batch-fetched from PG inside _apply_recency_weighting
# ---------------------------------------------------------------------------


class TestP3_002_RecencyConfidenceFromPG:
    @pytest.mark.asyncio
    async def test_recency_weighting_issues_one_pg_select(self):
        """AC2: exactly one batched SELECT per retrieve when memory IDs present."""
        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        mem_id_1, mem_id_2 = uuid.uuid4(), uuid.uuid4()
        results = [
            _result(
                "memory hit 1",
                0.9,
                "dense",
                entity_id=str(mem_id_1),
                collection="memories_dense",
                namespace="paradigm",
            ),
            _result(
                "memory hit 2",
                0.8,
                "sparse",
                entity_id=str(mem_id_2),
                collection="memories_sparse",
                namespace="paradigm",
            ),
            _result(
                "non-memory hit",
                0.7,
                "web",
                url="https://example.com",
                namespace="paradigm",
            ),
        ]

        # Mock PG returns 0.5 / 0.4 for the two memory IDs.
        rows = [
            MagicMock(id=mem_id_1, confidence=0.5),
            MagicMock(id=mem_id_2, confidence=0.4),
        ]
        execute_result = MagicMock()
        execute_result.all.return_value = rows

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_db = _mock_db_with_session(mock_session)

        weighted = await _apply_recency_weighting(results, mock_db)

        assert mock_session.execute.await_count == 1

        by_text = {r.text: r for r in weighted}
        assert by_text["memory hit 1"].metadata["confidence_factor"] == 0.5
        assert by_text["memory hit 2"].metadata["confidence_factor"] == 0.4
        # Non-memory result (web fallback) has no PG row → factor stays 1.0.
        assert by_text["non-memory hit"].metadata["confidence_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_recency_weighting_skips_pg_when_no_memory_ids(self):
        """AC3 corollary: pure non-memory results → no PG round-trip."""
        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        results = [
            _result("web hit 1", 0.9, "web", url="https://example.com/1"),
            _result("web hit 2", 0.8, "web", url="https://example.com/2"),
        ]

        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        weighted = await _apply_recency_weighting(results, mock_db)

        mock_session.execute.assert_not_called()
        assert all(r.metadata["confidence_factor"] == 1.0 for r in weighted)

    @pytest.mark.asyncio
    async def test_recency_weighting_handles_missing_pg_row(self):
        """A memory id with no PG row (orphaned Qdrant point) keeps factor 1.0."""
        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        orphan_id = uuid.uuid4()
        results = [
            _result(
                "orphaned memory",
                0.6,
                "dense",
                entity_id=str(orphan_id),
                collection="memories_dense",
            ),
        ]

        execute_result = MagicMock()
        execute_result.all.return_value = []  # PG returns nothing

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_db = _mock_db_with_session(mock_session)

        weighted = await _apply_recency_weighting(results, mock_db)

        assert weighted[0].metadata["confidence_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_recency_weighting_ignores_qdrant_payload_confidence(self):
        """Stale `confidence` left in a Qdrant payload must NOT be honoured.

        Pre-P3-002 the per-result `r.metadata["confidence"]` lookup let
        drifted Qdrant values shape the score. Now PG is the only source.
        """
        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        mem_id = uuid.uuid4()
        results = [
            _result(
                "memory with stale payload confidence",
                0.9,
                "dense",
                entity_id=str(mem_id),
                collection="memories_dense",
                confidence=0.99,  # stale, should be ignored
            ),
        ]

        execute_result = MagicMock()
        execute_result.all.return_value = [MagicMock(id=mem_id, confidence=0.3)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=execute_result)
        mock_db = _mock_db_with_session(mock_session)

        weighted = await _apply_recency_weighting(results, mock_db)

        assert weighted[0].metadata["confidence_factor"] == 0.3

    @pytest.mark.asyncio
    async def test_recency_weighting_no_db_falls_back_to_one(self, caplog):
        """When db is None (degraded mode) use 1.0 + log warning.

        A misconfigured prod where init failed to wire the DB
        must not silently bypass scoring with no observable signal.
        """
        import logging

        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        results = [
            _result(
                "memory",
                0.9,
                "dense",
                entity_id=str(uuid.uuid4()),
                collection="memories_dense",
            ),
        ]

        with caplog.at_level(logging.WARNING, logger=_TOOL_MODULE):
            weighted = await _apply_recency_weighting(results, None)

        assert weighted[0].metadata["confidence_factor"] == 1.0
        assert any("db is None" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_recency_weighting_pg_error_falls_back_to_one(self, caplog):
        """A PG fetch error must degrade to factor=1.0, not abort retrieve."""
        import logging

        from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

        results = [
            _result(
                "memory",
                0.9,
                "dense",
                entity_id=str(uuid.uuid4()),
                collection="memories_dense",
            ),
        ]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
        mock_db = _mock_db_with_session(mock_session)

        with caplog.at_level(logging.WARNING, logger=_TOOL_MODULE):
            weighted = await _apply_recency_weighting(results, mock_db)

        assert weighted[0].metadata["confidence_factor"] == 1.0
        assert any("PG fetch failed" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# AC8: Dispatcher integration — handler accepts dict, returns str
# ---------------------------------------------------------------------------


class TestAC8_DispatcherIntegration:
    def test_factory_returns_callable(self):
        handler = _make_handler()
        assert callable(handler)

    @pytest.mark.asyncio
    async def test_handler_accepts_dict_returns_str(self):
        with _patch_pipeline():
            handler = _make_handler()
            result = await handler({"query": "test query"})

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_handler_raises_on_missing_query(self):
        handler = _make_handler()
        with pytest.raises(ValueError, match="query"):
            await handler({})


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_results_returns_no_results_message(self):
        with _patch_pipeline():
            handler = _make_handler()
            result = await handler({"query": "obscure topic"})

        assert "0 results" in result.lower() or "no results" in result.lower()

    @pytest.mark.asyncio
    async def test_stage_description_in_task_context(self):
        """The stage parameter should generate an appropriate task_context for CRAG.

        Uses a sub-threshold score so the conditional CRAG skip
        introduced in P2-001 does not bypass ``evaluate_results``
        before this test can inspect its arguments.
        """
        fused = [_result("test", 0.3, "dense")]
        crag = CRAGResult(results=fused, action="pass_through")

        with _patch_pipeline(crag_result=crag, fused=fused) as mocks:
            handler = _make_handler(stage="formalizer")
            await handler({"query": "test"})

        task_context = mocks["crag"].call_args[0][1]
        assert "formalizer" in task_context.lower()

    @pytest.mark.asyncio
    async def test_skips_kg_retrieve_when_dense_top1_above_threshold(self):
        """P2-002 / R2: dense top-1 ≥ ner_skip_threshold → kg_retrieve not invoked."""
        from decisionlab.runtime import usage as usage_module

        dense_hit = _result("Strong dense hit.", 0.92, "dense", namespace="paradigm")

        with _patch_pipeline() as mocks:
            mocks["vec"].return_value = ([dense_hit], [])
            handler = _make_handler()
            result = await handler({"query": "reward learning paradigms"})

        mocks["kg"].assert_not_called()
        assert isinstance(result, str)
        assert usage_module.counters_snapshot().get("ner.skipped") == 1
        assert "ner.evaluated" not in usage_module.counters_snapshot()

    @pytest.mark.asyncio
    async def test_runs_kg_retrieve_when_dense_top1_below_threshold(self):
        """P2-002 / R2: dense top-1 < threshold → kg_retrieve runs as today."""
        from decisionlab.runtime import usage as usage_module

        weak_hit = _result("Weak dense hit.", 0.3, "dense", namespace="paradigm")

        with _patch_pipeline() as mocks:
            mocks["vec"].return_value = ([weak_hit], [])
            handler = _make_handler()
            await handler({"query": "ambiguous query"})

        mocks["kg"].assert_called_once()
        assert usage_module.counters_snapshot().get("ner.evaluated") == 1
        assert "ner.skipped" not in usage_module.counters_snapshot()

    @pytest.mark.asyncio
    async def test_runs_kg_retrieve_when_dense_results_empty(self):
        """Empty dense channel → top-1 score is 0.0, well below threshold."""
        from decisionlab.runtime import usage as usage_module

        with _patch_pipeline() as mocks:
            mocks["vec"].return_value = ([], [])
            handler = _make_handler()
            await handler({"query": "no dense hits"})

        mocks["kg"].assert_called_once()
        assert usage_module.counters_snapshot().get("ner.evaluated") == 1

    @pytest.mark.asyncio
    async def test_records_unavailable_when_kg_missing(self):
        """KG unavailable → ner.unavailable counter fires (no skip / evaluate)."""
        from decisionlab.runtime import usage as usage_module

        with _patch_pipeline() as mocks:
            mocks["vec"].return_value = ([_result("hit", 0.9, "dense")], [])
            handler = _make_handler(kg=None)
            await handler({"query": "no kg"})

        mocks["kg"].assert_not_called()
        snapshot = usage_module.counters_snapshot()
        assert snapshot.get("ner.unavailable") == 1
        assert "ner.skipped" not in snapshot
        assert "ner.evaluated" not in snapshot

    @pytest.mark.asyncio
    async def test_skip_gate_uses_live_settings_threshold(self, monkeypatch):
        """AC1+AC2: patching SETTINGS.ner_skip_threshold actually moves the gate."""
        from decisionlab.knowledge.retrieval import tool as tool_module
        from decisionlab.runtime import usage as usage_module

        # Score 0.8 — above default 0.7 (would skip), but below the patched 0.95.
        dense_hit = _result("Mid-confidence hit.", 0.8, "dense")

        patched = type(tool_module.SETTINGS).__new__(type(tool_module.SETTINGS))
        for f, v in vars(tool_module.SETTINGS).items():
            object.__setattr__(patched, f, v)
        object.__setattr__(patched, "ner_skip_threshold", 0.95)
        monkeypatch.setattr(tool_module, "SETTINGS", patched)

        with _patch_pipeline() as mocks:
            mocks["vec"].return_value = ([dense_hit], [])
            handler = _make_handler()
            await handler({"query": "stricter threshold"})

        mocks["kg"].assert_called_once()
        assert usage_module.counters_snapshot().get("ner.evaluated") == 1

    def test_default_ner_skip_threshold(self):
        """AC1: ner_skip_threshold defaults to 0.7."""
        from decisionlab.config import SETTINGS

        assert SETTINGS.ner_skip_threshold == 0.7

    def test_ner_skip_threshold_env_override(self, monkeypatch):
        """AC1: DECISIONLAB_NER_SKIP_THRESHOLD env var overrides the default."""
        from decisionlab.config import Settings

        monkeypatch.setenv("DECISIONLAB_NER_SKIP_THRESHOLD", "0.85")
        loaded = Settings.from_env()
        assert loaded.ner_skip_threshold == 0.85

    @pytest.mark.asyncio
    async def test_web_result_formatted_with_source(self):
        """Web results should show source attribution differently."""
        web_result = _result(
            "Fresh web info about RL.",
            0.85,
            "web",
            url="https://arxiv.org/abs/1234",
            title="RL Survey",
        )
        crag = CRAGResult(
            results=[web_result],
            action="web_fallback",
            evaluations=[],
            web_results_used=1,
        )

        with _patch_pipeline(crag_result=crag, fused=[web_result]):
            handler = _make_handler()
            result = await handler({"query": "test"})

        assert "web" in result.lower()
        assert "Fresh web info" in result
