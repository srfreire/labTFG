"""Integration tests for `--until X` partial pipeline runs.

Hit the real shared infrastructure (Postgres, etc.) but stub out the
agents to avoid API calls. Verify the --until flag terminates the loop
cleanly, persists final_stage on the run row, and records per-stage
Memory Agent results in runs.memory_results.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from decisionlab.knowledge.models import MemoryAgentResult
from decisionlab.router import PipelineState, Router, Stage


@pytest_asyncio.fixture
async def shared_init():
    """Bring up real shared infra and tear it down after each test."""
    import shared

    await shared.init()
    try:
        yield shared
    finally:
        await shared.shutdown()


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


async def _seed_run(shared_mod, run_id: uuid.UUID, problem: str) -> None:
    from shared.models import Run

    async with shared_mod.db.get_session() as s:
        s.add(
            Run(
                id=run_id,
                problem_description=problem,
                status="running",
                s3_prefix=f"research/{run_id}",
            )
        )
        await s.commit()


async def _delete_run(shared_mod, run_id: uuid.UUID) -> None:
    from sqlalchemy import delete

    from shared.models import Run

    async with shared_mod.db.get_session() as s:
        await s.execute(delete(Run).where(Run.id == run_id))
        await s.commit()


async def _fetch_run(shared_mod, run_id: uuid.UUID):
    from shared.models import Run

    async with shared_mod.db.get_session() as s:
        return await s.get(Run, run_id)


def _make_router_with_real_db(memory_agent, run_id: str) -> Router:
    """Router bound to a real DB-backed Run row; agents are mocked separately."""
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test problem",
        reports_dir=Path("."),
        run_id=run_id,
    )
    # `_init_memory_agent` short-circuits to None when shared.db is mocked,
    # but here we want to inject a mock agent on a real-DB Router. Skip the
    # auto-init and assign manually.
    with patch.object(Router, "_init_memory_agent", return_value=None):
        router = Router(
            client=AsyncMock(),
            state=state,
            search=MagicMock(),
            project_root=Path("."),
            stop_after=Stage.RESEARCH,
        )
    router.memory_agent = memory_agent
    router.state.save = AsyncMock()
    return router


@pytest.mark.asyncio
async def test_stop_after_research_terminates_after_review(shared_init):
    """With stop_after=RESEARCH, the loop ends after REVIEW_RESEARCH and
    never advances into FORMALIZE."""
    run_id = uuid.uuid4()
    await _seed_run(shared_init, run_id, "stop-after-research")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(return_value=_make_memory_result())
        router = _make_router_with_real_db(memory_agent, str(run_id))

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = Stage.FORMALIZE  # natural next stage

        formalize_called = False

        async def mock_formalize():
            nonlocal formalize_called
            formalize_called = True
            router.state.stage = router._next_after_work(Stage.FORMALIZE)

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(
                router, "_review_research", side_effect=mock_review_research
            ),
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
        await _delete_run(shared_init, run_id)


@pytest.mark.asyncio
async def test_partial_run_persists_final_stage_and_memory_results(shared_init):
    """After a `--until research` run, the runs row has final_stage='research'
    and memory_results contains the researcher's MemoryAgentResult dict."""
    run_id = uuid.uuid4()
    await _seed_run(shared_init, run_id, "partial-run-persistence")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(
            return_value=_make_memory_result(nodes_created=7, facts_stored=11)
        )
        router = _make_router_with_real_db(memory_agent, str(run_id))

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = Stage.FORMALIZE

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(
                router, "_review_research", side_effect=mock_review_research
            ),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        run_row = await _fetch_run(shared_init, run_id)
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
        await _delete_run(shared_init, run_id)


@pytest.mark.asyncio
async def test_memory_failure_persists_error_and_keeps_run_alive(shared_init):
    """When MemoryAgent.run() throws, the loop continues to REVIEW and then
    DONE, and runs.memory_results['researcher']['status'] == 'failed' with
    the error string captured."""
    run_id = uuid.uuid4()
    await _seed_run(shared_init, run_id, "memory-failure")
    try:
        memory_agent = MagicMock()
        memory_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
        router = _make_router_with_real_db(memory_agent, str(run_id))

        async def mock_research():
            router.state.stage = router._next_after_work(Stage.RESEARCH)

        async def mock_review_research():
            router.state.stage = Stage.FORMALIZE

        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(
                router, "_review_research", side_effect=mock_review_research
            ),
            patch.object(router, "_run_consolidation", AsyncMock()),
        ):
            await router.run()

        assert router.state.stage == Stage.DONE
        run_row = await _fetch_run(shared_init, run_id)
        assert run_row is not None
        researcher = (run_row.memory_results or {}).get("researcher")
        assert researcher is not None
        assert researcher["status"] == "failed"
        assert "boom" in researcher["error"]
    finally:
        await _delete_run(shared_init, run_id)


def test_invalid_stop_after_raises():
    """stop_after must be a work stage; review/done/memory stages are rejected."""
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test",
        reports_dir=Path("."),
        run_id=str(uuid.uuid4()),
    )
    with patch.object(Router, "_init_memory_agent", return_value=None):
        with pytest.raises(ValueError, match="stop_after must be a work stage"):
            Router(
                client=AsyncMock(),
                state=state,
                search=MagicMock(),
                project_root=Path("."),
                stop_after=Stage.REVIEW_RESEARCH,
            )
        with pytest.raises(ValueError, match="stop_after must be a work stage"):
            Router(
                client=AsyncMock(),
                state=state,
                search=MagicMock(),
                project_root=Path("."),
                stop_after=Stage.MEMORY_RESEARCH,
            )
