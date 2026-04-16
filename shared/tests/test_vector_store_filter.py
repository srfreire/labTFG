"""Unit tests for shared.vector_store._build_filter.

These don't need Qdrant — they exercise the helper that turns user dicts
into Qdrant Filter objects.
"""

from __future__ import annotations

from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

from shared.vector_store import _build_filter


def test_build_filter_exact_match():
    """{'k': 'v'} produces a single MatchValue condition."""
    f = _build_filter({"namespace": "paradigm"})
    assert isinstance(f, Filter)
    assert f.must is not None
    assert len(f.must) == 1
    cond = f.must[0]
    assert isinstance(cond, FieldCondition)
    assert cond.key == "namespace"
    assert isinstance(cond.match, MatchValue)
    assert cond.match.value == "paradigm"


def test_build_filter_range():
    """A nested dict produces a Range condition."""
    f = _build_filter({"confidence": {"gte": 0.7}})
    assert f.must is not None
    cond = f.must[0]
    assert cond.key == "confidence"
    assert isinstance(cond.range, Range)
    assert cond.range.gte == 0.7


def test_build_filter_combines_multiple():
    """Multiple keys produce one condition each."""
    f = _build_filter(
        {"namespace": "paradigm", "confidence": {"gte": 0.5, "lte": 1.0}}
    )
    assert f.must is not None
    assert len(f.must) == 2
    keys = {c.key for c in f.must}
    assert keys == {"namespace", "confidence"}


def test_build_filter_int_value():
    """Integer values use MatchValue (not Range)."""
    f = _build_filter({"step": 42})
    assert f.must is not None
    cond = f.must[0]
    assert isinstance(cond.match, MatchValue)
    assert cond.match.value == 42


def test_build_filter_empty_dict():
    """An empty dict yields a Filter with empty `must` list (no conditions)."""
    f = _build_filter({})
    assert isinstance(f, Filter)
    assert f.must == []
