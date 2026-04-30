"""Unit tests for Tracker helpers and simulation tools."""

import asyncio
import json

from simlab.environment import Action, Event
from simlab.tools import _event_to_dict, _summarize_events, build_simulation_tools


def _make_event(
    step: int, agent_id: str, action_name: str, reward: float = 0.0
) -> Event:
    return Event(
        step=step,
        agent_id=agent_id,
        action=Action(name=action_name),
        outcome={
            "action_result": {},
            "reward": reward,
            "model_state": {"energy": 50.0 - step},
        },
    )


# --- Helper tests ---


def test_event_to_dict():
    event = _make_event(5, "agent_0", "eat", reward=1.0)
    d = _event_to_dict(event)
    assert d["step"] == 5
    assert d["agent_id"] == "agent_0"
    assert d["action"] == {"name": "eat", "params": {}}
    assert d["outcome"]["reward"] == 1.0
    assert d["outcome"]["model_state"]["energy"] == 45.0


def test_summarize_events():
    events = [
        _make_event(0, "agent_0", "move_up"),
        _make_event(0, "agent_1", "eat", reward=1.0),
        _make_event(1, "agent_0", "eat", reward=1.0),
        _make_event(1, "agent_1", "move_down"),
    ]
    summary = _summarize_events(events)
    assert summary["total_events"] == 4
    assert summary["total_steps"] == 2
    assert set(summary["agents"]) == {"agent_0", "agent_1"}
    assert summary["events_per_agent"]["agent_0"] == 2
    assert summary["action_counts"]["eat"] == 2


def test_summarize_events_empty():
    summary = _summarize_events([])
    assert summary["total_events"] == 0
    assert summary["total_steps"] == 0


# --- Tool factory tests ---


def _make_events() -> list[Event]:
    events = []
    for step in range(5):
        events.append(
            _make_event(
                step,
                "agent_0",
                "move_up" if step % 2 == 0 else "eat",
                reward=float(step % 2),
            )
        )
        events.append(_make_event(step, "agent_1", "move_down"))
    return events


def test_get_simulation_events_returns_all():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(asyncio.run(registry["get_simulation_events"]({})))
    assert len(result) == 10


def test_get_simulation_events_summarizes_large():
    events = [_make_event(i, f"agent_{i % 3}", "move_up") for i in range(501)]
    _, registry = build_simulation_tools(events)
    result = json.loads(asyncio.run(registry["get_simulation_events"]({})))
    assert "total_events" in result
    assert result["total_events"] == 501


def test_get_agent_trajectory():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_0"}))
    )
    assert len(result) == 5
    assert all(e["agent_id"] == "agent_0" for e in result)


def test_get_agent_trajectory_unknown_agent():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_99"}))
    )
    assert result == []


def test_get_agent_state():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_state"]({"agent_id": "agent_0", "step": 2}))
    )
    assert result == {"energy": 48.0}


def test_get_agent_state_not_found():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_state"]({"agent_id": "agent_0", "step": 99}))
    )
    assert "error" in result
