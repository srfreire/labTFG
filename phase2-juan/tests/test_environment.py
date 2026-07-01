"""Tests for the generic environment."""

from __future__ import annotations

import json

import pytest
from simlab.environment import (
    Action,
    ActionRule,
    Agent,
    ConsumeEffect,
    Environment,
    Event,
    MoveEffect,
    NoopEffect,
    Position,
    Resource,
    ResourceRule,
)


class _AlwaysStay:
    def decide(self, perception: dict) -> Action:
        return Action("stay")

    def update(self, action, reward, new_perception):
        pass

    def get_state(self) -> dict:
        return {"dummy": True}


class _AlwaysRight:
    def decide(self, perception: dict) -> Action:
        return Action("right")

    def update(self, action, reward, new_perception):
        pass

    def get_state(self) -> dict:
        return {"direction": "right"}


class _AlwaysEat:
    def decide(self, perception: dict) -> Action:
        return Action("eat")

    def update(self, action, reward, new_perception):
        pass

    def get_state(self) -> dict:
        return {}


class _LearningModel:
    """A model whose state changes on update, so pre != post."""

    def __init__(self):
        self.counter = 0

    def decide(self, perception: dict) -> Action:
        return Action("stay")

    def update(self, action, reward, new_perception):
        self.counter += 1

    def get_state(self) -> dict:
        return {"counter": self.counter}


class _EnergyDepletingModel:
    def __init__(self, energy: float = 1.0):
        self.energy = energy

    def decide(self, perception: dict) -> Action:
        return Action("move")

    def update(self, action, reward, new_perception):
        self.energy += reward

    def get_state(self) -> dict:
        return {"energy": self.energy}


def _basic_actions():
    return [
        ActionRule("right", MoveEffect(dx=1, dy=0)),
        ActionRule("left", MoveEffect(dx=-1, dy=0)),
        ActionRule("up", MoveEffect(dx=0, dy=-1)),
        ActionRule("down", MoveEffect(dx=0, dy=1)),
        ActionRule("stay", NoopEffect()),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]


def _food_rule():
    return [
        ResourceRule(
            type="food",
            properties={"palatability": (0.1, 1.0)},
            count=2,
            regenerate=True,
        )
    ]


def test_environment_init():
    env = Environment(10, 10, actions=_basic_actions(), resources=[])
    assert env.width == 10 and env.height == 10


def test_spawn_initial_resources():
    env = Environment(5, 5, actions=[], resources=_food_rule(), seed=42)
    state = env.get_state()
    assert len(state["resources"]) == 2
    assert all(r.get("type") == "food" for r in state["resources"])


def test_add_agent():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    assert len(env.get_state()["agents"]) == 1


def test_agent_moves_on_action():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(
        Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight())
    )
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 1 and state["agents"][0]["y"] == 0


def test_agent_clamps_at_wall():
    actions = [ActionRule("left", MoveEffect(dx=-1, dy=0))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysLeft:
        def decide(self, perception):
            return Action("left")

        def update(self, action, reward, new_perception):
            pass

        def get_state(self):
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysLeft()))
    env.step()
    assert env.get_state()["agents"][0]["x"] == 0


def test_unknown_action_returns_zero_reward():
    env = Environment(5, 5, actions=[], resources=[])

    class _BadAction:
        def decide(self, perception):
            return Action("fly")

        def update(self, action, reward, new_perception):
            pass

        def get_state(self):
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_BadAction()))
    events = env.step()
    assert events[0].outcome["action_result"] == {"error": "unknown_action"}


def test_move_reward_propagates():
    actions = [ActionRule("walk", MoveEffect(dx=1, dy=0, reward=-0.01))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysWalk:
        def decide(self, perception):
            return Action("walk")

        def update(self, action, reward, new_perception):
            pass

        def get_state(self):
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysWalk()))
    events = env.step()
    assert events[0].outcome["reward"] == -0.01


def test_consume_resource():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[], seed=42)
    env.add_resource(
        Resource(
            id="f1",
            position=Position(0, 0),
            properties={"type": "food", "palatability": 0.5},
        )
    )
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is True
    assert events[0].outcome["reward"] == 1.0


def test_consume_nothing_returns_zero():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is False
    assert events[0].outcome["reward"] == 0.0


def test_resource_regenerates():
    food_rule = ResourceRule(
        type="food", properties={"palatability": (0.1, 1.0)}, count=0, regenerate=True
    )
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(
        Resource(
            id="f1",
            position=Position(0, 0),
            properties={"type": "food", "palatability": 0.5},
        )
    )
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    assert len(env.get_state()["resources"]) == 1


def test_consume_no_regenerate():
    food_rule = ResourceRule(type="food", properties={}, count=0, regenerate=False)
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(
        Resource(id="f1", position=Position(0, 0), properties={"type": "food"})
    )
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    assert len(env.get_state()["resources"]) == 0


def test_consume_wrong_type():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[])
    env.add_resource(
        Resource(id="w1", position=Position(0, 0), properties={"type": "water"})
    )
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is False


def test_noop_action():
    actions = [ActionRule("rest", NoopEffect(reward=0.1))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysRest:
        def decide(self, perception):
            return Action("rest")

        def update(self, action, reward, new_perception):
            pass

        def get_state(self):
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRest()))
    events = env.step()
    assert events[0].outcome["reward"] == 0.1


def test_perception_keys():
    food_rule = ResourceRule(
        type="food", properties={"palatability": (0.1, 1.0)}, count=1
    )
    env = Environment(5, 5, actions=_basic_actions(), resources=[food_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    assert set(perception.keys()) == {
        "x",
        "y",
        "grid_width",
        "grid_height",
        "step",
        "resources",
        "last_action_result",
    }


def test_perception_resources_grouped_by_type():
    food_rule = ResourceRule(type="food", properties={}, count=2)
    water_rule = ResourceRule(type="water", properties={}, count=1)
    env = Environment(5, 5, actions=[], resources=[food_rule, water_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    assert len(perception["resources"]["food"]) == 2
    assert len(perception["resources"]["water"]) == 1


def test_step_returns_events_with_outcome():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert len(events) == 1
    assert isinstance(events[0], Event)
    assert "action_result" in events[0].outcome
    assert "reward" in events[0].outcome
    assert "model_state" in events[0].outcome
    assert events[0].outcome["model_state"] == {"dummy": True}


def test_run_n_steps():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.run(10)
    assert len(events) == 10


def test_run_stops_when_agent_energy_depletes():
    env = Environment(
        5,
        5,
        actions=[ActionRule("move", MoveEffect(dx=1, dy=0, reward=-1.0))],
        resources=[],
    )
    env.add_agent(
        Agent(
            id="a1",
            position=Position(0, 0),
            decision_model=_EnergyDepletingModel(energy=1.0),
        )
    )

    events = env.run(10)

    assert len(events) == 1
    assert env.is_finished()
    assert env.get_state()["agents"][0]["alive"] is False
    assert events[0].outcome["model_state"]["energy"] == 0.0
    assert events[0].outcome["action_result"] == {
        "terminated": True,
        "termination_reason": "energy_depleted",
    }


def test_is_finished():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_agent(
        Agent(
            id="a1", position=Position(0, 0), decision_model=_AlwaysStay(), alive=False
        )
    )
    assert env.is_finished()
    env.add_agent(Agent(id="a2", position=Position(0, 0), decision_model=_AlwaysStay()))
    assert not env.is_finished()


def test_get_spec():
    actions = [
        ActionRule("move_up", MoveEffect(dx=0, dy=-1)),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]
    resources = [
        ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=5)
    ]
    env = Environment(5, 5, actions=actions, resources=resources)
    spec = env.get_spec()
    assert set(spec["available_actions"]) == {"move_up", "eat"}
    assert spec["resource_types"]["food"]["count"] == 5
    assert spec["grid"] == {"width": 5, "height": 5}


def test_seed_determinism():
    def run_sim(seed):
        food_rule = ResourceRule(
            type="food",
            properties={"palatability": (0.1, 1.0)},
            count=0,
            regenerate=True,
        )
        actions = [
            ActionRule("right", MoveEffect(dx=1, dy=0)),
            ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
        ]
        env = Environment(5, 5, actions=actions, resources=[food_rule], seed=seed)
        env.add_resource(
            Resource(
                id="f1",
                position=Position(1, 0),
                properties={"type": "food", "palatability": 0.5},
            )
        )
        env.add_agent(
            Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight())
        )
        return env.run(10)

    events_a = run_sim(42)
    events_b = run_sim(42)
    for a, b in zip(events_a, events_b, strict=False):
        assert a.outcome == b.outcome


def test_get_state_is_serializable():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.step()
    json.dumps(env.get_state())


def test_duplicate_action_names_raises():
    actions = [
        ActionRule("move", MoveEffect(dx=1, dy=0)),
        ActionRule("move", MoveEffect(dx=-1, dy=0)),
    ]
    with pytest.raises(ValueError, match="Duplicate action names"):
        Environment(5, 5, actions=actions, resources=[])


def test_duplicate_resource_types_raises():
    resources = [ResourceRule(type="food", count=1), ResourceRule(type="food", count=2)]
    with pytest.raises(ValueError, match="Duplicate resource types"):
        Environment(5, 5, actions=[], resources=resources)


def test_step_populates_decision_trace_fields():
    """Events from step() include perception, pre_state, and available_actions."""
    env = Environment(5, 5, actions=_basic_actions(), resources=_food_rule(), seed=42)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    e = events[0]
    assert "x" in e.perception
    assert "y" in e.perception
    assert "resources" in e.perception
    assert e.perception["x"] == 0
    assert e.pre_state == {"dummy": True}
    assert set(e.available_actions) == {"right", "left", "up", "down", "stay", "eat"}


def test_pre_state_captures_before_update():
    """pre_state reflects model state BEFORE update; outcome.model_state reflects AFTER."""
    env = Environment(5, 5, actions=[ActionRule("stay", NoopEffect())], resources=[])
    env.add_agent(
        Agent(id="a1", position=Position(0, 0), decision_model=_LearningModel())
    )
    events = env.step()
    e = events[0]
    assert e.pre_state["counter"] == 0
    assert e.outcome["model_state"]["counter"] == 1


def test_event_default_fields_backward_compatible():
    """Events created without new fields default to empty."""
    e = Event(step=0, agent_id="a1", action=Action("stay"))
    assert e.perception == {}
    assert e.pre_state == {}
    assert e.available_actions == []
