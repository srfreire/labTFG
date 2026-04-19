import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient


@pytest_asyncio.fixture
async def seeded_runs():
    """Seed three terminal runs + one running via the real DatabaseService."""
    import shared
    from shared.models import Run

    await shared.init()
    now = datetime.now(UTC).replace(tzinfo=None)
    ids = [uuid.uuid4() for _ in range(4)]
    async with shared.db.get_session() as s:
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
    yield [str(i) for i in ids]
    # cleanup — TestClient's lifespan may have torn shared down, so re-init
    # if needed before deleting our seeded rows.
    from sqlalchemy import delete

    if shared.db is None:
        await shared.init()
    async with shared.db.get_session() as s:
        for rid in ids:
            await s.execute(delete(Run).where(Run.id == rid))
        await s.commit()
    await shared.shutdown()


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
    }


@pytest.mark.asyncio
async def test_events_endpoint_returns_ndjson(seeded_runs):
    import shared
    from decisionlab.server import app

    run_id = seeded_runs[0]  # the 'done' run
    # Seed an event log for this run
    await shared.storage.put_text(
        f"research/{run_id}/events.jsonl",
        '{"seq":1,"type":"run_start"}\n{"seq":2,"type":"pipeline_done"}\n',
        content_type="application/x-ndjson",
    )
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/runs/{run_id}/events")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2
    finally:
        # TestClient's lifespan tears shared down; re-init for cleanup.
        if shared.storage is None:
            await shared.init()
        await shared.storage.delete(f"research/{run_id}/events.jsonl")


@pytest.mark.asyncio
async def test_events_endpoint_returns_404_when_missing(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[0]  # 'done' but no event log seeded
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_events_endpoint_returns_409_while_running(seeded_runs):
    from decisionlab.server import app

    run_id = seeded_runs[3]  # the 'running' one
    with TestClient(app) as client:
        resp = client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 409
