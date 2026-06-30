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


def test_get_simulation_events_summarizes_heavy_payload():
    # Few events, but each carries a heavy model_state (e.g. dual Q-tables) — the
    # count guard (500) would pass them through, yet the full dump would blow the
    # context window. The size guard must fall back to the summary instead.
    big_q_table = {f"state_{i}": [0.1, 0.2, 0.3] for i in range(2000)}
    events = [
        Event(
            step=i,
            agent_id=f"agent_{i % 3}",
            action=Action(name="move_up"),
            outcome={"action_result": {}, "reward": 0.0, "model_state": big_q_table},
        )
        for i in range(20)
    ]
    _, registry = build_simulation_tools(events)
    result = json.loads(asyncio.run(registry["get_simulation_events"]({})))
    assert "total_events" in result
    assert result["total_events"] == 20


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


def test_get_agent_trajectory_compact_drops_heavy_fields():
    """Compact mode (default) must omit perception and full model_state."""
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_0"}))
    )
    sample = result[0]
    assert "perception" not in sample
    assert "pre_state" not in sample
    assert "available_actions" not in sample
    assert "outcome" not in sample  # no nested model_state blob
    assert sample["action"] == "move_up"  # action is a string, not a dict
    assert "energy" in sample  # energy is surfaced flat


def test_get_agent_trajectory_compact_preserves_action_params():
    """Parametric actions must keep their params so distinct decisions don't collapse."""
    events = [
        Event(
            step=0,
            agent_id="agent_0",
            action=Action(name="move", params={"direction": "north"}),
            outcome={"reward": 0.0, "action_result": {}, "model_state": {}},
        ),
        Event(
            step=1,
            agent_id="agent_0",
            action=Action(name="move", params={}),
            outcome={"reward": 0.0, "action_result": {}, "model_state": {}},
        ),
    ]
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_0"}))
    )
    assert result[0]["action_params"] == {"direction": "north"}
    assert "action_params" not in result[1]  # empty params are omitted


def test_get_agent_trajectory_full_includes_everything():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(
            registry["get_agent_trajectory"]({"agent_id": "agent_0", "detail": "full"})
        )
    )
    assert result[0]["outcome"]["model_state"]["energy"] == 50.0
    assert result[0]["action"] == {"name": "move_up", "params": {}}


def test_get_agent_trajectory_summary():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(
            registry["get_agent_trajectory"](
                {"agent_id": "agent_0", "detail": "summary"}
            )
        )
    )
    # Field names mirror the Tracker Output Schema for direct copy.
    assert result["agent_id"] == "agent_0"
    assert result["steps_survived"] == 5
    assert result["resources_consumed"] == 0
    assert result["steps_range"] == [0, 4]
    assert result["actions"]["move_up"] == 3
    assert result["actions"]["eat"] == 2
    assert result["energy"]["initial"] == 50.0
    assert result["energy"]["final"] == 46.0


def test_get_agent_trajectory_summary_unknown_agent_keeps_agent_id():
    """Empty summary must still echo the queried agent_id."""
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(
            registry["get_agent_trajectory"]({"agent_id": "ghost", "detail": "summary"})
        )
    )
    assert result == {"agent_id": "ghost", "steps_survived": 0, "resources_consumed": 0}


def test_get_agent_trajectory_summary_tolerates_none_reward():
    """Reward stored as None must not crash the sum aggregation."""
    events = [
        Event(
            step=0,
            agent_id="agent_0",
            action=Action(name="move"),
            outcome={"reward": None, "action_result": {}, "model_state": {}},
        ),
        Event(
            step=1,
            agent_id="agent_0",
            action=Action(name="eat"),
            outcome={"reward": 1.5, "action_result": {}, "model_state": {}},
        ),
    ]
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(
            registry["get_agent_trajectory"](
                {"agent_id": "agent_0", "detail": "summary"}
            )
        )
    )
    assert result["total_reward"] == 1.5


def test_get_agent_trajectory_slice():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(
            registry["get_agent_trajectory"](
                {"agent_id": "agent_0", "from_step": 2, "to_step": 4}
            )
        )
    )
    assert [e["step"] for e in result] == [2, 3]


def test_get_event_window_caps_radius():
    """Radius > 30 is silently clamped to prevent context blowup."""
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_event_window"]({"center_step": 2, "radius": 9999}))
    )
    assert result["radius"] == 30


def test_get_event_window_null_radius_uses_default():
    """radius=null (LLM explicitly passes None) must fall back to the default."""
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_event_window"]({"center_step": 2, "radius": None}))
    )
    assert result["radius"] == 10


def test_get_event_window_negative_radius_uses_default():
    """Negative radius would produce an inverted/empty window; floor to default."""
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_event_window"]({"center_step": 2, "radius": -5}))
    )
    assert result["radius"] == 10
    assert len(result["events"]) > 0  # non-empty window confirms the fix


def test_get_event_window_compact_by_default():
    events = _make_events()
    _, registry = build_simulation_tools(events)
    result = json.loads(
        asyncio.run(registry["get_event_window"]({"center_step": 2, "radius": 5}))
    )
    # Compact events shouldn't carry perception/pre_state blobs
    assert all("perception" not in e for e in result["events"])
    assert all(isinstance(e["action"], str) for e in result["events"])


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
