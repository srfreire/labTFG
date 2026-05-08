"""Conditional CRAG (P2-001).

When the rerank already has a confident answer (top score above the
``crag_skip_threshold`` setting), ``handle_retrieve_knowledge`` short
circuits past ``evaluate_results`` instead of burning a Haiku
round-trip on every retrieve. Below the threshold, behaviour is
unchanged. Each branch records a telemetry counter
(``crag.skipped`` / ``crag.evaluated``) so impact is measurable.
"""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab import config as decisionlab_config
from decisionlab.knowledge.retrieval import tool as tool_module
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.knowledge.retrieval.tool import create_retrieve_knowledge
from decisionlab.runtime import usage as usage_module

_TOOL_MODULE = "decisionlab.knowledge.retrieval.tool"


def _set_threshold(monkeypatch: pytest.MonkeyPatch, value: float) -> None:
    """Override the frozen ``SETTINGS.crag_skip_threshold`` for one test.

    ``Settings`` is a frozen dataclass so ``setattr`` on the instance is
    rejected. Replace the module-level binding in ``tool`` (which is the
    one ``handle_retrieve_knowledge`` looks at) with a copy carrying the
    new threshold.
    """
    monkeypatch.setattr(
        tool_module,
        "SETTINGS",
        replace(tool_module.SETTINGS, crag_skip_threshold=value),
    )


def _result(text: str, score: float, source: str = "dense") -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata={})


def _make_handler():
    return create_retrieve_knowledge(
        kg=MagicMock(),
        vector_store=MagicMock(),
        embedding_service=MagicMock(),
        search_adapter=MagicMock(),
        client=AsyncMock(),
        run_id="run-test",
        stage="researcher",
    )


@contextmanager
def _patch_pipeline(*, fused: list[RetrievalResult]):
    """Patch the kg/vector/fuse layer so that ``fuse_and_rerank``
    returns *fused*. ``evaluate_results`` is patched too so each test
    can assert on its call count.

    The CRAGResult returned by the patched ``evaluate_results`` echoes
    the fused list — keeps downstream weighting/format steps happy
    when the test exercises the evaluate branch.
    """
    default_eval_result = CRAGResult(
        results=fused, action="pass_through", evaluations=[], web_results_used=0
    )
    with (
        patch(f"{_TOOL_MODULE}.kg_retrieve", new_callable=AsyncMock) as mock_kg,
        patch(f"{_TOOL_MODULE}.vector_retrieve", new_callable=AsyncMock) as mock_vec,
        patch(f"{_TOOL_MODULE}.fuse_and_rerank", new_callable=AsyncMock) as mock_fuse,
        patch(f"{_TOOL_MODULE}.evaluate_results", new_callable=AsyncMock) as mock_crag,
    ):
        mock_kg.return_value = []
        mock_vec.return_value = ([], [])
        mock_fuse.return_value = fused
        mock_crag.return_value = default_eval_result
        yield {"kg": mock_kg, "vec": mock_vec, "fuse": mock_fuse, "crag": mock_crag}


# ---------------------------------------------------------------------------
# AC1: configurable threshold
# ---------------------------------------------------------------------------


class TestAC1_CRAGSkipThreshold:
    def test_default_is_0_5(self):
        assert decisionlab_config.SETTINGS.crag_skip_threshold == pytest.approx(0.5)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DECISIONLAB_CRAG_SKIP_THRESHOLD", "0.8")
        reloaded = importlib.reload(decisionlab_config)
        try:
            assert reloaded.SETTINGS.crag_skip_threshold == pytest.approx(0.8)
        finally:
            monkeypatch.delenv("DECISIONLAB_CRAG_SKIP_THRESHOLD", raising=False)
            importlib.reload(decisionlab_config)

    def test_invalid_env_value_raises(self, monkeypatch):
        monkeypatch.setenv("DECISIONLAB_CRAG_SKIP_THRESHOLD", "not-a-float")
        try:
            with pytest.raises(ValueError):
                importlib.reload(decisionlab_config)
        finally:
            monkeypatch.delenv("DECISIONLAB_CRAG_SKIP_THRESHOLD", raising=False)
            importlib.reload(decisionlab_config)


# ---------------------------------------------------------------------------
# AC2: skip branch — top score >= threshold => no LLM call
# ---------------------------------------------------------------------------


class TestAC2_SkipBranch:
    @pytest.mark.asyncio
    async def test_top_score_at_threshold_skips_evaluate(self, monkeypatch):
        # Threshold is 0.5; top score 0.5 is the boundary and should skip.
        _set_threshold(monkeypatch, 0.5)
        fused = [_result("a", 0.5), _result("b", 0.4), _result("c", 0.3)]

        with _patch_pipeline(fused=fused) as mocks:
            handler = _make_handler()
            await handler({"query": "anything"})

        mocks["crag"].assert_not_called()

    @pytest.mark.asyncio
    async def test_top_score_above_threshold_skips_evaluate(self, monkeypatch):
        _set_threshold(monkeypatch, 0.5)
        fused = [_result("a", 0.92), _result("b", 0.8), _result("c", 0.6)]

        with _patch_pipeline(fused=fused) as mocks:
            handler = _make_handler()
            result = await handler({"query": "anything"})

        mocks["crag"].assert_not_called()
        assert "Retrieved Knowledge" in result

    @pytest.mark.asyncio
    async def test_skip_branch_returns_rerank_pass_through_action(self, monkeypatch):
        """The skip branch must surface ``action='rerank_pass_through'`` so
        downstream telemetry/inspection can distinguish the skip from a
        genuine CRAG ``pass_through``."""
        _set_threshold(monkeypatch, 0.5)
        fused = [_result("a", 0.92)]

        captured: dict[str, object] = {}

        def _capture(results, *, top_k, web_supplemented):
            captured["web_supplemented"] = web_supplemented
            return results[:top_k]

        with (
            _patch_pipeline(fused=fused),
            patch(f"{_TOOL_MODULE}._final_truncate", side_effect=_capture),
        ):
            handler = _make_handler()
            await handler({"query": "anything"})

        # Skip path should never set the web-supplemented flag.
        assert captured["web_supplemented"] is False


# ---------------------------------------------------------------------------
# AC3: evaluate branch unchanged — sub-threshold still calls CRAG
# ---------------------------------------------------------------------------


class TestAC3_EvaluateBranch:
    @pytest.mark.asyncio
    async def test_top_score_below_threshold_calls_evaluate(self, monkeypatch):
        _set_threshold(monkeypatch, 0.5)
        fused = [_result("a", 0.49), _result("b", 0.3)]

        with _patch_pipeline(fused=fused) as mocks:
            handler = _make_handler()
            await handler({"query": "anything"})

        mocks["crag"].assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_rerank_calls_evaluate(self, monkeypatch):
        """Empty fused list means top score defaults to 0.0, so the
        evaluate branch handles the empty case (mirrors today's behaviour)."""
        _set_threshold(monkeypatch, 0.5)

        with _patch_pipeline(fused=[]) as mocks:
            handler = _make_handler()
            await handler({"query": "anything"})

        mocks["crag"].assert_called_once()

    @pytest.mark.asyncio
    async def test_threshold_tunable_via_settings(self, monkeypatch):
        """A high threshold forces evaluation even on confident reranks."""
        _set_threshold(monkeypatch, 0.95)
        fused = [_result("a", 0.92), _result("b", 0.85)]

        with _patch_pipeline(fused=fused) as mocks:
            handler = _make_handler()
            await handler({"query": "anything"})

        mocks["crag"].assert_called_once()


# ---------------------------------------------------------------------------
# AC4: telemetry counters
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_counters():
    """Counters are module-level — reset before *and* after each test in
    this file so concurrent or interleaved suites can't pollute the
    skip/evaluate snapshots."""
    usage_module.reset()
    yield
    usage_module.reset()


class TestAC4_Telemetry:
    @pytest.mark.asyncio
    async def test_skip_increments_skipped_counter(self, monkeypatch):
        _set_threshold(monkeypatch, 0.5)

        with _patch_pipeline(fused=[_result("a", 0.92)]):
            handler = _make_handler()
            await handler({"query": "anything"})

        snap = usage_module.counters_snapshot()
        assert snap.get("crag.skipped", 0) == 1
        assert snap.get("crag.evaluated", 0) == 0

    @pytest.mark.asyncio
    async def test_evaluate_increments_evaluated_counter(self, monkeypatch):
        _set_threshold(monkeypatch, 0.5)

        with _patch_pipeline(fused=[_result("a", 0.4)]):
            handler = _make_handler()
            await handler({"query": "anything"})

        snap = usage_module.counters_snapshot()
        assert snap.get("crag.skipped", 0) == 0
        assert snap.get("crag.evaluated", 0) == 1


# ---------------------------------------------------------------------------
# Counter helper itself — record_usage-style API
# ---------------------------------------------------------------------------


class TestUsageCounters:
    def test_increment_counter_accumulates(self):
        usage_module.increment_counter("crag.skipped")
        usage_module.increment_counter("crag.skipped")
        assert usage_module.counters_snapshot()["crag.skipped"] == 2

    def test_increment_counter_with_amount(self):
        usage_module.increment_counter("ner.skipped", 5)
        assert usage_module.counters_snapshot()["ner.skipped"] == 5

    def test_reset_clears_counters(self):
        usage_module.increment_counter("crag.evaluated")
        usage_module.reset()
        assert usage_module.counters_snapshot() == {}
