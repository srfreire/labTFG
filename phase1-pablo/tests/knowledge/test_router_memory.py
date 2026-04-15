"""Tests for Router ↔ MemoryAgent integration."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.models import MemoryAgentResult
from decisionlab.router import PipelineState, Router, Stage

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_router(emit=None, memory_agent=None) -> Router:
    client = AsyncMock()
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test problem",
        reports_dir=Path("."),
        run_id=str(uuid.uuid4()),
    )
    search = MagicMock()
    # Patch _init_memory_agent to avoid importing shared during construction
    with patch.object(Router, "_init_memory_agent", return_value=None):
        router = Router(
            client=client,
            state=state,
            search=search,
            project_root=Path("."),
            emit=emit,
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


def _mock_shared():
    """Create a mock shared module for inline import shared."""
    from contextlib import asynccontextmanager

    mock = MagicMock()
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    mock.db.get_session = _ctx
    mock.storage.get_text = AsyncMock(return_value="mock stage output")
    return mock


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
    """Router creates MemoryAgent automatically when shared infra is available."""
    mock_shared = _mock_shared()
    mock_shared.db = MagicMock()
    mock_shared.kg = MagicMock()
    mock_shared.vectors = MagicMock()
    mock_shared.embeddings = MagicMock()

    with patch.dict(sys.modules, {"shared": mock_shared}):
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
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review),
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

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
        with patch.object(router, "_review_research", side_effect=mock_review):
            await router.run()

    memory_agent.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_agent_failure_does_not_block_pipeline():
    """AC5: If MemoryAgent.run() throws via _run_memory_agent, the pipeline continues."""
    memory_agent = MagicMock()
    memory_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
    emit = AsyncMock()

    router = _make_router(emit=emit, memory_agent=memory_agent)
    router.state.stage = Stage.RESEARCH

    async def mock_research():
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
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
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
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
        # 2nd call: succeed → advance to review
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
        with (
            patch.object(router, "_do_research", side_effect=mock_research_fail),
            patch.object(router, "_review_research", side_effect=mock_review),
        ):
            await router.run()

    # Memory agent called exactly once — for the 2nd successful iteration only.
    # The 1st iteration (handler failure, no stage advance) did NOT trigger it.
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

    stage_sequence = [
        (Stage.RESEARCH, Stage.REVIEW_RESEARCH),
        (Stage.REVIEW_RESEARCH, Stage.FORMALIZE),
        (Stage.FORMALIZE, Stage.REVIEW_FORMALIZE),
        (Stage.REVIEW_FORMALIZE, Stage.GET_ENV_SPEC),
        (Stage.GET_ENV_SPEC, Stage.REASON),
        (Stage.REASON, Stage.REVIEW_REASON),
        (Stage.REVIEW_REASON, Stage.BUILD),
        (Stage.BUILD, Stage.REVIEW_BUILD),
        (Stage.REVIEW_BUILD, Stage.DONE),
    ]

    handler_mocks = {}
    handler_names = {
        Stage.RESEARCH: "_do_research",
        Stage.REVIEW_RESEARCH: "_review_research",
        Stage.FORMALIZE: "_do_formalize",
        Stage.REVIEW_FORMALIZE: "_review_formalize",
        Stage.GET_ENV_SPEC: "_get_env_spec",
        Stage.REASON: "_do_reason",
        Stage.REVIEW_REASON: "_review_reason",
        Stage.BUILD: "_do_build",
        Stage.REVIEW_BUILD: "_review_build",
    }

    for from_stage, to_stage in stage_sequence:
        async def make_handler(target_stage=to_stage):
            router.state.stage = target_stage

        handler_mocks[handler_names[from_stage]] = make_handler

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
        patches = [
            patch.object(router, name, side_effect=fn)
            for name, fn in handler_mocks.items()
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
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
        with (
            patch.object(router, "_do_research", side_effect=mock_research),
            patch.object(router, "_review_research", side_effect=mock_review),
        ):
            await router.run()

    # Find the agents message
    agents_msgs = [
        call.args[0]
        for call in emit.call_args_list
        if isinstance(call.args[0], dict) and call.args[0].get("type") == "agents"
    ]
    assert len(agents_msgs) == 1
    agents_list = agents_msgs[0]["agents"]
    agent_names = [a["name"] for a in agents_list]
    assert "memory_agent" in agent_names
    # Memory agent entry should have a color
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
        router.state.stage = Stage.REVIEW_RESEARCH

    async def mock_review():
        router.state.stage = Stage.DONE

    mock_shared = _mock_shared()
    with patch.dict(sys.modules, {"shared": mock_shared}):
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
