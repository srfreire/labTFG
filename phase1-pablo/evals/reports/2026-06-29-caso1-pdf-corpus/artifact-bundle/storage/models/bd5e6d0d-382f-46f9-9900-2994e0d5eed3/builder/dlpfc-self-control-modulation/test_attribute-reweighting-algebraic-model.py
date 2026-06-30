"""
Tests for AttributeReweightingAlgebraicModelModel
Paradigm: dlpfc-self-control-modulation
Formulation: attribute-reweighting-algebraic-model
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from attribute_reweighting_algebraic_model_model import (
    AttributeReweightingAlgebraicModelModel,
    Action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=0, y=0, grid_width=10, grid_height=10, step=0, foods=None, last_action_result=None):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": foods or []},
        "last_action_result": last_action_result or {},
    }


def make_food(x, y, palatability):
    return {"x": x, "y": y, "type": "food", "palatability": palatability}


# ---------------------------------------------------------------------------
# B1: Conflict triggers dlPFC engagement
# ---------------------------------------------------------------------------

def test_b1_conflict_triggers_dlpfc_coupling():
    """
    B1: When high-palatability (0.9) and low-palatability (0.2) foods are nearby,
    coupling C should be > 0.3.
    """
    model = AttributeReweightingAlgebraicModelModel()

    # Place agent at (5,5) with two foods nearby: one tasty (pal=0.9), one healthy (pal=0.2)
    foods = [
        make_food(5, 4, 0.9),   # high palatability (temptation)
        make_food(5, 6, 0.2),   # low palatability (healthy)
    ]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
    model.update(action, 0.0, new_perception)

    state = model.get_state()
    # K = 0.9 - 0.2 = 0.7 (taste advantage of temptation)
    # C = sigmoid(1.5*0.7) * G * (1-D) = sigmoid(1.05)*0.5*1.0 ≈ 0.741*0.5 = 0.371
    assert state["conflict_signal"] > 0.0, (
        f"Expected conflict > 0, got {state['conflict_signal']}"
    )
    assert state["dlpfc_coupling"] > 0.3, (
        f"Expected dlPFC coupling > 0.3, got {state['dlpfc_coupling']}"
    )


# ---------------------------------------------------------------------------
# B2: Depletion accumulates under sustained conflict
# ---------------------------------------------------------------------------

def test_b2_depletion_accumulates_under_sustained_conflict():
    """
    B2: After many conflict trials with sustained high G, D increases and C decreases.

    We maintain G=1.0 throughout by resetting it each step (simulating a sustained
    high-goal-activation regime). This isolates the depletion dynamics from G decay.

    With K≈0.9, G=1.0, D=0:
      C = sigmoid(1.5*0.9)*1.0*(1-D) ≈ 0.794*(1-D)
      D_new = D + 0.08*C - 0.04*(1-C)
    Net depletion rate at D=0: 0.08*0.794 - 0.04*(1-0.794) = 0.0635 - 0.0082 = 0.0553
    After 10 steps: D > 0.3 easily.
    """
    model = AttributeReweightingAlgebraicModelModel()
    model.goal_activation = 1.0  # sustained high goal activation
    model.depletion_level = 0.0

    # Foods creating strong conflict
    foods = [
        make_food(3, 5, 0.95),  # very tasty
        make_food(7, 5, 0.05),  # very healthy
    ]

    c_at_step_1 = None

    for step in range(50):
        # Maintain high goal activation to isolate depletion dynamics
        model.goal_activation = 1.0
        action = Action(name="stay")
        new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
        model.update(action, 0.0, new_perception)
        state = model.get_state()
        if step == 0:
            c_at_step_1 = state["dlpfc_coupling"]

    state = model.get_state()
    assert state["depletion_level"] > 0.5, (
        f"Expected D > 0.5 after 50 steps of sustained high-G conflict, "
        f"got {state['depletion_level']:.4f}"
    )
    assert state["dlpfc_coupling"] < c_at_step_1, (
        f"Expected C at step 50 ({state['dlpfc_coupling']:.4f}) < C at step 1 ({c_at_step_1:.4f})"
    )


# ---------------------------------------------------------------------------
# B3: Without conflict, agent prefers high-palatability food (taste-dominated)
# ---------------------------------------------------------------------------

def test_b3_no_conflict_prefers_high_palatability():
    """
    B3: Without conflict, taste weights are dominant and the CCV for moving toward
    high-palatability food is higher than stay.

    Note: With a single food (no conflict), K=0 but sigmoid(0)=0.5, so C=0.5*G*(1-D).
    At G=0.5, D=0: C=0.25, w_h=0.2+0.6*0.25=0.35, w_tau=0.65.
    The taste_weight is still > 0.5, confirming taste dominance (health_weight baseline = 0.2).
    """
    model = AttributeReweightingAlgebraicModelModel()

    # Single high-palatability food one step above the agent
    foods_single = [make_food(5, 4, 0.9)]

    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods_single, last_action_result={})
    model.update(action, 0.0, new_perception)

    state = model.get_state()

    # Taste weight should be > 0.5 (taste still dominates over health even with baseline coupling)
    assert state["taste_weight"] > 0.5, (
        f"Expected taste_weight > 0.5 without strong conflict, got {state['taste_weight']}"
    )

    # The CCV for move_up (toward food at x=5,y=4) should be positive and > stay
    q = state["q_values"]
    assert q["move_up"] > q["stay"], (
        f"Expected CCV(move_up) > CCV(stay), got {q['move_up']:.4f} vs {q['stay']:.4f}"
    )


# ---------------------------------------------------------------------------
# B4: With active dlPFC, agent shifts preference toward healthy food
# ---------------------------------------------------------------------------

def test_b4_active_dlpfc_shifts_toward_healthy():
    """
    B4: Set G=1.0, D=0.0, place both food types.
    Over 100 trials, fraction choosing low-palatability (healthy) > 0.4.
    """
    random.seed(42)
    model = AttributeReweightingAlgebraicModelModel()
    model.goal_activation = 1.0   # G=1.0
    model.depletion_level = 0.0   # D=0.0

    # High-conflict scenario: tasty food (pal=0.9) at left, healthy (pal=0.1) at right
    # Agent at (5,5): move_left → food at (4,5), move_right → food at (6,5)
    foods = [
        make_food(4, 5, 0.9),   # left: very tasty
        make_food(6, 5, 0.1),   # right: very healthy
    ]

    # Force compute weights with high conflict scenario
    dummy_action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
    model.update(dummy_action, 0.0, new_perception)

    # Count healthy choices (move_right → toward low-palatability food)
    healthy_choices = 0
    total = 100

    for _ in range(total):
        perception = make_perception(x=5, y=5, foods=foods)
        action = model.decide(perception)
        if action.name == "move_right":
            healthy_choices += 1

    fraction_healthy = healthy_choices / total
    assert fraction_healthy > 0.4, (
        f"Expected fraction choosing low-palatability > 0.4 with active dlPFC, "
        f"got {fraction_healthy:.3f}"
    )


# ---------------------------------------------------------------------------
# B5: Goal activation decays and recovers
# ---------------------------------------------------------------------------

def test_b5_goal_activation_decays_and_recovers():
    """
    B5: Run 30 steps eating only high-palatability → G < 0.2;
    then eat low-palatability 5 times → G > 0.5.
    """
    model = AttributeReweightingAlgebraicModelModel()

    # Eat high-palatability food 30 times (not healthy, no boost)
    high_pal_food = [make_food(0, 0, 0.9)]
    for _ in range(30):
        action = Action(name="eat")
        # last_action_result includes palatability so update knows it's not healthy
        new_perception = make_perception(
            x=0, y=0,
            foods=high_pal_food,
            last_action_result={"palatability": 0.9}
        )
        model.update(action, 1.0, new_perception)

    state = model.get_state()
    assert state["goal_activation"] < 0.2, (
        f"Expected G < 0.2 after 30 high-pal meals, got {state['goal_activation']:.4f}"
    )

    # Now eat healthy (low-palatability) food 5 times
    low_pal_food = [make_food(0, 0, 0.1)]
    for _ in range(5):
        action = Action(name="eat")
        new_perception = make_perception(
            x=0, y=0,
            foods=low_pal_food,
            last_action_result={"palatability": 0.1}
        )
        model.update(action, 1.0, new_perception)

    state = model.get_state()
    assert state["goal_activation"] > 0.5, (
        f"Expected G > 0.5 after 5 healthy meals, got {state['goal_activation']:.4f}"
    )


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

def test_get_state_has_q_values():
    """get_state() must include a q_values dict with all expected action keys."""
    model = AttributeReweightingAlgebraicModelModel()
    state = model.get_state()
    assert "q_values" in state, "get_state() must include q_values"
    q = state["q_values"]
    for expected in ["move_up", "move_down", "move_left", "move_right", "stay"]:
        assert expected in q, f"q_values missing '{expected}'"
        assert isinstance(q[expected], float), f"q_values['{expected}'] must be float"


def test_decide_is_read_only():
    """decide() must not change state variables."""
    model = AttributeReweightingAlgebraicModelModel()
    before = model.get_state()
    foods = [make_food(1, 0, 0.7)]
    perception = make_perception(x=0, y=0, foods=foods)
    _ = model.decide(perception)
    after = model.get_state()
    assert before["goal_activation"] == after["goal_activation"]
    assert before["depletion_level"] == after["depletion_level"]
    assert before["dlpfc_coupling"] == after["dlpfc_coupling"]
    assert before["conflict_signal"] == after["conflict_signal"]


def test_decide_returns_valid_action():
    """decide() must return an Action with a non-empty name string."""
    model = AttributeReweightingAlgebraicModelModel()
    foods = [make_food(0, 0, 0.8)]
    perception = make_perception(x=0, y=0, foods=foods)
    action = model.decide(perception)
    assert isinstance(action, Action)
    assert isinstance(action.name, str) and len(action.name) > 0


def test_eat_action_available_when_food_present():
    """When food is at the agent's position, 'eat' must be a candidate action."""
    random.seed(0)
    model = AttributeReweightingAlgebraicModelModel()
    # Override weights to strongly prefer eating
    model.health_weight = 0.5
    model.taste_weight = 0.5

    foods = [make_food(0, 0, 0.9)]
    perception = make_perception(x=0, y=0, foods=foods)

    # Run many decisions — 'eat' should appear at least once
    actions_seen = set()
    for _ in range(100):
        a = model.decide(perception)
        actions_seen.add(a.name)

    assert "eat" in actions_seen, f"'eat' never chosen; seen: {actions_seen}"


def test_update_increases_depletion_under_coupling():
    """R6: Depletion increases when coupling C is high."""
    model = AttributeReweightingAlgebraicModelModel()
    # Manually set high G, low D and high conflict to ensure high coupling
    model.goal_activation = 1.0
    model.depletion_level = 0.0

    foods = [
        make_food(3, 5, 0.99),  # extreme conflict
        make_food(7, 5, 0.01),
    ]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})

    for _ in range(5):
        model.goal_activation = 1.0  # sustain G to ensure C stays high
        model.update(action, 0.0, new_perception)

    state = model.get_state()
    assert state["depletion_level"] > 0.0, (
        f"Expected D > 0 after updates with high conflict, got {state['depletion_level']}"
    )


def test_no_food_produces_zero_stay_ccv():
    """With no foods, stay CCV should be 0.0."""
    model = AttributeReweightingAlgebraicModelModel()
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=[], last_action_result={})
    model.update(action, 0.0, new_perception)
    state = model.get_state()
    assert state["q_values"]["stay"] == 0.0, (
        f"Expected stay CCV = 0.0 with no food, got {state['q_values']['stay']}"
    )


def test_weights_sum_to_one():
    """health_weight + taste_weight must always equal 1.0."""
    model = AttributeReweightingAlgebraicModelModel()
    foods = [make_food(3, 5, 0.9), make_food(7, 5, 0.1)]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
    for _ in range(10):
        model.update(action, 0.0, new_perception)
        state = model.get_state()
        total = state["health_weight"] + state["taste_weight"]
        assert abs(total - 1.0) < 1e-9, (
            f"Weights must sum to 1.0, got {total}"
        )


def test_conflict_signal_zero_with_single_food():
    """With a single food item, conflict signal K should be 0 (no disagreement possible)."""
    model = AttributeReweightingAlgebraicModelModel()
    foods = [make_food(2, 2, 0.8)]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
    model.update(action, 0.0, new_perception)
    state = model.get_state()
    assert state["conflict_signal"] == 0.0, (
        f"Expected K=0 with single food, got {state['conflict_signal']}"
    )


def test_high_conflict_increases_health_weight():
    """High conflict with G=1, D=0 must shift health_weight above baseline."""
    model = AttributeReweightingAlgebraicModelModel()
    model.goal_activation = 1.0
    model.depletion_level = 0.0

    foods = [
        make_food(0, 0, 0.95),  # very tasty
        make_food(1, 0, 0.05),  # very healthy
    ]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})
    model.update(action, 0.0, new_perception)

    state = model.get_state()
    # K ≈ 0.9, C = sigmoid(1.35)*1.0*1.0 ≈ 0.794
    # w_h = 0.2 + 0.6*0.794 = 0.676
    assert state["health_weight"] > model.w_h0, (
        f"Expected health_weight > baseline {model.w_h0}, got {state['health_weight']:.4f}"
    )
    assert state["health_weight"] > 0.5, (
        f"Expected health_weight > 0.5 with max G and max conflict, got {state['health_weight']:.4f}"
    )


def test_depletion_net_accumulation_with_sustained_high_g():
    """
    Direct unit test of R6: with G=1.0 and strong conflict, each step must
    increase D (since alpha_D * C > beta_D * (1-C) when C > beta_D/(alpha_D+beta_D) = 0.04/0.12 = 0.33).
    """
    model = AttributeReweightingAlgebraicModelModel()
    model.goal_activation = 1.0
    model.depletion_level = 0.0

    foods = [
        make_food(0, 0, 0.95),
        make_food(9, 9, 0.05),
    ]
    action = Action(name="stay")
    new_perception = make_perception(x=5, y=5, foods=foods, last_action_result={})

    d_prev = 0.0
    for step in range(10):
        model.goal_activation = 1.0  # hold G constant
        model.update(action, 0.0, new_perception)
        state = model.get_state()
        d_curr = state["depletion_level"]
        assert d_curr >= d_prev, (
            f"Depletion should not decrease at step {step}: {d_curr:.4f} < {d_prev:.4f}"
        )
        d_prev = d_curr

    assert model.depletion_level > 0.3, (
        f"Expected D > 0.3 after 10 high-conflict steps, got {model.depletion_level:.4f}"
    )
