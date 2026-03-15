"""Tests for the Tracker agent — helpers, tools, and integration."""
import asyncio
import json

from simlab.environment import Action, Event
from simlab.tracker import _event_to_dict, _summarize_events, _build_tools


def _make_event(step: int, agent_id: str, action_name: str, reward: float = 0.0) -> Event:
    return Event(
        step=step,
        agent_id=agent_id,
        action=Action(name=action_name),
        outcome={"action_result": {}, "reward": reward, "model_state": {"energy": 50.0 - step}},
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
        events.append(_make_event(step, "agent_0", "move_up" if step % 2 == 0 else "eat", reward=float(step % 2)))
        events.append(_make_event(step, "agent_1", "move_down"))
    return events


def test_get_simulation_events_returns_all():
    events = _make_events()
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_simulation_events"]({})))
    assert len(result) == 10


def test_get_simulation_events_summarizes_large():
    events = [_make_event(i, f"agent_{i % 3}", "move_up") for i in range(501)]
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_simulation_events"]({})))
    assert "total_events" in result
    assert result["total_events"] == 501


def test_get_agent_trajectory():
    events = _make_events()
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_0"})))
    assert len(result) == 5
    assert all(e["agent_id"] == "agent_0" for e in result)


def test_get_agent_trajectory_unknown_agent():
    events = _make_events()
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_agent_trajectory"]({"agent_id": "agent_99"})))
    assert result == []


def test_get_agent_state():
    events = _make_events()
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_agent_state"]({"agent_id": "agent_0", "step": 2})))
    assert result == {"energy": 48.0}


def test_get_agent_state_not_found():
    events = _make_events()
    _, registry = _build_tools(events)
    result = json.loads(asyncio.run(registry["get_agent_state"]({"agent_id": "agent_0", "step": 99})))
    assert "error" in result


# --- Integration tests ---

import os

import anthropic
import pytest

from simlab.tracker import Tracker
from simlab.environment import (
    Environment, Agent, Position, ActionRule, ResourceRule,
    MoveEffect, ConsumeEffect,
)


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
@pytest.mark.integration
def test_tracker_observes_simulation():
    env = Environment(
        width=5, height=5,
        actions=[
            ActionRule("move_up", MoveEffect(dx=0, dy=-1)),
            ActionRule("move_down", MoveEffect(dx=0, dy=1)),
            ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
        ],
        resources=[ResourceRule(type="food", count=3, regenerate=True)],
        seed=42,
    )

    class DummyModel:
        def decide(self, perception):
            return Action(name="move_down")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self):
            return {"mood": "hungry"}

    env.add_agent(Agent(id="agent_0", position=Position(2, 2), decision_model=DummyModel()))
    events = env.run(steps=20)

    client = anthropic.AsyncAnthropic()
    tracker = Tracker(client=client)
    result = asyncio.run(tracker.run("Observa esta simulacion y reporta que paso.", events))

    data = json.loads(result)
    assert "summary" in data
    assert "trajectories" in data
    assert "episodes" in data
    assert "agent_0" in data["trajectories"]
