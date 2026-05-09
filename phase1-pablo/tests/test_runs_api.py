import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seeded_runs():
    """Seed three terminal runs + one running via the real DatabaseService."""
    from shared.models import Run
    from shared.services import init_services, shutdown_services

    services = await init_services()
    now = datetime.now(UTC).replace(tzinfo=None)
    ids = [uuid.uuid4() for _ in range(4)]
    try:
        async with services.db.get_session() as s:
            s.add_all(
                [
                    Run(
                        id=ids[0],
                        problem_description="p-done",
                        status="done",
                        s3_prefix=f"research/{ids[0]}",
                        artifact_count=3,
                        created_at=now - timedelta(minutes=3),
                    ),
                    Run(
                        id=ids[1],
                        problem_description="p-cancel",
                        status="cancelled",
                        s3_prefix=f"research/{ids[1]}",
                        artifact_count=None,
                        created_at=now - timedelta(minutes=2),
                    ),
                    Run(
                        id=ids[2],
                        problem_description="p-fail",
                        status="failed",
                        s3_prefix=f"research/{ids[2]}",
                        artifact_count=None,
                        created_at=now - timedelta(minutes=1),
                    ),
                    Run(
                        id=ids[3],
                        problem_description="p-running",
                        status="running",
                        s3_prefix=f"research/{ids[3]}",
                        created_at=now,
                    ),
                ]
            )
            await s.commit()
    finally:
        await shutdown_services(services)

    yield [str(i) for i in ids]

    # cleanup — TestClient's lifespan owns its own services, so spin up
    # a fresh ``Services`` for the row deletion.
    from sqlalchemy import delete

    cleanup = await init_services()
    try:
        async with cleanup.db.get_session() as s:
            for rid in ids:
                await s.execute(delete(Run).where(Run.id == rid))
            await s.commit()
    finally:
        await shutdown_services(cleanup)


@pytest.mark.asyncio
async def test_runs_list_excludes_running_and_orders_newest_first(seeded_runs):
    from decisionlab.server import app

    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    payload = resp.json()
    # Only the seeded terminal runs — filter by our seeded ids to avoid picking
    # up rows from other tests
    seeded = [r for r in payload if r["run_id"] in seeded_runs]
    statuses = [r["status"] for r in seeded]
    assert "running" not in statuses
    # Newest first among our seeded: failed (-1m), cancelled (-2m), done (-3m)
    assert statuses[:3] == ["failed", "cancelled", "done"]
    sample = seeded[0]
    assert set(sample.keys()) == {
        "run_id",
        "problem",
        "status",
        "started_at",
        "artifact_count",
        "final_stage",
        "memory_results",
    }


@pytest.mark.asyncio
async def test_trace_endpoint_returns_ndjson(seeded_runs):
    from decisionlab.server import app
    from shared.services import init_services, shutdown_services

    run_id = seeded_runs[0]  # the 'done' run
    # Seed a trace for this run via a transient ``Services``; the endpoint
    # itself reads through the lifespan-owned ``Services`` inside TestClient.
    seed_services = await init_services()
    try:
        await seed_services.storage.put_text(
            f"research/{run_id}/trace.jsonl",
            '{"seq":1,"type":"run_start"}\n{"seq":2,"type":"pipeline_done"}\n',
            content_type="application/x-ndjson",
        )
    finally:
        await shutdown_services(seed_services)

    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/runs/{run_id}/trace")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2
    finally:
        cleanup = await init_services()
        try:
            await cleanup.storage.delete(f"research/{run_id}/trace.jsonl")
        finally:
            await shutdown_services(cleanup)


@pytest.mark.asyncio
async def test_trace_endpoint_returns_404_when_missing(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[0]  # 'done' but no trace seeded
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/trace")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trace_endpoint_returns_409_while_running(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[3]  # the 'running' one
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/trace")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_trace_endpoint_returns_404_on_malformed_uuid(seeded_runs):
    """A non-UUID run_id raises ValueError on uuid.UUID() and is mapped to 404
    before any DB/storage lookup happens (see decisionlab.server.get_run_trace).
    """
    from decisionlab.server import app

    with TestClient(app) as client:
        resp = client.get("/api/runs/not-a-valid-uuid/trace")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Trace not found"
