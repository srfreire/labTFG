"""Runtime-budget tests for LLM agents.

These tests protect the web demo from accidental prompt/tool bloat: the agents
should prefer focused tool use and bounded output unless a caller opts in.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from simlab.environment import Action, Event


def _mock_response(text: str = "{}"):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


@pytest.mark.asyncio
async def test_tracker_uses_demo_safe_runtime_budget():
    from simlab.tracker import Tracker

    captured = {}

    async def fake_loop(**kwargs):
        captured.update(kwargs)
        return _mock_response('{"summary": "", "trajectories": {}, "episodes": []}')

    event = Event(step=0, agent_id="a1", action=Action(name="stay"))

    with patch("simlab.tracker.run_agent_loop", side_effect=fake_loop):
        tracker = Tracker(client=MagicMock())
        await tracker.run("observa", [event])

    assert captured["max_iterations"] <= 8
    assert captured["max_tokens"] <= 2048
    assert "Tool budget" in captured["system"]


@pytest.mark.asyncio
async def test_analyst_uses_focused_runtime_budget():
    from simlab.analyst import Analyst

    captured = {}

    async def fake_loop(**kwargs):
        captured.update(kwargs)
        return _mock_response('{"patterns": [], "comparisons": [], "metrics": {}}')

    event = Event(step=0, agent_id="a1", action=Action(name="stay"))

    with patch("simlab.analyst.run_agent_loop", side_effect=fake_loop):
        analyst = Analyst(client=MagicMock(), storage=MagicMock(), db=MagicMock())
        await analyst.run("analiza", "tracker", [event])

    assert captured["max_iterations"] <= 8
    assert captured["max_tokens"] <= 3072
    assert "Tool budget" in captured["system"]
    assert "get_agent_state aggressively" not in captured["system"]


@pytest.mark.asyncio
async def test_architect_uses_small_generation_budget():
    from simlab.architect import Architect

    captured = {}

    async def fake_loop(**kwargs):
        captured.update(kwargs)
        return _mock_response(
            '{"grid": {"width": 1, "height": 1}, "actions": [], "resources": []}'
        )

    with patch("simlab.architect.run_agent_loop", side_effect=fake_loop):
        architect = Architect(client=MagicMock())
        await architect.run("grid 1x1")

    assert captured["max_iterations"] <= 6
    assert captured["max_tokens"] <= 1536
