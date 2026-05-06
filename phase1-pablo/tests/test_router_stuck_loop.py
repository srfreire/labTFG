"""Tests for the stuck-stage safeguard in `Router._run_loop`.

When a work-stage handler swallows an agent exception and returns without
advancing `state.stage`, the outer loop must abort after
`_MAX_STAGE_RETRIES` consecutive non-progress iterations rather than spin
forever — otherwise non-interactive callers (eval harness, web server)
have no way to stop a persistently-failing agent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.router import PipelineState, Router, Stage


def _make_router(stage: Stage = Stage.RESEARCH) -> Router:
    state = PipelineState(
        stage=stage,
        problem="test problem",
        reports_dir=Path("."),
        run_id="00000000-0000-0000-0000-000000000000",
    )
    with patch.object(Router, "_init_memory_agent", return_value=None):
        return Router(
            client=AsyncMock(),
            state=state,
            search=MagicMock(),
            project_root=Path("."),
        )


@pytest.mark.asyncio
async def test_run_loop_aborts_when_stage_never_advances(monkeypatch):
    """A handler that always returns without advancing must trigger abort."""
    monkeypatch.setenv("DECISIONLAB_MAX_STAGE_RETRIES", "3")
    router = _make_router()

    call_count = 0

    async def stuck_handler():
        nonlocal call_count
        call_count += 1
        # never advance state — simulates an agent that keeps failing

    handlers = {Stage.RESEARCH: stuck_handler}

    # Stub out infrastructure side-effects.
    router._emit_agents = AsyncMock()
    router.state.save = AsyncMock()
    router._update_run = AsyncMock()
    router._tracer = MagicMock()
    router._tracer.events.return_value = [{"kind": "stage", "name": "research"}]

    with pytest.raises(RuntimeError, match=r"stuck at research.*3 consecutive"):
        await router._run_loop(handlers)

    assert call_count == 3, "Handler should have been retried up to the cap"


@pytest.mark.asyncio
async def test_run_loop_resets_counter_after_progress(monkeypatch):
    """A successful advance resets the stuck counter so a later stall is
    counted from zero — otherwise a noisy stage could spuriously trip the
    cap on a healthy run."""
    monkeypatch.setenv("DECISIONLAB_MAX_STAGE_RETRIES", "3")
    router = _make_router()

    research_calls = 0
    formalize_calls = 0

    async def research_handler():
        nonlocal research_calls
        research_calls += 1
        if research_calls < 2:
            return  # first call fails
        router.state.stage = Stage.FORMALIZE  # second call succeeds

    async def formalize_handler():
        nonlocal formalize_calls
        formalize_calls += 1
        # always fails — but counter was reset, so we should get the full
        # `max_retries` attempts here, not be aborted on the first try.

    # Pad the handler dict with no-op stages so dict lookup never KeyErrors.
    handlers = {
        Stage.RESEARCH: research_handler,
        Stage.FORMALIZE: formalize_handler,
    }

    router._emit_agents = AsyncMock()
    router.state.save = AsyncMock()
    router._update_run = AsyncMock()
    router._tracer = MagicMock()
    router._tracer.events.return_value = [{"kind": "stage", "name": "x"}]

    with pytest.raises(RuntimeError, match=r"stuck at formalize"):
        await router._run_loop(handlers)

    assert research_calls == 2
    assert formalize_calls == 3
