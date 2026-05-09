"""Tests for P5-001: Cross-run retrieval with recency weighting.

Tests the recency weighting function, run_id/run_date metadata in KG and
vector results, and cross-run retrieval filtering.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from decisionlab.knowledge.retrieval.kg_retrieval import (
    _collect_passages,
    _ScoredNode,
)
from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting
from decisionlab.knowledge.retrieval.vector_retrieval import _to_results
from shared.vector_store import ScoredPoint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso(days_ago: int = 0) -> str:
    """Return an ISO8601 UTC timestamp for N days ago."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _result(text: str, score: float, source: str, **meta) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata=dict(meta))


# ---------------------------------------------------------------------------
# AC1: Cross-run retrieval — run 3 returns results from runs 1, 2 but not 3
# ---------------------------------------------------------------------------


class TestAC1_CrossRunRetrieval:
    """AC1 — exclude_run_id semantics now sit inside the Qdrant filter
    (must_not). _to_results no longer drops points on the Python side;
    Qdrant has already excluded the current-run hits before _to_results
    sees them. Filter-shape coverage is in
    tests/knowledge/retrieval/test_exclude_run_id_filter.py.
    """

    def test_to_results_passes_through_all_qdrant_returned_points(self):
        """Whatever Qdrant returns, _to_results converts. No runtime
        run_id filtering happens here anymore."""
        points = [
            ScoredPoint("p1", 0.9, {"text_preview": "run-1 fact", "run_id": "run-1"}),
            ScoredPoint("p2", 0.85, {"text_preview": "run-2 fact", "run_id": "run-2"}),
        ]
        results = _to_results(points, "dense", "memories_dense")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# AC2: Recency weighting — yesterday scores higher than 30 days ago
# ---------------------------------------------------------------------------


class TestAC2_RecencyWeighting:
    async def test_recent_fact_scores_higher_than_old(self):
        """Same base score: yesterday's fact beats 30-day-old fact."""
        results = [
            _result("Same fact", 0.9, "dense", run_id="run-1", created_at=_utc_iso(30)),
            _result("Same fact", 0.9, "dense", run_id="run-2", created_at=_utc_iso(1)),
        ]

        weighted = await _apply_recency_weighting(results)

        run2 = next(r for r in weighted if r.metadata["run_id"] == "run-2")
        run1 = next(r for r in weighted if r.metadata["run_id"] == "run-1")
        assert run2.score > run1.score

    async def test_results_resorted_by_weighted_score(self):
        """After weighting, results are re-sorted by final score."""
        results = [
            _result("Old high score", 0.95, "dense", created_at=_utc_iso(365)),
            _result("New lower score", 0.85, "dense", created_at=_utc_iso(0)),
        ]

        weighted = await _apply_recency_weighting(results)

        # 0.85 * 1.0 = 0.85 vs 0.95 * 0.16 = 0.152 — new wins
        assert weighted[0].score > weighted[1].score
        assert weighted[0].text == "New lower score"


# ---------------------------------------------------------------------------
# AC3: Recency factor values match spec constants
# ---------------------------------------------------------------------------


class TestAC3_RecencyFactorValues:
    async def test_zero_day_factor_is_1(self):
        results = [_result("Today", 1.0, "dense", created_at=_utc_iso(0))]
        weighted = await _apply_recency_weighting(results)
        assert weighted[0].metadata["recency_factor"] == pytest.approx(1.0)

    async def test_30_day_factor_approx_086(self):
        results = [_result("30d old", 1.0, "dense", created_at=_utc_iso(30))]
        weighted = await _apply_recency_weighting(results)
        expected = 0.995**30  # ~0.8607
        assert weighted[0].metadata["recency_factor"] == pytest.approx(
            expected, rel=1e-3
        )

    async def test_365_day_factor_approx_016(self):
        results = [_result("365d old", 1.0, "dense", created_at=_utc_iso(365))]
        weighted = await _apply_recency_weighting(results)
        expected = 0.995**365  # ~0.1613
        assert weighted[0].metadata["recency_factor"] == pytest.approx(
            expected, rel=1e-2
        )

    async def test_final_score_is_original_times_recency(self):
        results = [_result("Test", 0.9, "dense", created_at=_utc_iso(30))]
        weighted = await _apply_recency_weighting(results)
        factor = 0.995**30
        assert weighted[0].score == pytest.approx(0.9 * factor, rel=1e-3)

    async def test_no_timestamp_gets_factor_1(self):
        results = [_result("Web result", 0.8, "web")]
        weighted = await _apply_recency_weighting(results)
        assert weighted[0].metadata["recency_factor"] == 1.0
        assert weighted[0].score == 0.8

    async def test_invalid_timestamp_gets_factor_1(self):
        results = [_result("Bad ts", 0.8, "dense", created_at="not-a-date")]
        weighted = await _apply_recency_weighting(results)
        assert weighted[0].metadata["recency_factor"] == 1.0

    async def test_naive_timestamp_treated_as_utc(self):
        naive = datetime.now().isoformat()
        results = [_result("Naive", 1.0, "dense", created_at=naive)]
        weighted = await _apply_recency_weighting(results)
        assert weighted[0].metadata["recency_factor"] == pytest.approx(1.0, abs=0.01)

    async def test_empty_results(self):
        assert await _apply_recency_weighting([]) == []


# ---------------------------------------------------------------------------
# AC4: Result metadata includes run_id and run_date for all results
# ---------------------------------------------------------------------------


class TestAC4_RunMetadataInResults:
    def test_vector_results_include_run_date(self):
        """Vector results have run_date derived from created_at."""
        ts = _utc_iso(5)
        points = [
            ScoredPoint(
                "p1",
                0.9,
                {
                    "text_preview": "fact",
                    "run_id": "run-1",
                    "created_at": ts,
                },
            ),
        ]

        results = _to_results(points, "dense", "memories_dense")

        assert results[0].metadata["run_id"] == "run-1"
        assert results[0].metadata["run_date"] == ts
        assert results[0].metadata["created_at"] == ts

    def test_vector_results_without_created_at_have_no_run_date(self):
        """If created_at is missing, run_date is not added."""
        points = [ScoredPoint("p1", 0.9, {"text_preview": "fact", "run_id": "run-1"})]
        results = _to_results(points, "dense", "memories_dense")
        assert "run_date" not in results[0].metadata

    async def test_recency_preserves_all_existing_metadata(self):
        meta = {
            "run_id": "run-1",
            "created_at": _utc_iso(0),
            "namespace": "paradigm",
            "source_stage": "researcher",
        }
        results = [RetrievalResult(text="T", score=0.9, source="dense", metadata=meta)]
        weighted = await _apply_recency_weighting(results)
        for key in ("run_id", "namespace", "source_stage"):
            assert key in weighted[0].metadata
        assert "recency_factor" in weighted[0].metadata


# ---------------------------------------------------------------------------
# AC5: KG traversal results include run_id provenance
# ---------------------------------------------------------------------------


class TestAC5_KGRunIdProvenance:
    def test_kg_passages_include_run_count_and_recency_from_node_properties(self):
        """KG results expose ``run_count`` and ``last_run_at`` from node props.

        P0-004 replaced the unbounded ``run_ids`` array with these two
        properties; per-run history now lives in Postgres
        ``node_run_observations`` and is fetched separately.
        """
        nodes = [
            _ScoredNode(
                node_id="4:a",
                labels=["Variable"],
                properties={
                    "name": "ghrelin",
                    "run_count": 2,
                    "last_run_at": "2026-04-10T12:00:00Z",
                    "created_at": "2026-04-10T12:00:00Z",
                },
                score=1.0,
                relation_chain=[],
            ),
        ]

        results = _collect_passages(nodes, limit=10)

        assert results[0].metadata["run_count"] == 2
        assert results[0].metadata["last_run_at"] == "2026-04-10T12:00:00Z"
        assert results[0].metadata["run_date"] == "2026-04-10T12:00:00Z"
        assert results[0].metadata["created_at"] == "2026-04-10T12:00:00Z"

    def test_kg_passages_include_relation_memory_ids(self):
        """KG results carry rel_memory_ids — caller joins through PG for run_id."""
        nodes = [
            _ScoredNode(
                node_id="4:b",
                labels=["BrainRegion"],
                properties={"name": "VTA", "run_count": 1},
                score=0.85,
                relation_chain=["MEASURES"],
                rel_memory_ids=["mem-1"],
            ),
        ]

        results = _collect_passages(nodes, limit=10)

        assert results[0].metadata["rel_memory_ids"] == ["mem-1"]

    def test_kg_passages_without_run_provenance_omit_keys(self):
        """Nodes without run_count/last_run_at don't get the keys in metadata."""
        nodes = [
            _ScoredNode(
                node_id="4:c",
                labels=["Paradigm"],
                properties={"name": "test"},
                score=0.7,
                relation_chain=[],
            ),
        ]

        results = _collect_passages(nodes, limit=10)

        assert "run_count" not in results[0].metadata
        assert "last_run_at" not in results[0].metadata
        # Legacy keys must not leak back in.
        assert "run_ids" not in results[0].metadata
        assert "run_id" not in results[0].metadata

    def test_seed_node_has_no_rel_memory_ids(self):
        """Seed nodes (hop 0) have no relation memory_ids."""
        nodes = [
            _ScoredNode(
                node_id="4:seed",
                labels=["Variable"],
                properties={"name": "x", "run_count": 1},
                score=1.0,
                relation_chain=[],
                rel_memory_ids=None,
            ),
        ]

        results = _collect_passages(nodes, limit=10)

        assert "rel_memory_ids" not in results[0].metadata
