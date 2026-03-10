"""Integration tests — our models running inside Juan's Environment."""
from simlab.environment import (
    Agent,
    ModelAdapter,
    Environment,
    Position,
    Resource,
)
from denis.homeostatic import HomeostaticModel, HomeostaticParams
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode


def _make_env(seed=42):
    env = Environment(5, 5, seed=seed, food_regenerate=True)
    env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.8}))
    env.add_resource(Resource(id="f2", position=Position(3, 3), properties={"type": "food", "palatability": 0.5}))
    return env


def test_homeostatic_runs_in_environment():
    env = _make_env()
    adapter = ModelAdapter(HomeostaticModel())
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    assert all(e.agent_id == "a1" for e in events)


def test_hedonic_runs_in_environment():
    env = _make_env()
    adapter = ModelAdapter(HedonicModel(HedonicParams(grid_size=(5, 5))))
    env.add_agent(Agent(id="a1", position=Position(2, 2), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    # Epsilon should have decayed
    assert adapter.get_state()["epsilon"] < 1.0


def test_integrated_runs_in_environment():
    env = _make_env()
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(HedonicParams(grid_size=(5, 5))),
        mode=IntegrationMode.INDEPENDENT,
    )
    adapter = ModelAdapter(model)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(50)
    assert len(events) == 50
    state = adapter.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state


def test_multiple_agents_different_models():
    env = _make_env()
    env.add_agent(Agent(
        id="homeo",
        position=Position(0, 0),
        decision_model=ModelAdapter(HomeostaticModel()),
    ))
    env.add_agent(Agent(
        id="hedonic",
        position=Position(4, 4),
        decision_model=ModelAdapter(HedonicModel(HedonicParams(grid_size=(5, 5)))),
    ))
    events = env.run(30)
    assert len(events) == 60  # 2 agents x 30 steps
    agent_ids = {e.agent_id for e in events}
    assert agent_ids == {"homeo", "hedonic"}


def test_events_contain_model_state():
    env = _make_env()
    adapter = ModelAdapter(HomeostaticModel())
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
        adapter = ModelAdapter(model)
        env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
        events = env.run(20)
        assert len(events) == 20
