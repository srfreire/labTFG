"""Tests for Router ↔ MemoryAgent integration."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.models import MemoryAgentResult
from decisionlab.router import PipelineState, Router, Stage
from shared.services import Services

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_db_with_session():
    """Build a mock DatabaseService whose get_session is a working asynccontextmanager."""
    mock_db = MagicMock()
    session = AsyncMock()
    session.commit = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []
    exec_result.all.return_value = []
    session.execute = AsyncMock(return_value=exec_result)
    fake_run = MagicMock()
    fake_run.memory_results = None
    session.get = AsyncMock(return_value=fake_run)

    @asynccontextmanager
    async def _ctx():
        yield session

    mock_db.get_session = _ctx
    return mock_db


def _make_storage():
    storage = MagicMock()
    storage.get_text = AsyncMock(return_value="mock stage output")
    storage.put_text = AsyncMock()
    storage.list = AsyncMock(return_value=[])
    storage.exists = AsyncMock(return_value=True)
    return storage


def _make_services(*, db=None, storage=None, kg=None, vectors=None, embeddings=None):
    return Services(
        db=db if db is not None else _make_db_with_session(),
        storage=storage if storage is not None else _make_storage(),
        kg=kg,
        vectors=vectors,
        embeddings=embeddings,
    )


def _make_router(emit=None, memory_agent=None, services=None) -> Router:
    client = AsyncMock()
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test problem",
        reports_dir=Path("."),
        run_id=str(uuid.uuid4()),
    )
    search = MagicMock()
    services = services or _make_services()
    # Patch _init_memory_agent to avoid auto-creating one.
    with patch.object(Router, "_init_memory_agent", return_value=None):
        router = Router(
            client=client,
            state=state,
            search=search,
            project_root=Path("."),
            emit=emit,
            services=services,
        )
    if memory_agent is not None:
        router.memory_agent = memory_agent
    # Mock save() — avoids S3 dependency
    router.state.save = AsyncMock()
    return router


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_has_memory_agent_attribute():
    """Router should have memory_agent attribute (defaults to None when no infra)."""
    router = _make_router()
    assert hasattr(router, "memory_agent")
    assert router.memory_agent is None


@pytest.mark.asyncio
async def test_router_auto_inits_memory_agent_when_shared_available():
    """Router creates MemoryAgent automatically when knowledge infra is available."""
    services = _make_services(
        kg=MagicMock(),
        vectors=MagicMock(),
        embeddings=MagicMock(),
    )

    client = AsyncMock()
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test",
        reports_dir=Path("."),
        run_id=str(uuid.uuid4()),
    )
    router = Router(
        client=client,
        state=state,
        search=MagicMock(),
        project_root=Path("."),
        services=services,
    )

    assert router.memory_agent is not None


@pytest.mark.asyncio
async def test_memory_agent_called_after_research():
    """AC1: MemoryAgent.run() is called after successful research stage."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(return_value=_make_memory_result())
    emit = AsyncMock()

    router = _make_router(emit=emit, memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

    async def mock_formalize():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research),
        patch.object(router, "_review_research", side_effect=mock_review),
        patch.object(router, "_do_formalize", side_effect=mock_formalize),
    ):
        await router.run()

    assert memory_agent.run.await_count >= 1
    first_call = memory_agent.run.call_args_list[0]
    assert first_call.args[0] == "researcher"


@pytest.mark.asyncio
async def test_memory_agent_not_called_for_review_stages():
    """Memory Agent is NOT called for REVIEW_* stages."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(return_value=_make_memory_result())

    router = _make_router(memory_agent=memory_agent)
    router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    with patch.object(router, "_review_research", side_effect=mock_review):
        await router.run()

    memory_agent.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_agent_failure_does_not_block_pipeline():
    """AC5: If MemoryAgent.run() throws inside _memory_<stage>, the pipeline continues."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
    emit = AsyncMock()

    router = _make_router(emit=emit, memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research),
        patch.object(router, "_review_research", side_effect=mock_review),
    ):
        await router.run()

    assert router.state.stage == Stage.DONE


@pytest.mark.asyncio
async def test_memory_agent_skipped_when_none():
    """AC4: If memory_agent is None, pipeline runs normally."""
    router = _make_router()
    assert router.memory_agent is None
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research),
        patch.object(router, "_review_research", side_effect=mock_review),
    ):
        await router.run()

    assert router.state.stage == Stage.DONE


@pytest.mark.asyncio
async def test_memory_agent_skipped_on_handler_failure():
    """Memory Agent is NOT called if the stage handler fails (stage doesn't advance)."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(return_value=_make_memory_result())

    router = _make_router(memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH

    call_count = 0

    async def mock_research_fail():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return  # don't advance stage — simulates handler failure
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = router._next_after_review(Stage.REVIEW_RESEARCH)

    async def mock_formalize():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research_fail),
        patch.object(router, "_review_research", side_effect=mock_review),
        patch.object(router, "_do_formalize", side_effect=mock_formalize),
    ):
        await router.run()

    assert memory_agent.run.await_count == 1


@pytest.mark.asyncio
async def test_memory_agent_called_for_all_work_stages():
    """AC1: MemoryAgent is called after RESEARCH, FORMALIZE, REASON, and BUILD."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(return_value=_make_memory_result())
    emit = AsyncMock()

    router = _make_router(emit=emit, memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH
    router.state.approved_paradigms = ["test-paradigm"]
    router.state.selected_formulations = {"test-paradigm": ["f01"]}
    router.state.approved_specs = {"test-paradigm": ["f01"]}

    def make_work(work_stage: Stage):
        async def fn():
            router.state.stage = router._next_after_work(work_stage)

        return fn

    def make_advance(target: Stage):
        async def fn():
            router.state.stage = target

        return fn

    handler_mocks = {
        "_do_research": make_work(Stage.RESEARCH),
        "_review_research": make_advance(
            router._next_after_review(Stage.REVIEW_RESEARCH)
        ),
        "_do_formalize": make_work(Stage.FORMALIZE),
        "_review_formalize": make_advance(
            router._next_after_review(Stage.REVIEW_FORMALIZE)
        ),
        "_get_env_spec": make_advance(Stage.REASON),
        "_do_reason": make_work(Stage.REASON),
        "_review_reason": make_advance(router._next_after_review(Stage.REVIEW_REASON)),
        "_do_build": make_work(Stage.BUILD),
        "_review_build": make_advance(router._next_after_review(Stage.REVIEW_BUILD)),
    }

    patches = [
        patch.object(router, name, side_effect=fn) for name, fn in handler_mocks.items()
    ]
    for p in patches:
        p.start()
    try:
        await router.run()
    finally:
        for p in patches:
            p.stop()

    called_stages = [call.args[0] for call in memory_agent.run.call_args_list]
    assert "researcher" in called_stages
    assert "formalizer" in called_stages
    assert "reasoner" in called_stages
    assert "builder" in called_stages
    assert memory_agent.run.await_count == 4


# ---------------------------------------------------------------------------
# P4-005: agents init message tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_emits_agents_message_with_memory_agent():
    """AC4: agents init message includes memory_agent when available."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(return_value=_make_memory_result())
    emit = AsyncMock()

    router = _make_router(emit=emit, memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research),
        patch.object(router, "_review_research", side_effect=mock_review),
    ):
        await router.run()

    agents_msgs = [
        call.args[0]
        for call in emit.call_args_list
        if isinstance(call.args[0], dict) and call.args[0].get("type") == "agents"
    ]
    assert len(agents_msgs) == 1
    agents_list = agents_msgs[0]["agents"]
    agent_names = [a["name"] for a in agents_list]
    assert "memory_agent" in agent_names
    ma_entry = next(a for a in agents_list if a["name"] == "memory_agent")
    assert "color" in ma_entry


@pytest.mark.asyncio
async def test_router_emits_agents_message_without_memory_agent():
    """AC3: agents init message excludes memory_agent when infra unavailable."""
    emit = AsyncMock()

    router = _make_router(emit=emit)  # No memory_agent
    assert router.memory_agent is None
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = router._next_after_work(Stage.RESEARCH)

    async def mock_review():
        router.state.stage = Stage.DONE

    with (
        patch.object(router, "_do_research", side_effect=mock_research),
        patch.object(router, "_review_research", side_effect=mock_review),
    ):
        await router.run()

    agents_msgs = [
        call.args[0]
        for call in emit.call_args_list
        if isinstance(call.args[0], dict) and call.args[0].get("type") == "agents"
    ]
    assert len(agents_msgs) == 1
    agent_names = [a["name"] for a in agents_msgs[0]["agents"]]
    assert "memory_agent" not in agent_names
