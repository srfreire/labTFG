"""Tests for ModelAdapter — imports Phase 1 classes."""
from __future__ import annotations

from simlab.environment import (
    Action,
    ActionRule,
    Agent,
    ConsumeEffect,
    DecisionModel,
    Environment,
    MoveEffect,
    ModelAdapter,
    NoopEffect,
    Position,
    Resource,
    ResourceRule,
    homeostatic_perception_mapper,
)
from denis.homeostatic import HomeostaticModel, HomeostaticParams
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode


def _make_perception_dict(x=2, y=2, grid_w=5, grid_h=5, step=0, ate=False, food=None):
    """Build a perception dict in the NEW generic format."""
    if food is None:
        food = [{"x": 3, "y": 2, "palatability": 0.8, "type": "food"}]
    return {
        "x": x, "y": y,
        "grid_width": grid_w, "grid_height": grid_h,
        "resources": {"food": food},
        "last_action_result": {"consumed": ate} if ate else {},
        "step": step,
    }


# --- Adapter pass-through (no mapper) ---

def test_adapter_passthrough_no_mapper():
    """Without a mapper, perception dict passes through as-is."""
    calls = []

    class _Spy:
        def decide(self, perception):
            calls.append(perception)
            return Action("stay")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self):
            return {}

    adapter = ModelAdapter(_Spy())
    p = {"x": 1, "y": 2}
    adapter.decide(p)
    assert calls[0] is p  # same dict object, no transformation


# --- Adapter with mapper + HomeostaticModel ---

def test_adapter_with_mapper_decide():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    action = adapter.decide(_make_perception_dict())
    assert isinstance(action, Action)
    assert action.name in {"up", "down", "left", "right", "stay"}

def test_adapter_with_mapper_update():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    state_before = adapter.get_state()
    action = adapter.decide(_make_perception_dict())
    adapter.update(action, -0.01, _make_perception_dict(step=1))
    state_after = adapter.get_state()
    assert state_after["hunger"] != state_before["hunger"] or state_after["fat"] != state_before["fat"]

def test_adapter_get_state_returns_homeostatic_keys():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    state = adapter.get_state()
    assert "fat" in state
    assert "glycogen" in state
    assert "hunger" in state

def test_adapter_satisfies_decision_model_protocol():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    assert isinstance(adapter, DecisionModel)


# --- Adapter with HedonicModel ---

def test_adapter_with_hedonic_model():
    params = HedonicParams(grid_size=(5, 5))
    model = HedonicModel(params)
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
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
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    for i in range(10):
        action = adapter.decide(_make_perception_dict(step=i))
        adapter.update(action, -0.01, _make_perception_dict(step=i + 1))
    state = adapter.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state


# --- Full integration: adapter inside Environment ---

def test_environment_run_with_homeostatic_adapter():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    actions = [
        ActionRule("up", MoveEffect(dx=0, dy=-1)),
        ActionRule("down", MoveEffect(dx=0, dy=1)),
        ActionRule("left", MoveEffect(dx=-1, dy=0)),
        ActionRule("right", MoveEffect(dx=1, dy=0)),
        ActionRule("stay", NoopEffect()),
    ]
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=2, regenerate=True)
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(20)
    assert len(events) == 20
