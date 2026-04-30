"""Integration tests — our models running inside Juan's Environment."""

from denis.hedonic import HedonicModel, HedonicParams
from denis.homeostatic import HomeostaticModel
from denis.integrated import IntegratedModel, IntegrationMode
from simlab.environment import (
    ActionRule,
    Agent,
    ConsumeEffect,
    Environment,
    ModelAdapter,
    MoveEffect,
    NoopEffect,
    Position,
    ResourceRule,
    homeostatic_perception_mapper,
)


def _make_env(seed=42):
    actions = [
        ActionRule("up", MoveEffect(dx=0, dy=-1)),
        ActionRule("down", MoveEffect(dx=0, dy=1)),
        ActionRule("left", MoveEffect(dx=-1, dy=0)),
        ActionRule("right", MoveEffect(dx=1, dy=0)),
        ActionRule("stay", NoopEffect()),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]
    resources = [
        ResourceRule(
            type="food",
            properties={"palatability": (0.3, 0.9)},
            count=2,
            regenerate=True,
        ),
    ]
    return Environment(5, 5, actions=actions, resources=resources, seed=seed)


def _adapter(model):
    return ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)


def test_homeostatic_runs_in_environment():
    env = _make_env()
    adapter = _adapter(HomeostaticModel())
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    assert all(e.agent_id == "a1" for e in events)


def test_hedonic_runs_in_environment():
    env = _make_env()
    adapter = _adapter(HedonicModel(HedonicParams(grid_size=(5, 5))))
    env.add_agent(Agent(id="a1", position=Position(2, 2), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    assert adapter.get_state()["epsilon"] < 1.0


def test_integrated_runs_in_environment():
    env = _make_env()
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(HedonicParams(grid_size=(5, 5))),
        mode=IntegrationMode.INDEPENDENT,
    )
    adapter = _adapter(model)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    state = adapter.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state


def test_multiple_agents_different_models():
    env = _make_env()
    env.add_agent(
        Agent(
            id="homeo",
            position=Position(0, 0),
            decision_model=_adapter(HomeostaticModel()),
        )
    )
    env.add_agent(
        Agent(
            id="hedonic",
            position=Position(4, 4),
            decision_model=_adapter(HedonicModel(HedonicParams(grid_size=(5, 5)))),
        )
    )
    events = env.run(30)
    assert len(events) == 60  # 2 agents x 30 steps
    agent_ids = {e.agent_id for e in events}
    assert agent_ids == {"homeo", "hedonic"}


def test_events_contain_model_state():
    env = _make_env()
    adapter = _adapter(HomeostaticModel())
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(5)
    for e in events:
        model_state = e.outcome["model_state"]
        assert "fat" in model_state
        assert "hunger" in model_state


def test_all_integration_modes_run():
    for mode in IntegrationMode:
        env = _make_env()
        model = IntegratedModel(
            homeostatic=HomeostaticModel(),
            hedonic=HedonicModel(HedonicParams(grid_size=(5, 5))),
            mode=mode,
        )
        adapter = _adapter(model)
        env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
        events = env.run(20)
        assert len(events) == 20
