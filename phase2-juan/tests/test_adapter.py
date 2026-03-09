"""Tests for DenisModelAdapter — imports Phase 1 classes."""
from __future__ import annotations

from simlab.environment import (
    Action,
    Agent,
    DecisionModel,
    DenisModelAdapter,
    Environment,
    Position,
    Resource,
)
from denis.homeostatic import HomeostaticModel, HomeostaticParams
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode


def _make_perception_dict(x=2, y=2, grid_w=5, grid_h=5, step=0, ate=False, food=None):
    if food is None:
        food = [{"x": 3, "y": 2, "palatability": 0.8}]
    return {
        "x": x, "y": y,
        "grid_width": grid_w, "grid_height": grid_h,
        "nearby_resources": food,
        "ate_food": ate,
        "step": step,
    }


# --- Adapter with HomeostaticModel ---

def test_adapter_decide_returns_generic_action():
    model = HomeostaticModel(HomeostaticParams())
    adapter = DenisModelAdapter(model)
    action = adapter.decide(_make_perception_dict())
    assert isinstance(action, Action)
    assert action.name in {"up", "down", "left", "right", "stay"}


def test_adapter_update_does_not_raise():
    model = HomeostaticModel(HomeostaticParams())
    adapter = DenisModelAdapter(model)
    action = adapter.decide(_make_perception_dict())
    adapter.update(action, -0.01, _make_perception_dict(step=1))


def test_adapter_get_state_returns_homeostatic_keys():
    model = HomeostaticModel(HomeostaticParams())
    adapter = DenisModelAdapter(model)
    state = adapter.get_state()
    assert "fat" in state
    assert "glycogen" in state
    assert "hunger" in state


def test_adapter_satisfies_decision_model_protocol():
    model = HomeostaticModel(HomeostaticParams())
    adapter = DenisModelAdapter(model)
    assert isinstance(adapter, DecisionModel)


# --- Adapter with HedonicModel ---

def test_adapter_with_hedonic_model():
    params = HedonicParams(grid_size=(5, 5))
    model = HedonicModel(params)
    adapter = DenisModelAdapter(model)
    initial_epsilon = adapter.get_state()["epsilon"]
    for i in range(5):
        action = adapter.decide(_make_perception_dict(step=i))
        adapter.update(action, -0.01, _make_perception_dict(step=i + 1))
    assert adapter.get_state()["epsilon"] < initial_epsilon


# --- Adapter with IntegratedModel ---

def test_adapter_with_integrated_model():
    model = IntegratedModel(
        homeostatic=HomeostaticModel(HomeostaticParams()),
        hedonic=HedonicModel(HedonicParams(grid_size=(5, 5))),
        mode=IntegrationMode.INDEPENDENT,
    )
    adapter = DenisModelAdapter(model)
    for i in range(10):
        action = adapter.decide(_make_perception_dict(step=i))
        adapter.update(action, -0.01, _make_perception_dict(step=i + 1))
    state = adapter.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state


# --- Full integration: adapter inside Environment ---

def test_environment_run_with_homeostatic_adapter():
    model = HomeostaticModel(HomeostaticParams())
    adapter = DenisModelAdapter(model)
    env = Environment(5, 5, seed=42, food_regenerate=True)
    env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.8}))
    env.add_resource(Resource(id="f2", position=Position(3, 3), properties={"type": "food", "palatability": 0.6}))
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(20)
    assert len(events) == 20


def test_perception_dict_keys():
    env = Environment(5, 5)
    env.add_resource(Resource(id="f1", position=Position(2, 2), properties={"type": "food", "palatability": 0.5}))
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStayDummy())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    expected_keys = {"x", "y", "grid_width", "grid_height", "nearby_resources", "ate_food", "step"}
    assert set(perception.keys()) == expected_keys


class _AlwaysStayDummy:
    def decide(self, perception: dict) -> Action:
        return Action("stay")
    def update(self, action, reward, new_perception):
        pass
    def get_state(self) -> dict:
        return {}
