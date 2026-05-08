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
    )


_TOOL_MODULE = "decisionlab.knowledge.retrieval.tool"


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


def _mock_db_with_session(session: object) -> object:
    db = MagicMock()
    db.get_session = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return db


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
            patch(f"{_TOOL_MODULE}.shared") as mock_shared,
        ):
            mock_shared.db = mock_db
            handler = _make_handler()
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
    async def test_track_memory_access_issues_one_execute_and_one_commit(self):
        """AC1: regardless of batch size, one execute + one commit on the session."""
        from decisionlab.knowledge.retrieval.tool import _track_memory_access

        mem_results = [_memory_result(str(uuid.uuid4())) for _ in range(5)]
        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with patch(f"{_TOOL_MODULE}.shared") as mock_shared:
            mock_shared.db = mock_db
            await _track_memory_access(mem_results)

        assert mock_session.execute.await_count == 1
        assert mock_session.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_track_memory_access_logs_batch_size(self, caplog):
        """AC4: emits `touch_memory.batch_size=N` telemetry log."""
        import logging

        from decisionlab.knowledge.retrieval.tool import _track_memory_access

        mem_results = [_memory_result(str(uuid.uuid4())) for _ in range(3)]
        mock_session = AsyncMock()
        mock_db = _mock_db_with_session(mock_session)

        with (
            patch(f"{_TOOL_MODULE}.shared") as mock_shared,
            caplog.at_level(logging.INFO, logger=_TOOL_MODULE),
        ):
            mock_shared.db = mock_db
            await _track_memory_access(mem_results)

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

        with patch(f"{_TOOL_MODULE}.shared") as mock_shared:
            mock_shared.db = mock_db
            await _track_memory_access(web_only)

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()


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
        """The stage parameter should generate an appropriate task_context for CRAG."""
        fused = [_result("test", 0.9, "dense")]
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
            usage_module.reset()
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
            usage_module.reset()
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
            usage_module.reset()
            handler = _make_handler()
            await handler({"query": "no dense hits"})

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
