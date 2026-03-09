"""Tests for the generic environment — zero Phase 1 imports."""
from __future__ import annotations

from simlab.environment import (
    Action,
    Agent,
    DecisionModel,
    Environment,
    Event,
    Position,
    Resource,
)


# --- Dummy model for tests ---

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


# --- Dataclass tests ---

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


# --- Protocol test ---

def test_decision_model_protocol_satisfied():
    model = _AlwaysStay()
    assert isinstance(model, DecisionModel)


# --- Environment init tests ---

def test_environment_init():
    env = Environment(10, 10)
    assert env.width == 10
    assert env.height == 10


def test_add_agent():
    env = Environment(5, 5)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    state = env.get_state()
    assert len(state["agents"]) == 1


def test_add_resource():
    env = Environment(5, 5)
    res = Resource(id="f1", position=Position(2, 3), properties={"type": "food", "palatability": 0.8})
    env.add_resource(res)
    state = env.get_state()
    assert len(state["resources"]) == 1


# --- Step and run tests ---

def test_step_returns_events():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert len(events) == 1
    assert isinstance(events[0], Event)


def test_step_increments_counter():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.step()
    assert env.get_state()["step"] == 1


def test_run_n_steps():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.run(10)
    assert len(events) == 10


def test_is_finished_when_all_dead():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay(), alive=False))
    assert env.is_finished()


def test_is_finished_false_when_alive():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    assert not env.is_finished()


# --- Movement tests ---

def test_agent_moves_on_action():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 1
    assert state["agents"][0]["y"] == 0


def test_agent_clamps_at_wall():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))

    class _AlwaysLeft:
        def decide(self, perception: dict) -> Action:
            return Action("left")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env._agents[0].decision_model = _AlwaysLeft()
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 0


# --- Food collection tests ---

def test_food_collection():
    env = Environment(5, 5, food_regenerate=False)
    env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.5}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
    events = env.step()
    assert events[0].outcome["ate_food"] is True


def test_food_regenerates():
    env = Environment(5, 5, seed=42, food_regenerate=True)
    env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.5}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
    env.step()
    state = env.get_state()
    assert len(state["resources"]) == 1


# --- Determinism test ---

def test_seed_determinism():
    def run_sim(seed):
        env = Environment(5, 5, seed=seed, food_regenerate=True)
        env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.5}))
        env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
        return env.run(10)

    events_a = run_sim(42)
    events_b = run_sim(42)
    for a, b in zip(events_a, events_b):
        assert a.outcome == b.outcome


# --- State serialization test ---

def test_get_state_is_serializable():
    import json
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.add_resource(Resource(id="f1", position=Position(2, 2), properties={"type": "food"}))
    env.step()
    state = env.get_state()
    json.dumps(state)  # should not raise


def test_step_records_model_state():
    env = Environment(5, 5)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert events[0].outcome["model_state"] == {"dummy": True}
