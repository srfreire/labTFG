"""
Tests for ClassicalWienerProcessWithPerActionAccumulatorsModel
Covers all expected_behaviors from the spec.
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from classical_wiener_process_with_per_action_accumulators_model import (
    ClassicalWienerProcessWithPerActionAccumulatorsModel,
    Action,
    ACTIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=0, y=0, gw=10, gh=10, step=0, food=None, last_action_result=None):
    return {
        "x": x,
        "y": y,
        "grid_width": gw,
        "grid_height": gh,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


# ---------------------------------------------------------------------------
# B1: Agent navigates toward nearest food
# ---------------------------------------------------------------------------

def test_B1_navigates_toward_food():
    """
    Place food at (5,5), agent at (0,0).
    Over 50 decisions the chosen actions should be biased toward
    move_right / move_down (Manhattan-reducing directions).
    """
    random.seed(42)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()

    food = [{"x": 5, "y": 5}]
    perception = make_perception(x=0, y=0, food=food)

    toward_food = {"move_right", "move_down"}
    toward_count = 0
    total = 50

    for _ in range(total):
        action = model.decide(perception)
        if action.name in toward_food:
            toward_count += 1
        model.update(action, 0.0, perception)

    # Should prefer toward-food directions more than chance (2/6 ≈ 33%)
    assert toward_count / total > 0.40, (
        f"Expected >40% toward-food actions, got {toward_count}/{total}"
    )


# ---------------------------------------------------------------------------
# B2: Agent eats when on food cell
# ---------------------------------------------------------------------------

def test_B2_eats_when_on_food():
    """
    When food is on the agent's cell, 'eat' should be chosen > 60% of the time.
    """
    random.seed(0)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()

    food = [{"x": 3, "y": 3}]
    perception = make_perception(x=3, y=3, food=food)

    eat_count = 0
    total = 100

    for _ in range(total):
        action = model.decide(perception)
        if action.name == "eat":
            eat_count += 1
        model.update(action, 1.0 if action.name == "eat" else 0.0, perception)

    assert eat_count / total > 0.60, (
        f"Expected >60% 'eat' choices, got {eat_count}/{total}"
    )


# ---------------------------------------------------------------------------
# B3: Stochastic exploration when equidistant
# ---------------------------------------------------------------------------

def test_B3_stochastic_exploration_equidistant():
    """
    Agent at (5,5), food at (5,3) [up] and (5,7) [down].
    Both move_up and move_down are equidistant; each should be chosen ≥20% over 100 runs.
    """
    random.seed(7)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()

    # distance from (5,4) to (5,3) = 1; distance from (5,6) to (5,7) = 1 → truly equidistant
    food = [{"x": 5, "y": 3}, {"x": 5, "y": 7}]
    perception = make_perception(x=5, y=5, food=food)

    counts = {a: 0 for a in ACTIONS}
    total = 100

    for _ in range(total):
        action = model.decide(perception)
        counts[action.name] += 1
        model.update(action, 0.0, perception)

    assert counts["move_up"] / total >= 0.20, (
        f"move_up chosen only {counts['move_up']}/{total} times"
    )
    assert counts["move_down"] / total >= 0.20, (
        f"move_down chosen only {counts['move_down']}/{total} times"
    )


# ---------------------------------------------------------------------------
# B4: Reward history biases future decisions
# ---------------------------------------------------------------------------

def test_B4_reward_history_biases_eat():
    """
    After 10 successful eat rewards, r_bar['eat'] should exceed r_bar['move_up'].
    """
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()

    food = [{"x": 2, "y": 2}]
    perception = make_perception(x=2, y=2, food=food)
    eat_action = Action(name="eat")

    for _ in range(10):
        model.update(eat_action, 1.0, perception)

    state = model.get_state()
    assert state["reward_history"]["eat"] > state["reward_history"]["move_up"], (
        f"eat reward history {state['reward_history']['eat']:.4f} not > "
        f"move_up {state['reward_history']['move_up']:.4f}"
    )


# ---------------------------------------------------------------------------
# B5: Decision time varies with evidence quality
# ---------------------------------------------------------------------------

def test_B5_decision_time_faster_with_close_food():
    """
    When food is adjacent (high proximity → high drift), the race should resolve
    faster (lower mean T_d) than when food is far away.
    """
    random.seed(123)
    n_trials = 30

    # Food directly adjacent (move_right would step onto it)
    model_close = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    food_close = [{"x": 1, "y": 0}]   # distance from (0,0) after move_right = 0
    perception_close = make_perception(x=0, y=0, food=food_close)

    td_close = []
    for _ in range(n_trials):
        model_close.decide(perception_close)
        td_close.append(model_close._last_t_d)
        model_close.update(Action("stay"), 0.0, perception_close)

    # Food far away
    model_far = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    food_far = [{"x": 9, "y": 9}]
    perception_far = make_perception(x=0, y=0, food=food_far)

    td_far = []
    for _ in range(n_trials):
        model_far.decide(perception_far)
        td_far.append(model_far._last_t_d)
        model_far.update(Action("stay"), 0.0, perception_far)

    mean_close = sum(td_close) / len(td_close)
    mean_far = sum(td_far) / len(td_far)

    assert mean_close < mean_far, (
        f"Expected faster decisions with close food: "
        f"mean T_d close={mean_close:.1f}, far={mean_far:.1f}"
    )


# ---------------------------------------------------------------------------
# Structural / contract tests
# ---------------------------------------------------------------------------

def test_get_state_contains_required_keys():
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    state = model.get_state()
    for key in ("evidence_accumulator", "drift_rate", "noise_sample",
                "reward_history", "chosen_action", "decision_time", "q_values"):
        assert key in state, f"Missing key '{key}' in get_state()"


def test_q_values_has_all_actions():
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    perception = make_perception(x=0, y=0, food=[{"x": 3, "y": 3}])
    action = model.decide(perception)
    model.update(action, 0.5, perception)
    qv = model.get_state()["q_values"]
    for a in ACTIONS:
        assert a in qv, f"q_values missing action '{a}'"
        assert isinstance(qv[a], float), f"q_values['{a}'] is not float"


def test_decide_returns_valid_action():
    random.seed(99)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    perception = make_perception(x=2, y=2, food=[{"x": 4, "y": 4}])
    action = model.decide(perception)
    assert isinstance(action, Action)
    assert action.name in ACTIONS, f"Unknown action '{action.name}'"


def test_accumulators_clamped_to_bounds():
    """Accumulator values should never exceed 'a' or go below 0."""
    random.seed(55)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel(sigma=5.0)  # extreme noise
    perception = make_perception(x=0, y=0, food=[])
    for _ in range(20):
        action = model.decide(perception)
        model.update(action, 0.0, perception)
        for val in model.evidence_accumulator.values():
            assert 0.0 <= val <= model.a + 1e-9, (
                f"Accumulator value {val} out of bounds [0, {model.a}]"
            )


def test_reward_history_decay_non_chosen():
    """Non-chosen actions should have their reward history decay toward 0."""
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel(gamma=0.9)
    # Manually set all reward histories high
    for a in ACTIONS:
        model.reward_history[a] = 1.0
    perception = make_perception()
    # Force an update choosing 'eat'
    model.update(Action("eat"), 0.5, perception)
    for a in ACTIONS:
        if a != "eat":
            assert model.reward_history[a] < 1.0, (
                f"reward_history['{a}'] did not decay"
            )
            assert abs(model.reward_history[a] - 0.9) < 1e-9, (
                f"reward_history['{a}'] = {model.reward_history[a]}, expected 0.9"
            )


def test_no_food_no_crash():
    """Model should not crash when there are no food resources."""
    random.seed(11)
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    perception = make_perception(x=5, y=5, food=[])
    action = model.decide(perception)
    model.update(action, 0.0, perception)
    assert action.name in ACTIONS


def test_default_parameters():
    """Check that default parameters match the spec."""
    model = ClassicalWienerProcessWithPerActionAccumulatorsModel()
    assert model.a == 1.5
    assert model.sigma == 0.1
    assert model.z0 == 0.75
    assert model.dt == 0.01
    assert model.T_max == 100
    assert model.k_res == 2.0
    assert model.k_eat == 1.0
    assert model.gamma == 0.9
