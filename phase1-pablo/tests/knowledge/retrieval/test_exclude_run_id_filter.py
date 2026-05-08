"""exclude_run_id moves from a Python post-filter into a Qdrant
must_not. Verifies (a) the value reaches the vector store call so
Qdrant applies the filter server-side, and (b) the post-filter loop
no longer drops points whose run_id matches.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

from decisionlab.knowledge.retrieval import vector_retrieval as vr
from shared.vector_store import ScoredPoint, _build_filter


def test_build_filter_lifts_exclude_into_must_not():
    """Special ``_exclude`` key is converted to a Qdrant ``must_not``
    condition; normal keys stay in ``must``."""
    f = _build_filter(
        {"namespace": "paradigm", "_exclude": {"run_id": "run-123"}}
    )
    assert isinstance(f, Filter)
    assert f.must == [
        FieldCondition(key="namespace", match=MatchValue(value="paradigm"))
    ]
    assert f.must_not == [
        FieldCondition(key="run_id", match=MatchValue(value="run-123"))
    ]


@pytest.mark.asyncio
async def test_exclude_run_id_is_passed_into_qdrant_filters(monkeypatch):
    """``exclude_run_id`` in the user-facing filters should be folded
    into the dict handed to ``search_dense`` / ``search_sparse``, NOT
    applied as a Python post-filter loop."""
    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    await vr.vector_retrieve(
        query="x",
        embedding_service=fake_emb,
        vector_store=fake_vs,
        limit=5,
        filters={"exclude_run_id": "run-123"},
    )

    dense_filters = fake_vs.search_dense.call_args.kwargs.get("filters")
    sparse_filters = fake_vs.search_sparse.call_args.kwargs.get("filters")

    assert dense_filters is not None
    assert dense_filters.get("_exclude", {}).get("run_id") == "run-123"
    assert sparse_filters is not None
    assert sparse_filters.get("_exclude", {}).get("run_id") == "run-123"


@pytest.mark.asyncio
async def test_no_post_filter_drops_qdrant_returned_points():
    """When Qdrant has already applied must_not, every returned point
    must survive — the old post-filter loop is gone."""
    pt = ScoredPoint(
        id="p1",
        score=0.9,
        payload={"text_preview": "x", "run_id": "run-keep"},
    )
    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[pt])
    fake_vs.search_sparse = AsyncMock(return_value=[pt])

    fake_emb = MagicMock()
    fake_emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

    dense, sparse = await vr.vector_retrieve(
        query="x",
        embedding_service=fake_emb,
        vector_store=fake_vs,
        limit=5,
        filters={"exclude_run_id": "run-123"},
    )
    # Qdrant has already filtered; we should not double-filter and
    # should not see this point dropped on the basis of run_id.
    assert any(r.metadata.get("run_id") == "run-keep" for r in dense)
    assert any(r.metadata.get("run_id") == "run-keep" for r in sparse)
