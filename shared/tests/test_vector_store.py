"""Integration tests for VectorStore (requires Qdrant on localhost:6333)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from shared.settings import Settings
from shared.vector_store import VectorStore

MANAGED_COLLECTIONS = ["artifacts_dense", "memories_dense", "artifacts_sparse", "memories_sparse"]


@pytest_asyncio.fixture
async def vs():
    """Yield a connected VectorStore with clean collections; close on teardown."""
    svc = VectorStore(Settings())
    await svc.connect()
    # Wipe managed collections so tests start from a clean state
    client = svc._c()
    for name in MANAGED_COLLECTIONS:
        try:
            await client.delete_collection(name)
        except Exception:
            pass
    yield svc
    await svc.close()


def _payload(namespace: str = "paradigm", confidence: float = 0.8) -> dict:
    return {
        "entity_id": uuid.uuid4().hex,
        "namespace": namespace,
        "source_stage": "researcher",
        "run_id": uuid.uuid4().hex,
        "importance": 5.0,
        "confidence": confidence,
        "created_at": "2026-04-14T00:00:00Z",
        "text_preview": "test point",
    }


# -- AC1: init_collections idempotent -----------------------------------------


@pytest.mark.asyncio
async def test_init_collections_creates_all_four(vs: VectorStore):
    """init_collections creates all 4 collections on fresh Qdrant."""
    await vs.init_collections()
    client = vs._c()
    names = {c.name for c in (await client.get_collections()).collections}
    for expected in ("artifacts_dense", "memories_dense", "artifacts_sparse", "memories_sparse"):
        assert expected in names, f"{expected} not created"


@pytest.mark.asyncio
async def test_init_collections_idempotent(vs: VectorStore):
    """Calling init_collections twice does not raise or duplicate."""
    await vs.init_collections()
    await vs.init_collections()  # should not raise
    client = vs._c()
    names = [c.name for c in (await client.get_collections()).collections]
    assert names.count("artifacts_dense") == 1


# -- AC2: dense upsert + search -----------------------------------------------


@pytest.mark.asyncio
async def test_dense_upsert_and_search(vs: VectorStore):
    """Can upsert a dense vector and search it back with correct payload."""
    await vs.init_collections()
    coll = "artifacts_dense"
    point_id = str(uuid.uuid4())
    vector = [0.1] * 1024
    payload = _payload()

    await vs.upsert_dense(coll, point_id, vector, payload)
    results = await vs.search_dense(coll, vector, limit=5)

    assert len(results) >= 1
    found = next((r for r in results if r.id == point_id), None)
    assert found is not None
    assert found.payload["namespace"] == "paradigm"
    assert found.payload["entity_id"] == payload["entity_id"]


# -- AC3: sparse upsert + search ----------------------------------------------


@pytest.mark.asyncio
async def test_sparse_upsert_and_search(vs: VectorStore):
    """Can upsert a sparse vector and search it back."""
    await vs.init_collections()
    coll = "artifacts_sparse"
    point_id = str(uuid.uuid4())
    indices = [0, 5, 10, 100]
    values = [1.0, 0.5, 0.8, 0.3]
    payload = _payload()

    await vs.upsert_sparse(coll, point_id, indices, values, payload)
    results = await vs.search_sparse(coll, indices, values, limit=5)

    assert len(results) >= 1
    found = next((r for r in results if r.id == point_id), None)
    assert found is not None
    assert found.payload["namespace"] == "paradigm"


# -- AC4: filter by namespace -------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_namespace(vs: VectorStore):
    """Upsert 3 points with different namespaces, filter returns only matching."""
    await vs.init_collections()
    coll = "artifacts_dense"
    vector = [0.5] * 1024

    ids = []
    for ns in ("paradigm", "formulation", "model"):
        pid = str(uuid.uuid4())
        ids.append((pid, ns))
        await vs.upsert_dense(coll, pid, vector, _payload(namespace=ns))

    results = await vs.search_dense(coll, vector, limit=10, filters={"namespace": "paradigm"})
    result_ids = {r.id for r in results}
    paradigm_id = ids[0][0]
    assert paradigm_id in result_ids
    for pid, ns in ids[1:]:
        assert pid not in result_ids, f"Point with namespace={ns} should be filtered out"


# -- AC5: filter by confidence threshold ---------------------------------------


@pytest.mark.asyncio
async def test_filter_by_confidence_threshold(vs: VectorStore):
    """confidence gte 0.7 excludes low-confidence points."""
    await vs.init_collections()
    coll = "memories_dense"
    vector = [0.3] * 1024

    high_id = str(uuid.uuid4())
    low_id = str(uuid.uuid4())
    await vs.upsert_dense(coll, high_id, vector, _payload(confidence=0.9))
    await vs.upsert_dense(coll, low_id, vector, _payload(confidence=0.3))

    results = await vs.search_dense(
        coll, vector, limit=10, filters={"confidence": {"gte": 0.7}}
    )
    result_ids = {r.id for r in results}
    assert high_id in result_ids
    assert low_id not in result_ids


# -- AC6: delete removes points -----------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_points(vs: VectorStore):
    """delete() removes points and subsequent search does not return them."""
    await vs.init_collections()
    coll = "artifacts_dense"
    point_id = str(uuid.uuid4())
    # Use a distinct vector direction so this point is uniquely the top result
    vector = [0.0] * 1024
    vector[0] = 1.0
    await vs.upsert_dense(coll, point_id, vector, _payload())

    # verify it's there
    results = await vs.search_dense(coll, vector, limit=1)
    assert len(results) == 1
    assert results[0].id == point_id

    # delete and verify gone
    await vs.delete(coll, [point_id])
    results = await vs.search_dense(coll, vector, limit=1)
    assert not any(r.id == point_id for r in results)


# -- Guard: not connected raises RuntimeError ----------------------------------


@pytest.mark.asyncio
async def test_not_connected_raises():
    """Calling methods before connect() raises RuntimeError."""
    svc = VectorStore(Settings())
    with pytest.raises(RuntimeError, match="not connected"):
        await svc.upsert_dense("artifacts_dense", "x", [0.0] * 1024, {})


# -- Upsert idempotency: re-upsert updates payload ----------------------------


@pytest.mark.asyncio
async def test_upsert_dense_updates_existing(vs: VectorStore):
    """Re-upserting same ID updates the payload."""
    await vs.init_collections()
    coll = "memories_dense"
    point_id = str(uuid.uuid4())
    vector = [0.0] * 1024
    vector[1] = 1.0

    await vs.upsert_dense(coll, point_id, vector, _payload(namespace="paradigm"))
    await vs.upsert_dense(coll, point_id, vector, _payload(namespace="model"))

    results = await vs.search_dense(coll, vector, limit=20)
    found = next((r for r in results if r.id == point_id), None)
    assert found is not None
    assert found.payload["namespace"] == "model"
    # Verify there's only one point with this ID (upsert replaced, not duplicated)
    assert sum(1 for r in results if r.id == point_id) == 1
