"""
Tests for DriveReductionTdQLearningModelFreeModel
Covers all five expected_behaviors from the spec.
"""

import math
import random
import sys
import os
import importlib
import importlib.util

# PYTHONPATH is pre-configured; just ensure directory is on path
sys.path.insert(0, os.path.dirname(__file__))

# The model file has hyphens in its name, so we use importlib to load it
_spec = importlib.util.spec_from_file_location(
    "drive_reduction_td_q_learning_model_free_model",
    os.path.join(
        os.path.dirname(__file__),
        "drive-reduction-td-q-learning-model-free_model.py",
    ),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

DriveReductionTdQLearningModelFreeModel = _mod.DriveReductionTdQLearningModelFreeModel
Action = _mod.Action
ALL_ACTIONS = _mod.ALL_ACTIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=0, y=0, grid_width=5, grid_height=5, step=0,
                    resources=None, last_action_result=None):
    return {
        'x': x,
        'y': y,
        'grid_width': grid_width,
        'grid_height': grid_height,
        'step': step,
        'resources': resources if resources is not None else {},
        'last_action_result': last_action_result if last_action_result is not None else {},
    }


def no_food_perception(x=0, y=0, step=0):
    return make_perception(x=x, y=y, step=step, resources={'food': []})


def food_at(x, y):
    return {'food': [{'x': x, 'y': y, 'type': 'food'}]}


# ---------------------------------------------------------------------------
# B1: Hunger increases monotonically due to metabolic drift (no eating)
# ---------------------------------------------------------------------------

def test_b1_hunger_increases_without_eating():
    """
    Run steps with no food → assert h_t increases each step by lambda_drift
    until h_max.

    With drift=0.2 and h_max=10.0, hitting max requires 50 steps (0.2*50=10).
    We also verify monotonic increase throughout.
    """
    model = DriveReductionTdQLearningModelFreeModel(
        metabolic_drift_rate=0.2,   # 50 steps × 0.2 = 10.0 → hits h_max exactly
        max_hunger=10.0,
    )
    model.h_t = 0.0
    model.s_t = (0, 0)

    prev_h = model.h_t
    hit_max = False

    for step in range(60):  # 60 > 50 needed, generous margin
        action = Action(name='stay')
        new_perception = make_perception(
            x=0, y=0, step=step + 1,
            resources={'food': []},
            last_action_result={'consumed': False},
        )
        model.update(action, 0.0, new_perception)

        h_now = model.h_t
        if prev_h < model.h_max:
            # Should have increased (or reached cap)
            assert h_now >= prev_h, (
                f"Step {step}: h_t should not decrease without eating; "
                f"got {h_now} < {prev_h}"
            )
        if h_now >= model.h_max:
            hit_max = True
        prev_h = h_now

    assert hit_max, (
        f"Expected h_t to reach h_max=10 within 60 steps of drift=0.2; "
        f"final h_t={model.h_t}"
    )


def test_b1_hunger_strictly_increases_before_cap():
    """Each step before hitting h_max, h_t strictly increases by lambda_drift."""
    drift = 0.3
    model = DriveReductionTdQLearningModelFreeModel(
        metabolic_drift_rate=drift,
        max_hunger=10.0,
    )
    model.h_t = 0.0
    model.s_t = (0, 0)

    for step in range(10):
        h_before = model.h_t
        action = Action(name='stay')
        new_perception = make_perception(
            x=0, y=0, step=step + 1,
            resources={'food': []},
            last_action_result={'consumed': False},
        )
        model.update(action, 0.0, new_perception)
        expected = min(h_before + drift, 10.0)
        assert abs(model.h_t - expected) < 1e-9, (
            f"Step {step}: expected h_t={expected:.4f}, got {model.h_t:.4f}"
        )


# ---------------------------------------------------------------------------
# B2: Eating reduces drive and produces positive homeostatic reward
# ---------------------------------------------------------------------------

def test_b2_eating_reduces_drive():
    """
    set h_t = 5.0, execute eat at food cell → assert h_t_next < h_t and r_t > 0
    """
    model = DriveReductionTdQLearningModelFreeModel(
        resource_nutritive_value=3.0,
        metabolic_drift_rate=0.1,
        max_hunger=10.0,
    )
    model.h_t = 5.0
    model.s_t = (2, 2)

    action = Action(name='eat')
    new_perception = make_perception(
        x=2, y=2, step=1,
        resources=food_at(2, 2),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    # h_t_next = clip(5.0 + 0.1 - 3.0, 0, 10) = 2.1
    assert model.h_t < 5.0, f"Expected h_t to decrease after eating; got {model.h_t}"
    assert model.r_t > 0.0, f"Expected positive homeostatic reward; got {model.r_t}"


def test_b2_q_table_updated_after_eat():
    """Q-table entry for the executed eat action should be non-zero after update."""
    model = DriveReductionTdQLearningModelFreeModel()
    model.h_t = 5.0
    model.s_t = (1, 1)

    action = Action(name='eat')
    new_perception = make_perception(
        x=1, y=1, step=1,
        resources=food_at(1, 1),
        last_action_result={'consumed': True},
    )
    # h_bin_old for h_t=5.0, h_bins=10, h_max=10 => bin=5
    h_bin_old = min(int(5.0 / 10.0 * 10), 9)
    model.update(action, 1.0, new_perception)

    q_key = ((1, 1), h_bin_old, 'eat')
    assert q_key in model.Q, "Q-table should have entry for eat after update"
    assert model.Q[q_key] != 0.0, "Q-value for eat should be non-zero after positive reward"


# ---------------------------------------------------------------------------
# B3: Alliesthesia — reward near setpoint ≈ 0, reward when hungry >> 0
# ---------------------------------------------------------------------------

def test_b3_alliesthesia_low_hunger_small_reward():
    """
    set h_t = 0.1, eat → assert r_t ≈ 0 (almost at setpoint, little drive to reduce)
    """
    model = DriveReductionTdQLearningModelFreeModel(
        resource_nutritive_value=3.0,
        metabolic_drift_rate=0.1,
        drive_exponent=2,
        drive_scaling=1.0,
        setpoint=0.0,
    )
    model.h_t = 0.1
    model.s_t = (0, 0)

    action = Action(name='eat')
    new_perception = make_perception(
        x=0, y=0, step=1,
        resources=food_at(0, 0),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    # D_before = 1.0 * |0.1|^2 = 0.01
    # h_next = clip(0.1 + 0.1 - 3.0, 0, 10) = 0.0
    # D_after = 0.0
    # r_t = 0.01 - 0.0 = 0.01  (near zero)
    assert abs(model.r_t) < 0.5, (
        f"Expected small reward near setpoint, got r_t={model.r_t}"
    )


def test_b3_alliesthesia_high_hunger_large_reward():
    """
    set h_t = 8.0, eat → assert r_t >> 0 (far from setpoint, large drive reduction)
    """
    model = DriveReductionTdQLearningModelFreeModel(
        resource_nutritive_value=3.0,
        metabolic_drift_rate=0.1,
        drive_exponent=2,
        drive_scaling=1.0,
        setpoint=0.0,
    )
    model.h_t = 8.0
    model.s_t = (0, 0)

    action = Action(name='eat')
    new_perception = make_perception(
        x=0, y=0, step=1,
        resources=food_at(0, 0),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    # D_before = |8.0|^2 = 64.0
    # h_next = clip(8.0 + 0.1 - 3.0, 0, 10) = 5.1
    # D_after = |5.1|^2 = 26.01
    # r_t = 64.0 - 26.01 = 37.99  >> 0
    assert model.r_t > 10.0, (
        f"Expected large reward when very hungry, got r_t={model.r_t}"
    )


def test_b3_reward_increases_with_hunger():
    """Reward from eating is larger when hungrier (alliesthesia principle)."""
    def reward_for_hunger(h):
        model = DriveReductionTdQLearningModelFreeModel(
            resource_nutritive_value=3.0,
            metabolic_drift_rate=0.0,  # no drift so we isolate eating effect
            setpoint=0.0,
        )
        model.h_t = h
        model.s_t = (0, 0)
        action = Action(name='eat')
        new_perception = make_perception(
            x=0, y=0, step=1,
            resources=food_at(0, 0),
            last_action_result={'consumed': True},
        )
        model.update(action, 1.0, new_perception)
        return model.r_t

    r_low = reward_for_hunger(0.5)
    r_high = reward_for_hunger(7.0)
    assert r_high > r_low, (
        f"Reward should be higher when hungry (h=7.0) than when sated (h=0.5); "
        f"got r_high={r_high:.4f}, r_low={r_low:.4f}"
    )


# ---------------------------------------------------------------------------
# B4: Q-values converge so agent moves toward food when hungry
# ---------------------------------------------------------------------------

def test_b4_trained_agent_favors_eat_when_hungry():
    """
    After training with many eat-food interactions in high-hunger states,
    Q-value for 'eat' at a food cell should be among the highest Q-values
    for that (state, hunger_bin).
    """
    random.seed(42)
    model = DriveReductionTdQLearningModelFreeModel(
        learning_rate=0.3,
        discount_factor=0.9,
        softmax_inv_temperature=2.0,
        resource_nutritive_value=4.0,
        metabolic_drift_rate=0.2,
        max_hunger=10.0,
    )
    food_x, food_y = 3, 3

    # Training loop: always hungry, always eat at food cell
    for step in range(1000):
        model.h_t = 7.0  # force hungry state
        model.s_t = (food_x, food_y)

        action = Action(name='eat')
        new_perception = make_perception(
            x=food_x, y=food_y, step=step + 1,
            resources=food_at(food_x, food_y),
            last_action_result={'consumed': True},
        )
        model.update(action, 1.0, new_perception)

    # After training: Q-value for 'eat' at high-hunger state should be positive
    # and higher than Q-values for non-eating actions
    h_high = 7.0
    h_bin_high = min(int(h_high / model.h_max * model.h_bins), model.h_bins - 1)
    pos = (food_x, food_y)

    q_eat = model.Q.get((pos, h_bin_high, 'eat'), 0.0)
    q_stay = model.Q.get((pos, h_bin_high, 'stay'), 0.0)

    assert q_eat > q_stay, (
        f"After training, Q(eat) should > Q(stay) when hungry; "
        f"got q_eat={q_eat:.4f}, q_stay={q_stay:.4f}"
    )
    assert q_eat > 0.0, f"Expected positive Q(eat) after training; got {q_eat:.4f}"


def test_b4_q_values_non_trivial_after_training():
    """Q-table should accumulate entries after repeated updates."""
    random.seed(7)
    model = DriveReductionTdQLearningModelFreeModel(learning_rate=0.2)

    for step in range(200):
        model.h_t = max(1.0, model.h_t)  # ensure some hunger
        model.s_t = (0, 0)
        action = Action(name='eat')
        new_perception = make_perception(
            x=0, y=0, step=step + 1,
            resources=food_at(0, 0),
            last_action_result={'consumed': True},
        )
        model.update(action, 1.0, new_perception)

    assert len(model.Q) > 0, "Q-table should have entries after training"


# ---------------------------------------------------------------------------
# B5: Agent does not seek food when sated
# ---------------------------------------------------------------------------

def test_b5_sated_agent_eat_q_value_low():
    """
    After training sated states with no/low reward for eating,
    Q-value for 'eat' when hunger≈0 should be low (near zero or negative).
    """
    random.seed(99)
    model = DriveReductionTdQLearningModelFreeModel(
        learning_rate=0.3,
        metabolic_drift_rate=0.0,
        resource_nutritive_value=1.0,
        drive_exponent=2,
        drive_scaling=1.0,
        setpoint=0.0,
        max_hunger=10.0,
    )
    food_x, food_y = 0, 0

    # Train many steps with h_t ≈ 0.1 (sated) — eating yields near-zero reward
    for step in range(500):
        model.h_t = 0.1
        model.s_t = (food_x, food_y)

        action = Action(name='eat')
        new_perception = make_perception(
            x=food_x, y=food_y, step=step + 1,
            resources=food_at(food_x, food_y),
            last_action_result={'consumed': True},
        )
        model.update(action, 0.0, new_perception)

    # Q-value for eat in near-zero hunger bin should be very small
    h_bin_sated = min(int(0.1 / model.h_max * model.h_bins), model.h_bins - 1)
    pos = (food_x, food_y)
    q_eat_sated = model.Q.get((pos, h_bin_sated, 'eat'), 0.0)

    assert q_eat_sated < 1.0, (
        f"Q(eat) when sated should be small; got {q_eat_sated:.4f}"
    )


def test_b5_sated_vs_hungry_q_differential():
    """
    Q(eat) when hungry >> Q(eat) when sated at the same position
    after training on varied hunger states.
    """
    random.seed(42)
    model = DriveReductionTdQLearningModelFreeModel(
        learning_rate=0.3,
        metabolic_drift_rate=0.0,
        resource_nutritive_value=3.0,
        drive_exponent=2,
        max_hunger=10.0,
    )
    food_x, food_y = 1, 1

    for step in range(800):
        # Alternate between sated and hungry
        h = 0.1 if step % 2 == 0 else 8.0
        model.h_t = h
        model.s_t = (food_x, food_y)

        action = Action(name='eat')
        new_perception = make_perception(
            x=food_x, y=food_y, step=step + 1,
            resources=food_at(food_x, food_y),
            last_action_result={'consumed': True},
        )
        model.update(action, 1.0, new_perception)

    pos = (food_x, food_y)
    # Sated: bin for h=0.1 → bin=0
    h_bin_sated = min(int(0.1 / model.h_max * model.h_bins), model.h_bins - 1)
    # Hungry: bin for h=8.0 → bin=8
    h_bin_hungry = min(int(8.0 / model.h_max * model.h_bins), model.h_bins - 1)

    q_sated = model.Q.get((pos, h_bin_sated, 'eat'), 0.0)
    q_hungry = model.Q.get((pos, h_bin_hungry, 'eat'), 0.0)

    assert q_hungry > q_sated, (
        f"Q(eat | hungry) should > Q(eat | sated); "
        f"got q_hungry={q_hungry:.4f}, q_sated={q_sated:.4f}"
    )


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

def test_decide_returns_action():
    """decide() should always return a valid Action."""
    random.seed(0)
    model = DriveReductionTdQLearningModelFreeModel()
    perception = make_perception(x=1, y=1, resources={'food': []})
    action = model.decide(perception)
    assert isinstance(action, Action)
    assert action.name in ALL_ACTIONS


def test_decide_does_not_mutate_state():
    """decide() must be read-only — calling it twice yields same internal state."""
    random.seed(5)
    model = DriveReductionTdQLearningModelFreeModel()
    model.h_t = 3.5
    model.s_t = (2, 2)

    state_before = model.get_state()
    perception = make_perception(x=2, y=2, resources={'food': []})
    # Call decide twice
    model.decide(perception)
    model.decide(perception)

    state_after = model.get_state()
    assert state_before['hunger_level'] == state_after['hunger_level']
    assert state_before['drive'] == state_after['drive']
    assert state_before['q_table_size'] == state_after['q_table_size']


def test_decide_never_returns_eat_without_food():
    """When no food is at position, 'eat' should essentially never be chosen (beta=50)."""
    model = DriveReductionTdQLearningModelFreeModel(softmax_inv_temperature=50.0)
    model.h_t = 9.9  # very hungry
    model.s_t = (0, 0)

    random.seed(17)
    perception = make_perception(x=0, y=0, resources={'food': []})
    actions = [model.decide(perception).name for _ in range(100)]
    # With -1e9 penalty and high beta, 'eat' should never be selected
    assert 'eat' not in actions, "Agent should not choose 'eat' when no food is present"


def test_get_state_has_q_values():
    """get_state() must return a dict with 'q_values' key mapping action→float."""
    model = DriveReductionTdQLearningModelFreeModel()
    state = model.get_state()
    assert 'q_values' in state, "get_state() must include 'q_values'"
    q_vals = state['q_values']
    assert isinstance(q_vals, dict)
    for a in ALL_ACTIONS:
        assert a in q_vals, f"q_values must include action '{a}'"
        assert isinstance(q_vals[a], float)


def test_internal_state_math_r2():
    """Verify R2: h_t_next = clip(h_t + drift - K*ate, 0, h_max)."""
    model = DriveReductionTdQLearningModelFreeModel(
        metabolic_drift_rate=0.2,
        resource_nutritive_value=2.0,
        max_hunger=10.0,
    )
    model.h_t = 4.0
    model.s_t = (0, 0)

    action = Action(name='eat')
    new_perception = make_perception(
        x=0, y=0, step=1,
        resources=food_at(0, 0),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    expected_h = max(0.0, min(4.0 + 0.2 - 2.0, 10.0))  # = 2.2
    assert abs(model.h_t - expected_h) < 1e-9, (
        f"Expected h_t={expected_h}, got {model.h_t}"
    )


def test_internal_state_math_r3_drive():
    """Verify R3: r_t = D_before - D_after with quadratic drive."""
    model = DriveReductionTdQLearningModelFreeModel(
        drive_exponent=2,
        drive_scaling=1.0,
        setpoint=0.0,
        metabolic_drift_rate=0.0,
        resource_nutritive_value=3.0,
        max_hunger=10.0,
    )
    model.h_t = 4.0
    model.s_t = (0, 0)

    action = Action(name='eat')
    new_perception = make_perception(
        x=0, y=0, step=1,
        resources=food_at(0, 0),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    # D_before = |4.0|^2 = 16.0
    # h_next = 4.0 + 0 - 3.0 = 1.0
    # D_after = |1.0|^2 = 1.0
    # r_t = 15.0
    expected_r = 16.0 - 1.0
    assert abs(model.r_t - expected_r) < 1e-9, (
        f"Expected r_t={expected_r}, got {model.r_t}"
    )


def test_hrpe_calculation():
    """Verify delta_t = r_t + gamma * max_Q_next - Q(s,h_bin,a)."""
    model = DriveReductionTdQLearningModelFreeModel(
        learning_rate=0.1,
        discount_factor=0.9,
        drive_exponent=2,
        drive_scaling=1.0,
        setpoint=0.0,
        metabolic_drift_rate=0.0,
        resource_nutritive_value=2.0,
        max_hunger=10.0,
    )
    model.h_t = 3.0
    model.s_t = (0, 0)

    # Pre-seed a Q value for the 'eat' action
    h_bin_old = min(int(3.0 / 10.0 * 10), 9)  # = 3
    model.Q[((0, 0), h_bin_old, 'eat')] = 5.0

    action = Action(name='eat')
    new_perception = make_perception(
        x=0, y=0, step=1,
        resources=food_at(0, 0),
        last_action_result={'consumed': True},
    )
    model.update(action, 1.0, new_perception)

    # h_next = 3.0 - 2.0 = 1.0
    # D_before = 9.0, D_after = 1.0 => r_t = 8.0
    # h_bin_next = min(int(1.0 / 10 * 10), 9) = 1
    # max_Q_next = 0.0 (no entries for (0,0), bin=1)
    # delta_t = 8.0 + 0.9*0.0 - 5.0 = 3.0
    expected_delta = 8.0 + 0.9 * 0.0 - 5.0
    assert abs(model.delta_t - expected_delta) < 1e-9, (
        f"Expected delta_t={expected_delta}, got {model.delta_t}"
    )

    # Q updated: 5.0 + 0.1 * 3.0 = 5.3
    expected_q = 5.0 + 0.1 * expected_delta
    assert abs(model.Q[((0, 0), h_bin_old, 'eat')] - expected_q) < 1e-9, (
        f"Expected Q={(expected_q)}, got {model.Q[((0,0), h_bin_old, 'eat')]}"
    )
