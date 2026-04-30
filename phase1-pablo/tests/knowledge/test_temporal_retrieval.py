"""Tests for P5-004: temporal retrieval via as_of parameter.

Tests the as_of filtering in retrieve_knowledge, verifying that only
results valid at the given timestamp are returned.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    _apply_temporal_filter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso(days_ago: int = 0) -> str:
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _result(text: str, score: float, source: str, **meta) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata=dict(meta))


# ---------------------------------------------------------------------------
# AC4: retrieve_knowledge(query, as_of=run_1_date) returns only run-1 knowledge
# ---------------------------------------------------------------------------


class TestAsOfSchemaParameter:
    def test_schema_includes_as_of_parameter(self):
        """The tool schema exposes an optional as_of parameter."""
        props = RETRIEVE_KNOWLEDGE_SCHEMA["input_schema"]["properties"]
        assert "as_of" in props
        assert props["as_of"]["type"] == "string"

    def test_as_of_not_required(self):
        """as_of is optional — not in required list."""
        required = RETRIEVE_KNOWLEDGE_SCHEMA["input_schema"]["required"]
        assert "as_of" not in required


class TestTemporalFilter:
    def test_filters_out_results_created_after_as_of(self):
        """Results with created_at after as_of are excluded."""
        as_of = datetime.now(UTC) - timedelta(days=5)
        results = [
            _result("old", 0.9, "dense", created_at=_utc_iso(10)),  # before as_of
            _result("new", 0.95, "dense", created_at=_utc_iso(1)),  # after as_of
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 1
        assert filtered[0].text == "old"

    def test_includes_results_created_at_exactly_as_of(self):
        """Results created exactly at as_of are included."""
        as_of = datetime.now(UTC)
        results = [
            _result("exact", 0.9, "dense", created_at=as_of.isoformat()),
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 1

    def test_excludes_expired_results(self):
        """Results with valid_to before as_of are excluded."""
        as_of = datetime.now(UTC) - timedelta(days=2)
        results = [
            _result(
                "expired",
                0.9,
                "dense",
                created_at=_utc_iso(10),
                valid_to=_utc_iso(5),  # expired 5 days ago, before as_of (2 days ago)
            ),
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 0

    def test_includes_results_with_null_valid_to(self):
        """Results without valid_to (currently valid) are included."""
        as_of = datetime.now(UTC)
        results = [
            _result("current", 0.9, "dense", created_at=_utc_iso(5)),
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 1

    def test_no_timestamp_results_excluded(self):
        """Results without any timestamp are excluded when as_of is set."""
        as_of = datetime.now(UTC)
        results = [
            _result("no-ts", 0.9, "web"),
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 0

    def test_unparseable_valid_to_excludes_result(self):
        """Results with present but unparseable valid_to are excluded."""
        as_of = datetime.now(UTC)
        results = [
            _result(
                "corrupt", 0.9, "dense", created_at=_utc_iso(5), valid_to="not-a-date"
            ),
        ]

        filtered = _apply_temporal_filter(results, as_of)

        assert len(filtered) == 0


class TestAC5_DefaultRetrievalCurrentOnly:
    def test_none_as_of_returns_all_results(self):
        """Default retrieval (no as_of) returns only currently valid knowledge."""
        results = [
            _result("current", 0.9, "dense", created_at=_utc_iso(0)),
            _result("old", 0.8, "dense", created_at=_utc_iso(30)),
        ]

        # With as_of=None, no temporal filter should be applied
        filtered = _apply_temporal_filter(results, None)

        assert len(filtered) == 2
