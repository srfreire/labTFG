from decisionlab.models.protocol import Action
from denis.grid import GridWorld, GridConfig


def test_grid_creation():
    config = GridConfig(width=5, height=5, food_count=3, food_palatability_range=(0.5, 1.0))
    grid = GridWorld(config)
    assert grid.width == 5
    assert grid.height == 5
    assert len(grid.food_sources) == 3


def test_agent_placement():
    config = GridConfig(width=5, height=5, food_count=1)
    grid = GridWorld(config)
    grid.place_agent(2, 3)
    assert grid.agent_position == (2, 3)


def test_agent_movement():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.place_agent(2, 2)
    grid.apply_action(Action.RIGHT)
    assert grid.agent_position == (3, 2)


def test_agent_stays_in_bounds():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.place_agent(0, 0)
    grid.apply_action(Action.LEFT)
    assert grid.agent_position == (0, 0)
    grid.apply_action(Action.UP)
    assert grid.agent_position == (0, 0)


def test_food_consumption():
    config = GridConfig(width=5, height=5, food_count=0, food_regenerate=False)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 2, "y": 2, "palatability": 0.8}]
    grid.place_agent(2, 2)
    perception = grid.get_perception(step=0)
    assert perception.ate_food is True
    assert len(grid.food_sources) == 0


def test_food_regeneration():
    config = GridConfig(width=5, height=5, food_count=1, food_regenerate=True)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 2, "y": 2, "palatability": 0.8}]
    grid.place_agent(2, 2)
    grid.get_perception(step=0)  # consumes food
    assert len(grid.food_sources) == 1  # regenerated


def test_perception_returns_correct_data():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 1, "y": 1, "palatability": 0.7}]
    grid.place_agent(3, 3)
    p = grid.get_perception(step=5)
    assert p.position == (3, 3)
    assert p.grid_size == (5, 5)
    assert p.step == 5
    assert p.ate_food is False
    assert len(p.food_sources) == 1
