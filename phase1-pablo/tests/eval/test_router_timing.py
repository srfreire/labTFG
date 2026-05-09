"""Router._run_loop must wrap each handler in ``record_stage`` so the
TimingLog ends up with one entry per stage that executed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.eval.timing import start_timing
from decisionlab.router import Router, Stage


@pytest.mark.asyncio
async def test_run_loop_emits_stage_timings(monkeypatch):
    """Bypass Router.__init__ — feed a stub state + stub handler dict and
    confirm each handler call appears in the TimingLog."""

    timing = start_timing()

    # Construct a Router without going through __init__ (which needs an
    # AsyncAnthropic client + WebSearchPort + a writable run_id row).
    router = Router.__new__(Router)
    router._tracer = MagicMock()
    router._tracer.events = lambda: [{"event": "stub"}]
    router._tracer.stage = MagicMock()
    router._tracer.marker = MagicMock()
    router._send_event = AsyncMock()
    router._emit_agents = AsyncMock()
    router._stop_after_review = None
    router._update_run = AsyncMock()
    router.memory_agent = None
    router._stop_after = None
    router._services = MagicMock()
    router.state = None  # set below

    state = MagicMock()
    state.stage = Stage.RESEARCH
    state.save = AsyncMock()
    router.state = state

    advance_calls = {"n": 0}

    async def research_handler():
        # Simulate handler advancing the state machine to DONE so the loop exits.
        advance_calls["n"] += 1
        state.stage = Stage.DONE

    handlers = {Stage.RESEARCH: research_handler}

    await router._run_loop(handlers)

    assert advance_calls["n"] == 1
    stages = [s.stage for s in timing.stages]
    assert Stage.RESEARCH.value in stages
