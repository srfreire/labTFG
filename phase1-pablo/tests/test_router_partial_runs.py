"""Integration tests for `--until X` partial pipeline runs.

Hit the real shared infrastructure (Postgres, etc.) but stub out the
agents to avoid API calls. Verify the --until flag terminates the loop
cleanly, persists final_stage on the run row, and records per-stage
Memory Agent results in runs.memory_results.
"""

from __future__ import annotations

import contextlib
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from decisionlab.knowledge.models import MemoryAgentResult
from decisionlab.router import PipelineState, Router, Stage

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def services_fixture():
    """Bring up real infrastructure ``Services`` and tear them down after each test."""
    from shared.services import init_services, shutdown_services

    services = await init_services()
    try:
        yield services
    finally:
        await shutdown_services(services)


def _make_memory_result(**overrides) -> MemoryAgentResult:
    defaults = dict(
        nodes_created=2,
        nodes_merged=1,
        relations_created=1,
        facts_stored=3,
        duplicates_skipped=0,
        conflicts_resolved=0,
        duration_ms=150,
    )
    defaults.update(overrides)
    return MemoryAgentResult(**defaults)


async def _seed_run(services, run_id: uuid.UUID, problem: str) -> None:
    from shared.models import Run

    async with services.db.get_session() as s:
        s.add(
            Run(
                id=run_id,
                problem_description=problem,
                status="running",
                s3_prefix=f"research/{run_id}",
            )
        )
        await s.commit()


async def _delete_run(services, run_id: uuid.UUID) -> None:
    from sqlalchemy import delete

    from shared.models import Run

    async with services.db.get_session() as s:
        await s.execute(delete(Run).where(Run.id == run_id))
        await s.commit()


async def _fetch_run(services, run_id: uuid.UUID):
    from shared.models import Run

    async with services.db.get_session() as s:
        return await s.get(Run, run_id)


def _make_router_with_real_db(memory_agent, run_id: str, services=None) -> Router:
    """Router bound to a real DB-backed Run row; agents are mocked separately."""
    from shared.services import Services

    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test problem",
        reports_dir=Path("."),
        run_id=run_id,
    )
    # When ``services`` is provided, use it; otherwise build a mock.
    if services is None:
        services = Services(
            db=MagicMock(),
            storage=MagicMock(),
            kg=None,
            vectors=None,
            embeddings=None,
        )
    with patch.object(Router, "_init_memory_agent", return_value=None):
        router = Router(
            client=AsyncMock(),
            state=state,
            search=MagicMock(),
            project_root=Path("."),
            stop_after=Stage.RESEARCH,
            services=services,
        )
    router.memory_agent = memory_agent
    router.state.save = AsyncMock()
    return router


@pytest.mark.asyncio
async def test_stop_after_research_terminates_after_review(services_fixture):
    """With stop_after=RESEARCH, the loop ends after REVIEW_RESEARCH and
    never advances into FORMALIZE."""
    run_id = uuid.uuid4()
    await _seed_run(services_fixture, run_id, "stop-after-research")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(return_value=_make_memory_result())
        router = _make_router_with_real_db(memory_agent, str(run_id), services_fixture)

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

        formalize_called = False

        async def mock_formalize():
            nonlocal formalize_called
            formalize_called = True
            router.state.stage = router._next_after_work(Stage.FORMALIZE)

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review_research),
            patch.object(router, "_do_formalize", side_effect=mock_formalize),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        assert router.state.stage == Stage.DONE
        assert formalize_called is False
        assert memory_agent.run.await_count == 1
        first_call = memory_agent.run.call_args_list[0]
        assert first_call.args[0] == "researcher"
    finally:
        await _delete_run(services_fixture, run_id)


@pytest.mark.asyncio
async def test_partial_run_persists_final_stage_and_memory_results(services_fixture):
    """After a `--until research` run, the runs row has final_stage='research'
    and memory_results contains the researcher's MemoryAgentResult dict."""
    run_id = uuid.uuid4()
    await _seed_run(services_fixture, run_id, "partial-run-persistence")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(
            return_value=_make_memory_result(nodes_created=7, facts_stored=11)
        )
        router = _make_router_with_real_db(memory_agent, str(run_id), services_fixture)

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review_research),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        run_row = await _fetch_run(services_fixture, run_id)
        assert run_row is not None
        assert run_row.final_stage == "research"
        assert run_row.memory_results is not None
        assert "researcher" in run_row.memory_results
        researcher = run_row.memory_results["researcher"]
        assert researcher["status"] == "ok"
        assert researcher["nodes_created"] == 7
        assert researcher["facts_stored"] == 11
        assert researcher["duration_ms"] == 150
    finally:
        await _delete_run(services_fixture, run_id)


@pytest.mark.asyncio
async def test_memory_failure_persists_error_and_keeps_run_alive(services_fixture):
    """When MemoryAgent.run() throws, the loop continues to REVIEW and then
    DONE, and runs.memory_results['researcher']['status'] == 'failed' with
    the error string captured."""
    run_id = uuid.uuid4()
    await _seed_run(services_fixture, run_id, "memory-failure")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
        router = _make_router_with_real_db(memory_agent, str(run_id), services_fixture)

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review_research),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        assert router.state.stage == Stage.DONE
        run_row = await _fetch_run(services_fixture, run_id)
        assert run_row is not None
        researcher = (run_row.memory_results or {}).get("researcher")
        assert researcher is not None
        assert researcher["status"] == "failed"
        assert "boom" in researcher["error"]
    finally:
        await _delete_run(services_fixture, run_id)


@pytest.mark.asyncio
async def test_partial_run_uploads_agrex_trace_artifact(services_fixture):
    """After `--until research`, research/{run_id}/trace.jsonl is in S3 and
    contains the events the stage handler emitted via Router._tracer."""
    from agrex import parse_trace

    run_id = uuid.uuid4()
    await _seed_run(services_fixture, run_id, "trace-artifact-check")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(return_value=_make_memory_result())
        router = _make_router_with_real_db(memory_agent, str(run_id), services_fixture)

        async def mock_research():
            router._tracer.agent("researcher", "Researcher")
            router._tracer.done("researcher")
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review_research),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        trace_key = f"research/{run_id}/trace.jsonl"
        assert await services_fixture.storage.exists(trace_key)
        content = await services_fixture.storage.get_text(trace_key)
        events = parse_trace(content)
        assert any(
            e["type"] == "node_add" and e["node"]["id"] == "researcher" for e in events
        )
        assert any(
            e["type"] == "node_update"
            and e["id"] == "researcher"
            and e["status"] == "done"
            for e in events
        )
        assert all("ts" in e for e in events)
        # Task 1: research stage emits a `tracer.stage(...)` event into the trace.
        assert any(
            e["type"] == "stage" and e.get("label") == "research" for e in events
        )
        # Task 1: REVIEW_RESEARCH transition emits a yellow review marker.
        assert any(
            e["type"] == "marker" and e.get("kind") == "review_research" for e in events
        )
    finally:
        await _delete_run(services_fixture, run_id)
        with contextlib.suppress(Exception):
            await services_fixture.storage.delete(f"research/{run_id}/trace.jsonl")


def test_invalid_stop_after_raises():
    """stop_after must be a work stage; review/done/memory stages are rejected."""
    from shared.services import Services

    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test",
        reports_dir=Path("."),
        run_id=str(uuid.uuid4()),
    )
    services = Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )
    with patch.object(Router, "_init_memory_agent", return_value=None):
        with pytest.raises(ValueError, match="stop_after must be a work stage"):
            Router(
                client=AsyncMock(),
                state=state,
                search=MagicMock(),
                project_root=Path("."),
                stop_after=Stage.REVIEW_RESEARCH,
                services=services,
            )
        with pytest.raises(ValueError, match="stop_after must be a work stage"):
            Router(
                client=AsyncMock(),
                state=state,
                search=MagicMock(),
                project_root=Path("."),
                stop_after=Stage.MEMORY_RESEARCH,
                services=services,
            )
