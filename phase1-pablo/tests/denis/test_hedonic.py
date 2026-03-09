# tests/denis/test_hedonic.py
import numpy as np
from decisionlab.models.protocol import Action, Perception, STAY
from denis.hedonic import HedonicModel, HedonicParams


def _make_perception(**overrides) -> Perception:
    defaults = dict(position=(2, 2), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    defaults.update(overrides)
    return Perception(**defaults)


def test_initial_q_table_is_zeros():
    m = HedonicModel(params=HedonicParams(grid_size=(5, 5)))
    state = m.get_state()
    assert state["q_table"].shape[0] > 0
    assert np.all(state["q_table"] == 0.0)


def test_decide_returns_valid_action():
    m = HedonicModel(params=HedonicParams(grid_size=(5, 5)))
    p = _make_perception()
    action = m.decide(p)
    assert isinstance(action, Action)


def test_epsilon_decays():
    params = HedonicParams(grid_size=(5, 5), epsilon=1.0, epsilon_decay=0.99, epsilon_min=0.01)
    m = HedonicModel(params=params)
    e_before = m.epsilon
    p = _make_perception()
    action = m.decide(p)
    m.update(action, 1.0, _make_perception(step=1))
    assert m.epsilon < e_before


def test_q_value_updates_after_reward():
    params = HedonicParams(grid_size=(5, 5), epsilon=0.0)  # pure exploitation
    m = HedonicModel(params=params)

    # Place food at (2, 2), agent at (2, 2)
    p = _make_perception(position=(2, 2), food_sources=[{"x": 2, "y": 2, "palatability": 1.0}])
    action = m.decide(p)

    # Give reward
    p_new = _make_perception(position=(2, 2), ate_food=True, step=1)
    m.update(action, 10.0, p_new)

    state = m.get_state()
    assert np.any(state["q_table"] != 0.0)


def test_hedonic_signal():
    params = HedonicParams(grid_size=(5, 5))
    m = HedonicModel(params=params)
    # Initially zero (all Q-values are 0)
    assert m.hedonic_signal((2, 2)) == 0.0

    # After learning, signal should change
    p = _make_perception(position=(2, 2))
    m.update(STAY, 10.0, _make_perception(position=(2, 2), step=1))
    assert m.hedonic_signal((2, 2)) != 0.0


