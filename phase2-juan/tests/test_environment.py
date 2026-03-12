"""Tests for the generic environment — zero Phase 1 imports."""
from __future__ import annotations

import json

import pytest

from simlab.environment import (
    Action,
    ActionRule,
    Agent,
    ConsumeEffect,
    DecisionModel,
    Environment,
    Event,
    MoveEffect,
    NoopEffect,
    Position,
    Resource,
    ResourceRule,
)


# --- Dummy models ---

class _AlwaysStay:
    def decide(self, perception: dict) -> Action:
        return Action("stay")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        pass

    def get_state(self) -> dict:
        return {"dummy": True}


class _AlwaysRight:
    def decide(self, perception: dict) -> Action:
        return Action("right")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        pass

    def get_state(self) -> dict:
        return {"direction": "right"}


class _AlwaysEat:
    def decide(self, perception: dict) -> Action:
        return Action("eat")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        pass

    def get_state(self) -> dict:
        return {}


# --- Helpers ---

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
    return [ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=2, regenerate=True)]


# --- Dataclasses ---

def test_position_dataclass():
    p = Position(1, 2)
    assert p.x == 1
    assert p.y == 2


def test_action_dataclass():
    a = Action("move", {"direction": "up"})
    assert a.name == "move"
    assert a.params == {"direction": "up"}


def test_action_default_params():
    a = Action("stay")
    assert a.params == {}


def test_event_dataclass():
    a = Action("stay")
    e = Event(step=0, agent_id="a1", action=a)
    assert e.step == 0
    assert e.agent_id == "a1"
    assert e.outcome == {}


def test_resource_dataclass():
    r = Resource(id="r1", position=Position(2, 3), properties={"type": "food"})
    assert r.id == "r1"
    assert r.position.x == 2
    assert r.properties["type"] == "food"


# --- Protocol ---

def test_decision_model_protocol_satisfied():
    model = _AlwaysStay()
    assert isinstance(model, DecisionModel)


# --- Effect types and config dataclasses ---

def test_move_effect_dataclass():
    e = MoveEffect(dx=1, dy=0)
    assert e.dx == 1
    assert e.reward == 0.0


def test_move_effect_custom_reward():
    e = MoveEffect(dx=0, dy=-1, reward=-0.01)
    assert e.reward == -0.01


def test_consume_effect_dataclass():
    e = ConsumeEffect(resource_type="food", reward=1.0)
    assert e.resource_type == "food"


def test_noop_effect_dataclass():
    e = NoopEffect()
    assert e.reward == 0.0


def test_action_rule_dataclass():
    rule = ActionRule(name="move_up", effect=MoveEffect(dx=0, dy=-1))
    assert rule.name == "move_up"
    assert isinstance(rule.effect, MoveEffect)


def test_resource_rule_dataclass():
    rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=5)
    assert rule.type == "food"
    assert rule.regenerate is True


def test_resource_rule_defaults():
    rule = ResourceRule(type="water", count=3)
    assert rule.properties == {}
    assert rule.regenerate is True


# --- Environment init and resource spawning ---

def test_environment_init():
    env = Environment(10, 10, actions=_basic_actions(), resources=[])
    assert env.width == 10
    assert env.height == 10


def test_spawn_initial_resources():
    env = Environment(5, 5, actions=[], resources=_food_rule(), seed=42)
    state = env.get_state()
    assert len(state["resources"]) == 2
    assert all(r.get("type") == "food" for r in state["resources"])


def test_add_agent():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    state = env.get_state()
    assert len(state["agents"]) == 1


def test_add_resource_manual():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_resource(Resource(id="f1", position=Position(2, 3), properties={"type": "food", "palatability": 0.8}))
    state = env.get_state()
    assert len(state["resources"]) == 1


# --- Movement ---

def test_agent_moves_on_action():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 1
    assert state["agents"][0]["y"] == 0


def test_agent_clamps_at_wall():
    actions = [ActionRule("left", MoveEffect(dx=-1, dy=0))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysLeft:
        def decide(self, perception: dict) -> Action:
            return Action("left")
        def update(self, action, reward, new_perception): pass
        def get_state(self) -> dict: return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysLeft()))
    env.step()
    assert env.get_state()["agents"][0]["x"] == 0


def test_unknown_action_returns_zero_reward():
    env = Environment(5, 5, actions=[], resources=[])

    class _BadAction:
        def decide(self, perception: dict) -> Action: return Action("fly")
        def update(self, action, reward, new_perception): pass
        def get_state(self) -> dict: return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_BadAction()))
    events = env.step()
    assert events[0].outcome["action_result"] == {"error": "unknown_action"}


def test_move_reward_propagates_to_event():
    actions = [ActionRule("walk", MoveEffect(dx=1, dy=0, reward=-0.01))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysWalk:
        def decide(self, perception: dict) -> Action:
            return Action("walk")
        def update(self, action, reward, new_perception): pass
        def get_state(self) -> dict: return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysWalk()))
    events = env.step()
    assert events[0].outcome["reward"] == -0.01


# --- Resource consumption ---

def test_consume_resource():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food", "palatability": 0.5}))
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
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=0, regenerate=True)
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food", "palatability": 0.5}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    assert len(env.get_state()["resources"]) == 1


def test_consume_no_regenerate():
    food_rule = ResourceRule(type="food", properties={}, count=0, regenerate=False)
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food"}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    assert len(env.get_state()["resources"]) == 0


def test_consume_wrong_type_at_same_position():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[])
    env.add_resource(Resource(id="w1", position=Position(0, 0), properties={"type": "water"}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is False
    assert len(env.get_state()["resources"]) == 1


def test_noop_action():
    actions = [ActionRule("rest", NoopEffect(reward=0.1))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysRest:
        def decide(self, perception: dict) -> Action: return Action("rest")
        def update(self, action, reward, new_perception): pass
        def get_state(self) -> dict: return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRest()))
    events = env.step()
    assert events[0].outcome["reward"] == 0.1


# --- Perception ---

def test_perception_keys():
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=1)
    env = Environment(5, 5, actions=_basic_actions(), resources=[food_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    expected = {"x", "y", "grid_width", "grid_height", "step", "resources", "last_action_result"}
    assert set(perception.keys()) == expected


def test_perception_resources_grouped_by_type():
    food_rule = ResourceRule(type="food", properties={}, count=2)
    water_rule = ResourceRule(type="water", properties={}, count=1)
    env = Environment(5, 5, actions=[], resources=[food_rule, water_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    assert "food" in perception["resources"]
    assert "water" in perception["resources"]
    assert len(perception["resources"]["food"]) == 2
    assert len(perception["resources"]["water"]) == 1


def test_manual_resource_unregistered_type_visible():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_resource(Resource(id="g1", position=Position(1, 1), properties={"type": "gold", "value": 100}))
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    assert "gold" in perception["resources"]
    assert len(perception["resources"]["gold"]) == 1


# --- Step and run ---

def test_step_outcome_has_action_result():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert "action_result" in events[0].outcome
    assert "reward" in events[0].outcome
    assert "model_state" in events[0].outcome


def test_step_injects_last_action_result():
    results = []

    class _CaptureUpdate:
        def decide(self, perception: dict) -> Action: return Action("stay")
        def update(self, action, reward, new_perception):
            results.append(new_perception.get("last_action_result"))
        def get_state(self) -> dict: return {}

    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_CaptureUpdate()))
    env.step()
    assert results[0] == {}


def test_step_returns_events():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert len(events) == 1
    assert isinstance(events[0], Event)


def test_step_increments_counter():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.step()
    assert env.get_state()["step"] == 1


def test_step_records_model_state():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert events[0].outcome["model_state"] == {"dummy": True}


def test_run_n_steps():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.run(10)
    assert len(events) == 10


def test_is_finished_when_all_dead():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay(), alive=False))
    assert env.is_finished()


def test_is_finished_false_when_alive():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    assert not env.is_finished()


# --- get_spec ---

def test_get_spec():
    actions = [
        ActionRule("move_up", MoveEffect(dx=0, dy=-1)),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]
    resources = [ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=5)]
    env = Environment(5, 5, actions=actions, resources=resources)
    spec = env.get_spec()
    assert set(spec["available_actions"]) == {"move_up", "eat"}
    assert "food" in spec["resource_types"]
    assert spec["resource_types"]["food"]["count"] == 5
    assert spec["grid"] == {"width": 5, "height": 5}


# --- Determinism and serialization ---

def test_seed_determinism():
    def run_sim(seed):
        food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=0, regenerate=True)
        actions = [
            ActionRule("right", MoveEffect(dx=1, dy=0)),
            ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
        ]
        env = Environment(5, 5, actions=actions, resources=[food_rule], seed=seed)
        env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.5}))
        env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
        return env.run(10)
    events_a = run_sim(42)
    events_b = run_sim(42)
    for a, b in zip(events_a, events_b):
        assert a.outcome == b.outcome


def test_get_state_is_serializable():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.add_resource(Resource(id="f1", position=Position(2, 2), properties={"type": "food"}))
    env.step()
    json.dumps(env.get_state())


# --- Validation ---

def test_duplicate_action_names_raises():
    actions = [
        ActionRule("move", MoveEffect(dx=1, dy=0)),
        ActionRule("move", MoveEffect(dx=-1, dy=0)),
    ]
    with pytest.raises(ValueError, match="Duplicate action names"):
        Environment(5, 5, actions=actions, resources=[])


def test_duplicate_resource_types_raises():
    resources = [
        ResourceRule(type="food", count=1),
        ResourceRule(type="food", count=2),
    ]
    with pytest.raises(ValueError, match="Duplicate resource types"):
        Environment(5, 5, actions=[], resources=resources)
