from denis.homeostatic import HomeostaticModel
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode
from denis.grid import GridWorld, GridConfig
from denis.simulation import Simulation, SimulationResult


def test_simulation_runs():
    grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )

    sim = Simulation(grid=grid, model=model)
    result = sim.run(steps=50)

    assert isinstance(result, SimulationResult)
    assert len(result.history) == 50
    assert result.total_food_eaten >= 0


def test_simulation_result_has_expected_fields():
    grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )

    sim = Simulation(grid=grid, model=model)
    result = sim.run(steps=10)

    entry = result.history[0]
    assert "step" in entry
    assert "position" in entry
    assert "action" in entry
    assert "ate_food" in entry
    assert "hunger" in entry
    assert "hedonic_signal" in entry


def test_simulation_with_all_modes():
    """Smoke test: all 4 integration modes run without error."""
    for mode in IntegrationMode:
        grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
        hedonic_params = HedonicParams(grid_size=(5, 5))
        model = IntegratedModel(
            homeostatic=HomeostaticModel(),
            hedonic=HedonicModel(params=hedonic_params),
            mode=mode,
        )
        sim = Simulation(grid=grid, model=model)
        result = sim.run(steps=20)
        assert len(result.history) == 20
