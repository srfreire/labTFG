"""
Tests for ContinuousDriveDynamicsWithUrgencyThresholdPolicyModel
================================================================
One test per expected_behavior entry (B1–B5).
"""

import random
import math
import sys
import os

# PYTHONPATH is pre-configured to builder/homeostatic-regulation
from continuous_drive_dynamics_with_urgency_threshold_policy_model import (
    ContinuousDriveDynamicsWithUrgencyThresholdPolicyModel,
    Action,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=5, y=5,
    grid_width=20, grid_height=20,
    step=0,
    food=None,
    last_action_result=None,
):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def make_model(**kwargs):
    return ContinuousDriveDynamicsWithUrgencyThresholdPolicyModel(**kwargs)


# ---------------------------------------------------------------------------
# B1 – Immediate foraging when depleted
# ---------------------------------------------------------------------------

def test_B1_forage_when_depleted_moves_toward_food():
    """
    set h=0.4 (well below setpoint 0.8) → D=(0.8-0.4)^2=0.16 >= D_crit=0.15
    → mode should be FORAGE and agent should move toward nearest food.
    Food is to the right of agent → expected action is move_right.
    """
    model = make_model()
    model.h     = 0.4
    model.D     = (max(0.8 - 0.4, 0.0)) ** 2   # 0.16
    model.D_prev = 0.16
    model.dD_dt  = 0.0  # not worsening, but D >= D_crit already

    # Food is to the right: agent at (5,5), food at (8,5)
    food = [{"x": 8, "y": 5}]
    perception = make_perception(x=5, y=5, food=food)

    action = model.decide(perception)

    # D=0.16 >= D_crit=0.15 → FORAGE mode → must be a move action
    assert action.name in ["move_up", "move_down", "move_left", "move_right"], (
        f"Expected a move action, got {action.name}"
    )
    # Greedy gradient: moving right reduces distance from 3 to 2 → move_right
    assert action.name == "move_right", (
        f"Expected move_right toward food at (8,5) from (5,5), got {action.name}"
    )


# ---------------------------------------------------------------------------
# B2 – Rest when sated
# ---------------------------------------------------------------------------

def test_B2_rest_when_sated():
    """
    set h=0.85 → D = max(0.8-0.85,0)^2 = 0 < D_low=0.02 → action == 'stay'
    """
    model = make_model()
    model.h     = 0.85
    model.D     = 0.0
    model.D_prev = 0.0
    model.dD_dt  = 0.0

    perception = make_perception(food=[])
    action = model.decide(perception)

    assert action.name == "stay", f"Expected 'stay' when sated, got '{action.name}'"


# ---------------------------------------------------------------------------
# B3 – Eat immediately when on food and hungry
# ---------------------------------------------------------------------------

def test_B3_eat_when_on_food_and_hungry():
    """
    place agent on food cell with h=0.5 → D=(0.8-0.5)^2=0.09 > 0 and food_here
    → mode == EAT → action == 'eat'
    """
    model = make_model()
    model.h     = 0.5
    model.D     = (0.8 - 0.5) ** 2   # 0.09
    model.D_prev = 0.09
    model.dD_dt  = 0.0

    # Food exactly at agent's cell
    food = [{"x": 5, "y": 5}]
    perception = make_perception(x=5, y=5, food=food)
    action = model.decide(perception)

    assert action.name == "eat", (
        f"Expected 'eat' when on food with D={model.D:.4f}, got '{action.name}'"
    )


# ---------------------------------------------------------------------------
# B4 – Energy oscillates around setpoint over many steps
# ---------------------------------------------------------------------------

def test_B4_energy_oscillates_around_setpoint():
    """
    Run 500 steps with food regenerating at fixed position.
    Mean energy should stay in (0.6, 0.9).
    """
    random.seed(42)
    model = make_model()

    # Fixed food at (5, 5); agent starts at (5, 5) too
    ax, ay = 5, 5
    food_pos = {"x": 5, "y": 5}

    energy_history = []

    for step in range(500):
        food = [food_pos]  # food always regenerates
        perception = make_perception(x=ax, y=ay, food=food, step=step)
        action = model.decide(perception)

        # Simulate environment: eat if on food cell and action=='eat'
        consumed = (
            action.name == "eat"
            and ax == food_pos["x"]
            and ay == food_pos["y"]
        )
        last_result = {"consumed": consumed}

        # Apply movement
        deltas = {
            "move_up":    (0, -1),
            "move_down":  (0,  1),
            "move_left":  (-1, 0),
            "move_right": ( 1, 0),
        }
        if action.name in deltas:
            dx, dy = deltas[action.name]
            ax = max(0, min(19, ax + dx))
            ay = max(0, min(19, ay + dy))

        new_perception = make_perception(
            x=ax, y=ay, food=food, step=step,
            last_action_result=last_result,
        )
        model.update(action, 0.0, new_perception)
        energy_history.append(model.h)

    mean_h = sum(energy_history) / len(energy_history)
    assert 0.6 < mean_h < 0.9, (
        f"Mean energy {mean_h:.4f} outside expected range (0.6, 0.9)"
    )


# ---------------------------------------------------------------------------
# B5 – Drive velocity detects worsening condition
# ---------------------------------------------------------------------------

def test_B5_drive_velocity_triggers_forage():
    """
    Drive velocity preemptive foraging: even when D < D_crit, if dD_dt > 0
    the agent should switch to FORAGE.

    Per R5:
        if D < D_low:          → REST      (checked first)
        elif food_here and D>0 → EAT
        elif D >= D_crit or dD_dt > 0 → FORAGE   ← target branch

    We need D_low < D < D_crit and dD_dt > 0 (and no food at current cell).

    h = 0.65 → D = (0.8-0.65)^2 = 0.0225
      D_low  = 0.02  → 0.0225 > 0.02   ✓ (won't REST on first branch)
      D_crit = 0.15  → 0.0225 < 0.15   ✓ (won't FORAGE via D >= D_crit)
    D_prev = 0.01   → dD_dt = 0.0225 - 0.01 = 0.0125 > 0 ✓ → FORAGE
    """
    model = make_model()
    model.h      = 0.65
    model.D      = (0.8 - 0.65) ** 2    # 0.0225
    model.D_prev = 0.01
    model.dD_dt  = model.D - model.D_prev   # 0.0125 > 0

    # No food at current cell, food exists elsewhere (forage moves toward it)
    food = [{"x": 10, "y": 10}]
    perception = make_perception(x=5, y=5, food=food)
    action = model.decide(perception)

    # Verify preconditions
    assert model.D > model.D_low, (
        f"Test precondition: D={model.D:.4f} should be > D_low={model.D_low}"
    )
    assert model.D < model.D_crit, (
        f"Test precondition: D={model.D:.4f} should be < D_crit={model.D_crit}"
    )
    assert model.dD_dt > 0, (
        f"Test precondition: dD_dt={model.dD_dt:.6f} should be > 0"
    )

    # Should be in FORAGE mode → a move action
    assert action.name in ["move_up", "move_down", "move_left", "move_right"], (
        f"Expected a move action in FORAGE mode (dD_dt>0 preemptive), got '{action.name}'"
    )


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

def test_get_state_contains_required_keys():
    """get_state() must return all expected keys including q_values."""
    model = make_model()
    state = model.get_state()
    required = {
        "energy_level", "setpoint", "drive", "previous_drive",
        "drive_velocity", "behavioural_mode", "q_values",
    }
    assert required.issubset(state.keys()), (
        f"Missing keys: {required - state.keys()}"
    )
    assert isinstance(state["q_values"], dict)
    assert len(state["q_values"]) == 6  # 4 move + stay + eat


def test_q_values_all_actions_present():
    """q_values must cover all six actions."""
    model = make_model()
    model.h = 0.5
    model.D = (0.8 - 0.5) ** 2
    perception = make_perception()
    model.update(Action("stay"), 0.0, perception)
    qv = model.get_state()["q_values"]
    for a in ["stay", "eat", "move_up", "move_down", "move_left", "move_right"]:
        assert a in qv, f"Missing q_value for '{a}'"


def test_decide_is_readonly():
    """decide() must not change internal state."""
    model = make_model()
    model.h     = 0.5
    model.D     = (0.8 - 0.5) ** 2
    model.dD_dt = 0.01
    perception  = make_perception(food=[{"x": 8, "y": 5}])

    h_before = model.h
    D_before = model.D
    model.decide(perception)
    assert model.h == h_before
    assert model.D == D_before


def test_update_applies_energy_decay():
    """Calling update with 'stay' (no move, no eat) must reduce h by lambda_decay."""
    model = make_model()
    model.h  = 0.8
    h_before = model.h
    action   = Action("stay")
    perception = make_perception()
    model.update(action, 0.0, perception)
    expected = max(0.0, h_before - model.lambda_decay)
    assert abs(model.h - expected) < 1e-9, (
        f"h should be {expected:.4f}, got {model.h:.4f}"
    )


def test_update_applies_eat_restoration():
    """Eating should increase energy by c_eat (minus decay)."""
    model = make_model()
    model.h  = 0.4
    h_before = model.h
    action   = Action("eat")
    perception = make_perception(last_action_result={"consumed": True})
    model.update(action, 1.0, perception)
    expected = min(1.0, h_before - model.lambda_decay + model.c_eat)
    assert abs(model.h - expected) < 1e-9, (
        f"h should be {expected:.4f}, got {model.h:.4f}"
    )


def test_update_applies_movement_cost():
    """Moving should cost c_move on top of decay."""
    model = make_model()
    model.h  = 0.8
    h_before = model.h
    action   = Action("move_right")
    perception = make_perception(x=6, y=5, last_action_result={})
    model.update(action, 0.0, perception)
    expected = max(0.0, h_before - model.lambda_decay - model.c_move)
    assert abs(model.h - expected) < 1e-9, (
        f"h should be {expected:.4f}, got {model.h:.4f}"
    )


def test_drive_zero_when_above_setpoint():
    """Drive must be zero when h >= h*."""
    model = make_model()
    model.h = 1.0
    d = model._compute_drive(model.h)
    assert d == 0.0, f"Drive should be 0 when h >= h*, got {d}"


def test_drive_increases_with_deficit():
    """Drive should increase as energy falls further below setpoint."""
    model = make_model()
    d1 = model._compute_drive(0.7)
    d2 = model._compute_drive(0.5)
    d3 = model._compute_drive(0.3)
    assert d1 < d2 < d3, (
        f"Drive should increase with deficit: {d1:.4f}, {d2:.4f}, {d3:.4f}"
    )


def test_energy_clamped_at_zero():
    """Energy must not drop below 0."""
    model = make_model()
    model.h = 0.01
    action  = Action("move_right")
    perception = make_perception(x=1, y=1, last_action_result={})
    for _ in range(20):
        model.update(action, 0.0, perception)
    assert model.h >= 0.0, f"Energy went negative: {model.h}"


def test_energy_clamped_at_one():
    """Energy must not exceed 1 even after many eat events."""
    model = make_model()
    model.h = 0.95
    action  = Action("eat")
    perception = make_perception(last_action_result={"consumed": True})
    for _ in range(10):
        model.update(action, 1.0, perception)
    assert model.h <= 1.0, f"Energy exceeded 1.0: {model.h}"


def test_mode_eat_takes_priority_over_forage():
    """
    When food is at the current cell and D > 0 (but below D_crit),
    EAT mode takes priority over FORAGE even when dD_dt > 0.
    """
    model = make_model()
    model.h     = 0.65
    model.D     = (0.8 - 0.65) ** 2    # 0.0225 — above D_low, below D_crit
    model.D_prev = 0.01
    model.dD_dt  = model.D - model.D_prev  # > 0

    # Food at agent's current cell
    food = [{"x": 5, "y": 5}]
    perception = make_perception(x=5, y=5, food=food)
    action = model.decide(perception)

    assert action.name == "eat", (
        f"EAT should take priority when food_here and D>0, got '{action.name}'"
    )


def test_drive_velocity_stored_correctly():
    """dD_dt should equal new_D - old_D after update."""
    model = make_model()
    model.h = 0.7
    model.D = (0.8 - 0.7) ** 2  # 0.01

    action     = Action("stay")   # no eat, no move
    perception = make_perception()
    model.update(action, 0.0, perception)

    # After update: h_new = 0.7 - 0.02 = 0.68
    # new_D = (0.8 - 0.68)^2 = 0.0144
    # dD_dt should be 0.0144 - 0.01 = 0.0044
    expected_dD = (0.8 - 0.68) ** 2 - 0.01
    assert abs(model.dD_dt - expected_dD) < 1e-9, (
        f"dD_dt should be {expected_dD:.6f}, got {model.dD_dt:.6f}"
    )
