"""Distinguish CRAG grader errors from genuine AMBIGUOUS verdicts (P2-004).

When the Haiku grader fails, the previous routing treated every passage
as AMBIGUOUS, which forced a DuckDuckGo web fallback on every retrieve.
During Haiku outages this turned every retrieve into a 2-network-hop
slow path. The grader-unavailable branch returns the reranked results
unchanged with action="grader_unavailable" and zero web calls so the
caller doesn't burn a DuckDuckGo budget on every retrieve while Haiku
is rate-limited.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.retrieval import crag
from decisionlab.knowledge.retrieval import tool as tool_module
from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge
from decisionlab.runtime import usage as usage_module

_TOOL_MODULE = "decisionlab.knowledge.retrieval.tool"


def _r(text: str, score: float = 0.3) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source="dense", metadata={})


@pytest.fixture(autouse=True)
def _isolate_counters():
    usage_module.reset()
    yield
    usage_module.reset()


# ---------------------------------------------------------------------------
# AC1: evaluate_results short-circuits on grader error
# ---------------------------------------------------------------------------


class TestAC1_GraderUnavailableShortCircuit:
    @pytest.mark.asyncio
    async def test_haiku_error_returns_grader_unavailable_with_no_web_calls(self):
        """Simulate the Haiku rate-limit path — _classify_results emits the
        fail-closed sentinel, evaluate_results must short-circuit before
        any web call."""
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(
            side_effect=RuntimeError("haiku rate limit")
        )
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])
        embeddings = AsyncMock()
        embeddings.rerank = AsyncMock(return_value=[])

        results = [_r("a"), _r("b")]
        out = await crag.evaluate_results(
            query="probe",
            task_context="ctx",
            results=results,
            client=fake_client,
            search_adapter=search,
            embedding_service=embeddings,
        )

        assert out.action == "grader_unavailable"
        assert out.web_results_used == 0
        assert out.results == results
        assert out.grading_failed is True
        # No DuckDuckGo invocation under any code path.
        search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_unparseable_response_returns_grader_unavailable(self):
        """A Haiku response with no valid evaluations is the same fail-closed
        sentinel — short-circuit instead of supplementing."""

        async def _bad(**_):
            block = MagicMock()
            block.type = "text"
            block.text = "garbage not json"
            resp = MagicMock()
            resp.content = [block]
            resp.stop_reason = "end_turn"
            resp.usage = None
            return resp

        fake_client = MagicMock()
        fake_client.messages.create = _bad
        search = AsyncMock()
        search.search = AsyncMock(return_value=[])

        out = await crag.evaluate_results(
            query="probe",
            task_context="ctx",
            results=[_r("only doc")],
            client=fake_client,
            search_adapter=search,
            embedding_service=AsyncMock(),
        )

        assert out.action == "grader_unavailable"
        assert out.web_results_used == 0
        search.search.assert_not_called()


# ---------------------------------------------------------------------------
# AC2: tool.py output marker
# ---------------------------------------------------------------------------


class TestAC2_OutputMarker:
    def test_format_output_renders_marker_when_grader_unavailable(self):
        out = tool_module._format_output(
            [_r("hello")],
            top_k=5,
            grader_unavailable=True,
        )
        assert "[grader_unavailable]" in out

    def test_format_output_no_marker_for_normal_path(self):
        out = tool_module._format_output([_r("hello")], top_k=5)
        assert "[grader_unavailable]" not in out

    def test_empty_results_still_carry_marker(self):
        out = tool_module._format_output([], top_k=5, grader_unavailable=True)
        assert "[grader_unavailable]" in out


# ---------------------------------------------------------------------------
# AC3: telemetry counter
# ---------------------------------------------------------------------------


class TestAC3_Telemetry:
    @pytest.mark.asyncio
    async def test_grader_failed_increments_counter(self):
        """End-to-end through handle_retrieve_knowledge: low rerank score
        forces the evaluate branch, simulated grader error must
        increment crag.grader_failed."""
        from decisionlab.knowledge.retrieval.models import CRAGResult

        fused = [_r("a", 0.1)]  # below crag_skip_threshold so evaluate runs
        unavailable = CRAGResult(
            results=fused,
            action="grader_unavailable",
            evaluations=[
                {
                    "index": 0,
                    "classification": "AMBIGUOUS",
                    "reasoning": "Default (evaluation failed)",
                }
            ],
            web_results_used=0,
            grading_failed=True,
        )

        with (
            patch(f"{_TOOL_MODULE}.kg_retrieve", new_callable=AsyncMock) as mock_kg,
            patch(f"{_TOOL_MODULE}.vector_retrieve", new_callable=AsyncMock) as mock_v,
            patch(f"{_TOOL_MODULE}.fuse_and_rerank", new_callable=AsyncMock) as mock_f,
            patch(
                f"{_TOOL_MODULE}.evaluate_results", new_callable=AsyncMock
            ) as mock_crag,
        ):
            mock_kg.return_value = []
            mock_v.return_value = ([], [])
            mock_f.return_value = fused
            mock_crag.return_value = unavailable

            handler = create_retrieve_knowledge(
                kg=MagicMock(),
                vector_store=MagicMock(),
                embedding_service=MagicMock(),
                search_adapter=MagicMock(),
                client=AsyncMock(),
                run_id="run-test",
                stage="researcher",
            )
            response = await handler({"query": "anything"})

        snap = usage_module.counters_snapshot()
        assert snap.get("crag.grader_failed", 0) == 1
        assert "[grader_unavailable]" in response

    @pytest.mark.asyncio
    async def test_normal_evaluate_does_not_increment_grader_failed(self):
        from decisionlab.knowledge.retrieval.models import CRAGResult

        fused = [_r("a", 0.1)]
        ok = CRAGResult(
            results=fused,
            action="pass_through",
            evaluations=[],
            web_results_used=0,
            grading_failed=False,
        )

        with (
            patch(f"{_TOOL_MODULE}.kg_retrieve", new_callable=AsyncMock) as mock_kg,
            patch(f"{_TOOL_MODULE}.vector_retrieve", new_callable=AsyncMock) as mock_v,
            patch(f"{_TOOL_MODULE}.fuse_and_rerank", new_callable=AsyncMock) as mock_f,
            patch(
                f"{_TOOL_MODULE}.evaluate_results", new_callable=AsyncMock
            ) as mock_crag,
        ):
            mock_kg.return_value = []
            mock_v.return_value = ([], [])
            mock_f.return_value = fused
            mock_crag.return_value = ok

            handler = create_retrieve_knowledge(
                kg=MagicMock(),
                vector_store=MagicMock(),
                embedding_service=MagicMock(),
                search_adapter=MagicMock(),
                client=AsyncMock(),
                run_id="run-test",
                stage="researcher",
            )
            response = await handler({"query": "anything"})

        snap = usage_module.counters_snapshot()
        assert snap.get("crag.grader_failed", 0) == 0
        assert "[grader_unavailable]" not in response
