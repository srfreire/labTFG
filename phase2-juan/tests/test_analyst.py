"""Integration tests for the Analyst agent (requires ANTHROPIC_API_KEY)."""
import asyncio
import json
import os

import anthropic
import pytest

from simlab.analyst import Analyst
from simlab.environment import (
    Environment, Agent, Position, Action, ActionRule, ResourceRule,
    MoveEffect, ConsumeEffect,
)


pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)


def _run_simulation():
    """Build a small environment, run it, return events."""
    env = Environment(
        width=5, height=5,
        actions=[
            ActionRule("move_up", MoveEffect(dx=0, dy=-1)),
            ActionRule("move_down", MoveEffect(dx=0, dy=1)),
            ActionRule("move_left", MoveEffect(dx=-1, dy=0)),
            ActionRule("move_right", MoveEffect(dx=1, dy=0)),
            ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
        ],
        resources=[ResourceRule(type="food", count=3, regenerate=True)],
        seed=42,
    )

    class HungryAgent:
        def __init__(self):
            self.hunger = 0
        def decide(self, perception):
            self.hunger += 1
            food = perception.get("resources", {}).get("food", [])
            for f in food:
                if f["x"] == perception["x"] and f["y"] == perception["y"]:
                    return Action(name="eat")
            if food:
                fx, fy = food[0]["x"], food[0]["y"]
                if fx > perception["x"]: return Action(name="move_right")
                if fx < perception["x"]: return Action(name="move_left")
                if fy > perception["y"]: return Action(name="move_down")
                if fy < perception["y"]: return Action(name="move_up")
            return Action(name="move_up")
        def update(self, action, reward, new_perception):
            if reward > 0: self.hunger = 0
        def get_state(self):
            return {"hunger": self.hunger}

    env.add_agent(Agent(id="agent_0", position=Position(0, 0), decision_model=HungryAgent()))
    env.add_agent(Agent(id="agent_1", position=Position(4, 4), decision_model=HungryAgent()))
    return env.run(steps=20)


FAKE_TRACKER_OUTPUT = json.dumps({
    "summary": "Simulation of 20 steps with 2 agents foraging for food.",
    "trajectories": {
        "agent_0": {"steps_survived": 20, "resources_consumed": 3, "actions": {"move_right": 5, "move_down": 4, "eat": 3, "move_up": 8}},
        "agent_1": {"steps_survived": 20, "resources_consumed": 2, "actions": {"move_left": 8, "move_up": 6, "eat": 2, "move_down": 4}},
    },
    "episodes": [
        {"agent": "agent_0", "type": "foraging_success", "step": 3, "description": "Found food at step 3"},
        {"agent": "agent_1", "type": "foraging_failure", "steps": [0, 8], "description": "Searched for 8 steps before finding food"},
    ],
})


@pytest.mark.integration
def test_analyst_produces_valid_output():
    events = _run_simulation()
    client = anthropic.AsyncAnthropic()
    analyst = Analyst(client=client)
    result = asyncio.run(analyst.run(
        "Analiza los datos y encuentra patrones de comportamiento.",
        FAKE_TRACKER_OUTPUT,
        events,
    ))

    data = json.loads(result)
    assert "patterns" in data
    assert "comparisons" in data
    assert "metrics" in data
    assert isinstance(data["patterns"], list)
    assert isinstance(data["comparisons"], list)
