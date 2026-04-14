"""
Tests for homeostatic-regulation_pi_negative_feedback model.
"""

import importlib.util
import random
import sys
import os

# Load model from file with hyphens in its name
_MODULE_NAME = "homeostatic_regulation_pi_negative_feedback_model"
_spec = importlib.util.spec_from_file_location(
    _MODULE_NAME,
    os.path.join(os.path.dirname(__file__),
                 "homeostatic-regulation_pi_negative_feedback_model.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod   # register BEFORE exec so @dataclass works
_spec.loader.exec_module(_mod)

HomeostaticPINegativeFeedback = _mod.HomeostaticPINegativeFeedback
Action = _mod.Action


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, step=0, food=None, grid_w=10, grid_h=10,
                    last_action_result=None):
    return {
        "x": x, "y": y,
        "grid_width": grid_w, "grid_height": grid_h,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


# ---------------------------------------------------------------------------
# B1 – Energy decays, error grows, control signal increases
# ---------------------------------------------------------------------------

def test_B1_energy_decays_error_and_control_increase():
    """20 steps without food: A decreases, e increases, c increases."""
    model = HomeostaticPINegativeFeedback()
    model.A = 50.0
    model.e = model.s - model.A   # 30 > 0
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    prev_A = model.A
    prev_e = model.e
    prev_c = model.c

    for i in range(20):
        action = Action(name="stay")
        perc = make_perception(step=i, last_action_result={})
        model.update(action, 0.0, perc)

        assert model.A < prev_A, \
            f"Energy did not decrease at step {i}: {prev_A} → {model.A}"
        assert model.e > prev_e, \
            f"Error did not increase at step {i}: {prev_e} → {model.e}"
        assert model.c > prev_c, \
            f"Control did not increase at step {i}: {prev_c} → {model.c}"
        prev_A = model.A
        prev_e = model.e
        prev_c = model.c


# ---------------------------------------------------------------------------
# B2 – Agent eats when food is at position and energy is below set point
# ---------------------------------------------------------------------------

def test_B2_eats_when_food_present_and_hungry():
    """Food at agent position, A < s → action == 'eat'."""
    model = HomeostaticPINegativeFeedback()
    model.A = 50.0
    model.e = model.s - model.A   # 30 > 0
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    action = model.decide(perc)

    assert action.name == "eat", f"Expected 'eat', got '{action.name}'"


# ---------------------------------------------------------------------------
# B3 – Agent stays when energy at or above set point
# ---------------------------------------------------------------------------

def test_B3_stays_when_energy_above_setpoint():
    """A = 85 (> s=80) → e = -5 ≤ 0 → action == 'stay'."""
    model = HomeostaticPINegativeFeedback()
    model.A = 85.0
    model.e = model.s - model.A   # -5
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    action = model.decide(perc)
    assert action.name == "stay", f"Expected 'stay', got '{action.name}'"


def test_B3_stays_exactly_at_setpoint():
    """A = 80 (== s=80) → e = 0 ≤ 0 → action == 'stay'."""
    model = HomeostaticPINegativeFeedback()
    model.A = 80.0
    model.e = 0.0
    model.c_P = 0.0
    model.c = 0.0

    perc = make_perception(x=5, y=5)
    action = model.decide(perc)
    assert action.name == "stay", f"Expected 'stay', got '{action.name}'"


# ---------------------------------------------------------------------------
# B4 – Integral term accumulates during prolonged deficit
# ---------------------------------------------------------------------------

def test_B4_integral_accumulates_during_deficit():
    """50 steps with A < s → c_I > 0 and increases over time."""
    model = HomeostaticPINegativeFeedback()
    model.A = 20.0
    model.e = model.s - model.A   # 60 > 0
    model.c_P = model.k_P * model.e
    model.c_I = 0.0
    model.c = model.c_P + model.c_I

    c_I_values = [model.c_I]
    for i in range(50):
        action = Action(name="stay")
        perc = make_perception(step=i, last_action_result={})
        model.update(action, 0.0, perc)
        c_I_values.append(model.c_I)

    assert model.c_I > 0, f"Integral should be positive, got c_I={model.c_I}"
    increasing = sum(
        1 for j in range(1, len(c_I_values)) if c_I_values[j] > c_I_values[j - 1]
    )
    assert increasing >= 1, "Integral term never increased during prolonged deficit"


# ---------------------------------------------------------------------------
# B5 – Agent moves toward nearest food when hungry
# ---------------------------------------------------------------------------

def test_B5_moves_toward_food_to_the_right():
    """Food 3 cells to the right, A < s → 'move_right'."""
    model = HomeostaticPINegativeFeedback()
    model.A = 50.0
    model.e = model.s - model.A
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    food = [{"x": 8, "y": 5, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    action = model.decide(perc)

    assert action.name == "move_right", \
        f"Expected 'move_right', got '{action.name}'"


def test_B5_moves_toward_food_above():
    """Food 1 cell above (y-1), A < s → 'move_up'."""
    model = HomeostaticPINegativeFeedback()
    model.A = 50.0
    model.e = model.s - model.A
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    food = [{"x": 5, "y": 4, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    action = model.decide(perc)

    assert action.name == "move_up", \
        f"Expected 'move_up', got '{action.name}'"


# ---------------------------------------------------------------------------
# B6 – Random exploration when hungry but no food visible
# ---------------------------------------------------------------------------

def test_B6_explores_randomly_no_food():
    """A < s, no food → action is one of the four movement actions."""
    random.seed(99)
    model = HomeostaticPINegativeFeedback()
    model.A = 30.0
    model.e = model.s - model.A
    model.c_P = model.k_P * model.e
    model.c = model.c_P + model.c_I

    perc = make_perception(x=5, y=5, food=[])
    valid_moves = {"move_up", "move_down", "move_left", "move_right"}
    for _ in range(20):
        action = model.decide(perc)
        assert action.name in valid_moves, \
            f"Expected movement action, got '{action.name}'"


# ---------------------------------------------------------------------------
# Extra: get_state returns correct keys
# ---------------------------------------------------------------------------

def test_get_state_keys():
    model = HomeostaticPINegativeFeedback()
    state = model.get_state()
    expected_keys = {
        "energy", "error_signal", "proportional_control",
        "integral_control", "total_control_signal", "q_values"
    }
    assert expected_keys == set(state.keys()), \
        f"State keys mismatch: {set(state.keys())}"


# ---------------------------------------------------------------------------
# Extra: energy dynamics after successful eat
# ---------------------------------------------------------------------------

def test_energy_increases_after_eating():
    model = HomeostaticPINegativeFeedback()
    model.A = 50.0
    initial_energy = model.A

    action = Action(name="eat")
    perc = make_perception(last_action_result={"consumed": True})
    model.update(action, 1.0, perc)

    expected = min(max(initial_energy - model.d + model.delta_eat, 0.0), model.A_max)
    assert abs(model.A - expected) < 1e-9, \
        f"Energy after eating: expected {expected}, got {model.A}"
