from decisionlab.models.protocol import Action, Perception
from denis.homeostatic import HomeostaticModel


def _make_perception(**overrides) -> Perception:
    defaults = dict(position=(2, 2), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    defaults.update(overrides)
    return Perception(**defaults)


def test_initial_state():
    m = HomeostaticModel()
    state = m.get_state()
    assert state["fat"] == 50.0
    assert state["glycogen"] == 20.0
    assert state["ghrelin"] == 0.1
    assert state["leptin"] == 0.8
    assert 0.0 <= state["hunger"] <= 1.0


def test_hunger_increases_without_food():
    m = HomeostaticModel()
    h_before = m.get_state()["hunger"]
    for t in range(100):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_after = m.get_state()["hunger"]
    assert h_after > h_before


def test_hunger_decreases_after_eating():
    # Starve first to build hunger
    m = HomeostaticModel()
    for t in range(200):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_before = m.get_state()["hunger"]

    # Eat
    p = _make_perception(step=200, ate_food=True)
    m.update(Action.STAY, 1.0, p)

    # Let physiology settle
    for t in range(201, 220):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_after = m.get_state()["hunger"]
    assert h_after < h_before


def test_state_variables_stay_in_valid_range():
    m = HomeostaticModel()
    for t in range(500):
        ate = t % 50 == 0
        p = _make_perception(step=t, ate_food=ate)
        m.update(Action.STAY, 1.0 if ate else 0.0, p)
    state = m.get_state()
    assert state["fat"] >= 0
    assert state["glycogen"] >= 0
    assert state["ghrelin"] >= 0
    assert state["leptin"] >= 0
    assert state["hunger"] >= 0


def test_decide_returns_action():
    m = HomeostaticModel()
    p = _make_perception(
        food_sources=[{"x": 3, "y": 3, "palatability": 0.8}],
    )
    action = m.decide(p)
    assert isinstance(action, Action)
