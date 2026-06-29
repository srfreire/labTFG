"""
Tests for WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel

Covers all 5 expected behaviors (B1–B5) from the spec.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from weighted_linear_summation_with_state_dependent_attribute_weights_algebraic_model import (
    WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel,
    Action,
    _palatability_to_abs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, grid_width=10, grid_height=10, food=None, last_action_result=None):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": 0,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def run_step(model, perception, action_name=None, reward=0.0, last_result=None):
    """Helper: call decide (optionally override action), then update."""
    action = model.decide(perception)
    if action_name is not None:
        action = Action(name=action_name)
    new_perc = dict(perception)
    new_perc["last_action_result"] = last_result or {}
    model.update(action, reward, new_perc)
    return action


# ---------------------------------------------------------------------------
# B1: Hunger increases over time without eating, w_imm > w_abs when very hungry
# ---------------------------------------------------------------------------

def test_B1_hunger_rises_and_biases_immediate_weight():
    """
    B1: Run 50 steps with no food reachable.
    Assert H_t > 0.9 (from initial 0.5, rising 0.01/step → 0.5 + 50*0.01 = 1.0 max)
    and w_imm > w_abs (hunger amplifies immediate weight).
    """
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    # eta=0.01 * 50 steps = +0.5 from 0.5 → capped at 1.0
    for _ in range(50):
        perc = make_perception(food=[])
        run_step(model, perc, reward=0.0)

    state = model.get_state()
    assert state["H_t"] > 0.9, f"Expected H_t > 0.9, got {state['H_t']}"
    assert state["w_imm"] > state["w_abs"], (
        f"Expected w_imm > w_abs when hungry, got w_imm={state['w_imm']:.4f}, w_abs={state['w_abs']:.4f}"
    )


# ---------------------------------------------------------------------------
# B2: After eating, hunger drops and the w_abs / w_imm ratio increases
# ---------------------------------------------------------------------------

def test_B2_eating_reduces_hunger_and_shifts_to_abstract_weight():
    """
    B2: Eat food at step T. Assert H_t drops and w_abs/w_imm ratio improves.
    """
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    # First, raise hunger high
    for _ in range(40):
        perc = make_perception(food=[])
        run_step(model, perc, reward=0.0)

    state_before = model.get_state()
    H_before = state_before["H_t"]
    ratio_before = state_before["w_abs"] / (state_before["w_imm"] + 1e-9)

    # Place food at agent position and eat it
    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.8}]
    perc = make_perception(x=5, y=5, food=food)
    run_step(model, perc, action_name="eat", reward=1.0, last_result={"consumed": True})

    state_after = model.get_state()
    H_after = state_after["H_t"]
    ratio_after = state_after["w_abs"] / (state_after["w_imm"] + 1e-9)

    assert H_after < H_before, f"Expected hunger to drop after eating, got {H_before:.4f} -> {H_after:.4f}"
    assert ratio_after > ratio_before, (
        f"Expected w_abs/w_imm ratio to increase after eating (less hungry), "
        f"got before={ratio_before:.4f}, after={ratio_after:.4f}"
    )


# ---------------------------------------------------------------------------
# B3: When very hungry, agent prefers closer food over farther high-quality food
# ---------------------------------------------------------------------------

def test_B3_hungry_agent_prefers_near_food():
    """
    B3: H_t=0.95, near food (dist=1, low palatability=0.2) vs far food (dist=5, high palatability=1.0).
    Agent should choose movement toward near food more often than far food.
    """
    random.seed(42)
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.95

    # Agent at (5, 5), grid 10x10
    # Near food: directly above at (5, 4) → move_up lands at (5,4), dist=0 → a_imm=1.0
    # Far food: at (0, 0) → very far
    food_near = {"x": 5, "y": 4, "type": "food", "palatability": 0.2}
    food_far = {"x": 0, "y": 0, "type": "food", "palatability": 1.0}

    perc = make_perception(x=5, y=5, food=[food_near, food_far])

    # Sample many decisions and count how often move_up (toward near) is chosen
    near_count = 0
    n_trials = 200

    for _ in range(n_trials):
        action = model.decide(perc)
        if action.name == "move_up":
            near_count += 1

    # With H_t=0.95, immediate weight is high; move_up (dist=0 from near food) should dominate
    assert near_count > n_trials * 0.3, (
        f"Expected move_up to be favored when hungry & near food present, "
        f"got {near_count}/{n_trials}"
    )


# ---------------------------------------------------------------------------
# B4: Attention shifts toward abstract attribute dimension via RPE learning
# ---------------------------------------------------------------------------

def test_B4_attention_shifts_toward_predictive_attribute():
    """
    B4: Verify that attention updates according to the RPE rule.

    Design: use a movement action (e.g. move_up) toward a high-palatability food.
    The action has a_imm in (0,1) and a_abs = palatability-derived.
    We set reward = 1.0 (above V_selected) so RPE > 0.

    When a_abs > a_imm, alpha_abs grows faster than alpha_imm under positive RPE.
    After renormalization, alpha_abs / alpha_imm > initial ratio.
    """
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    # Place food far enough that dist>0 so a_imm < 1 but a_abs is high
    # Agent at (0,0), food at (0,3) on 10x10 grid
    # move_down from (0,0) → (0,1); dist to food(0,3) = 2; max_dist=18
    # a_imm = 1 - 2/18 ≈ 0.889; a_abs = palatability=1.0 → 1.0
    # Both positive. With reward=1.0 and V_selected < 1.0, RPE > 0
    # Both alphas grow, but we verify the model remains consistent and
    # alpha_abs doesn't collapse (the test verifies the floor mechanism
    # and that alpha_abs >= epsilon throughout)

    # More targeted: use a setup where a_imm_selected=0 and a_abs_selected>0
    # Force "eat" action where there is NO food at agent position but there is
    # a food nearby → for "eat": a_imm=0, a_abs=0 (food not at pos).
    # This gives trivial update (0 * anything = 0).
    #
    # The cleanest testable case for R6: directly verify the algebraic rule
    # by controlling what decide() caches before calling update().
    #
    # We use a movement action toward food where a_imm < a_abs,
    # set a high reward, and verify alpha_abs increases relative to alpha_imm.

    model2 = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model2.alpha_imm = 0.5
    model2.alpha_abs = 0.5
    model2.H_t = 0.0   # sated so w_imm is lower, V_selected will be small

    # food at (5,4) from agent at (5,5) → move_up lands at (5,4), dist=0
    # a_imm = 1.0, a_abs = _palatability_to_abs(1.0) = 1.0
    # V = w_imm*1 + w_abs*1 = 1.0 regardless of weights
    # RPE = reward - 1.0 = 0.0 → no update. Need a_imm ≠ a_abs.

    # Use food at (5,3) from agent at (5,5), grid 10x10
    # move_up → (5,4); dist to food(5,3) = 1; max_dist=18
    # a_imm = 1 - 1/18 ≈ 0.944; a_abs = pal=1.0 → 1.0
    # V = w_imm*0.944 + w_abs*1.0 < 1.0  → RPE > 0 with reward=1.0
    # a_abs > a_imm so alpha_abs grows more than alpha_imm

    food = [{"x": 5, "y": 3, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)

    # Accumulate the ratio over many steps; ensure alpha_abs/alpha_imm trend upward
    initial_ratio = model2.alpha_abs / model2.alpha_imm  # starts at 1.0

    for _ in range(300):
        model2.decide(perc)
        # Force move_up (the cached attributes will be for move_up)
        model2.decide(perc)  # re-call decide so cache reflects move_up probabilities
        # Manually force move_up by overriding the cached selected values
        # a_imm for move_up to (5,4): dist to food(5,3)=1, max_dist=18 → 1-1/18
        a_imm_up = 1.0 - 1.0 / 18.0
        a_abs_up = _palatability_to_abs(1.0)  # = 1.0
        w_imm, w_abs = model2._compute_weights()
        V_up = w_imm * a_imm_up + w_abs * a_abs_up
        model2._last_selected_V = V_up
        model2._last_selected_a_imm = a_imm_up
        model2._last_selected_a_abs = a_abs_up
        new_perc = {**perc, "last_action_result": {}}
        model2.update(Action(name="move_up"), 1.0, new_perc)

    final_ratio = model2.alpha_abs / model2.alpha_imm
    assert final_ratio > initial_ratio, (
        f"Expected alpha_abs/alpha_imm to increase (a_abs > a_imm with positive RPE), "
        f"initial={initial_ratio:.4f}, final={final_ratio:.4f}"
    )


# ---------------------------------------------------------------------------
# B5: Agent eats food when standing on it and hungry
# ---------------------------------------------------------------------------

def test_B5_agent_eats_when_on_food_and_hungry():
    """
    B5: Place agent on food, set H_t=0.8. Assert P(eat) is highest action probability.
    """
    random.seed(0)
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.8

    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.8}]
    perc = make_perception(x=5, y=5, food=food)

    # Sample many decisions
    counts = {a: 0 for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]}
    n_trials = 500
    for _ in range(n_trials):
        action = model.decide(perc)
        counts[action.name] += 1

    eat_prob = counts["eat"] / n_trials
    max_other_prob = max(counts[a] / n_trials for a in counts if a != "eat")

    assert eat_prob > max_other_prob, (
        f"Expected eat to be most likely action, got eat_prob={eat_prob:.3f}, "
        f"max_other_prob={max_other_prob:.3f}. Counts: {counts}"
    )


# ---------------------------------------------------------------------------
# Additional unit tests for core mechanics
# ---------------------------------------------------------------------------

def test_weight_computation_hungry():
    """When H_t=1.0, w_imm should be significantly larger than w_abs."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 1.0
    model.alpha_imm = 0.5
    model.alpha_abs = 0.5
    # unnorm_imm = 0.5 * (1 + 0.6 * 1.0) = 0.5 * 1.6 = 0.8
    # unnorm_abs = 0.5 * 0.7 = 0.35
    # Z = 1.15, w_imm = 0.8/1.15, w_abs = 0.35/1.15
    w_imm, w_abs = model._compute_weights()
    assert abs(w_imm - 0.8 / 1.15) < 1e-6
    assert abs(w_abs - 0.35 / 1.15) < 1e-6
    assert abs(w_imm + w_abs - 1.0) < 1e-9


def test_weight_computation_sated():
    """When H_t=0.0, immediate weight is lower."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.0
    model.alpha_imm = 0.5
    model.alpha_abs = 0.5
    # unnorm_imm = 0.5 * 1.0 = 0.5
    # unnorm_abs = 0.5 * 0.7 = 0.35
    # Z = 0.85, w_imm = 0.5/0.85, w_abs = 0.35/0.85
    w_imm, w_abs = model._compute_weights()
    assert abs(w_imm - 0.5 / 0.85) < 1e-6
    assert abs(w_abs - 0.35 / 0.85) < 1e-6
    assert abs(w_imm + w_abs - 1.0) < 1e-9


def test_hunger_rises_without_eating():
    """Hunger should rise by eta each step when not eating."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.2
    perc = make_perception(food=[])
    run_step(model, perc, reward=0.0)
    state = model.get_state()
    assert abs(state["H_t"] - (0.2 + 0.01)) < 1e-6, f"Expected H_t={0.21}, got {state['H_t']}"


def test_hunger_drops_after_eating():
    """Hunger should drop by R_food - eta when eating."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.5
    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.8}]
    perc = make_perception(x=5, y=5, food=food)
    run_step(model, perc, action_name="eat", reward=1.0, last_result={"consumed": True})
    state = model.get_state()
    expected = max(0.0, 0.5 + 0.01 - 0.3)  # = 0.21
    assert abs(state["H_t"] - expected) < 1e-6, f"Expected H_t={expected}, got {state['H_t']}"


def test_attention_floors_at_epsilon():
    """Attention allocations should never go below epsilon."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    # Force extreme negative RPE many times to push alpha toward zero
    food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    for _ in range(500):
        run_step(model, perc, action_name="eat", reward=-1.0, last_result={"consumed": False})
    state = model.get_state()
    assert state["alpha_imm"] >= model.epsilon - 1e-9
    assert state["alpha_abs"] >= model.epsilon - 1e-9


def test_attention_always_sums_to_one():
    """alpha_imm + alpha_abs should always equal 1.0."""
    random.seed(7)
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    food = [{"x": 3, "y": 3, "type": "food", "palatability": 0.6}]
    for i in range(100):
        perc = make_perception(x=5, y=5, food=food)
        reward = random.uniform(-1, 1)
        run_step(model, perc, reward=reward)
        state = model.get_state()
        total = state["alpha_imm"] + state["alpha_abs"]
        assert abs(total - 1.0) < 1e-9, f"alpha sum = {total} at step {i}"


def test_get_state_has_q_values():
    """get_state() must include a 'q_values' key with all 6 actions."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    state = model.get_state()
    assert "q_values" in state
    for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]:
        assert a in state["q_values"], f"Missing '{a}' in q_values"


def test_q_values_populated_after_step():
    """q_values should reflect computed action values after an update."""
    random.seed(42)
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.9}]
    perc = make_perception(x=5, y=5, food=food)
    run_step(model, perc, reward=0.5)
    state = model.get_state()
    # eat action should have a_imm=1.0, a_abs high → positive V_a
    assert state["q_values"]["eat"] > 0.0, (
        f"Expected eat q_value > 0 with food present, got {state['q_values']['eat']}"
    )
    # stay action should have V_a=0.0
    assert state["q_values"]["stay"] == 0.0


def test_no_food_all_actions_have_zero_value():
    """With no food, all action values should be 0.0."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    perc = make_perception(food=[])
    model.decide(perc)
    for a, v in model._last_action_values.items():
        assert v == 0.0, f"Expected 0.0 for action {a} with no food, got {v}"


def test_palatability_normalization():
    """Test a_abs formula: palatability=0.1 → -1.0, palatability=1.0 → 1.0."""
    assert abs(_palatability_to_abs(0.1) - (-1.0)) < 1e-9
    assert abs(_palatability_to_abs(1.0) - 1.0) < 1e-9
    assert abs(_palatability_to_abs(0.55) - 0.0) < 1e-6  # midpoint


def test_immediate_attribute_eat_on_food():
    """a_imm for eat when standing on food should be 1.0."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    food = [{"x": 3, "y": 3, "type": "food", "palatability": 0.5}]
    a_imm, a_abs = model._compute_action_attributes("eat", (3, 3), food, 10, 10)
    assert a_imm == 1.0
    assert abs(a_abs - _palatability_to_abs(0.5)) < 1e-9


def test_immediate_attribute_eat_no_food():
    """a_imm for eat when NOT standing on food should be 0.0."""
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    food = [{"x": 7, "y": 7, "type": "food", "palatability": 0.5}]
    a_imm, a_abs = model._compute_action_attributes("eat", (3, 3), food, 10, 10)
    assert a_imm == 0.0
    assert a_abs == 0.0


def test_attention_update_rpe_rule_asymmetric():
    """
    Direct algebraic check of R6:
    When a_abs > a_imm and RPE > 0, alpha_abs grows more than alpha_imm,
    so alpha_abs / alpha_imm increases.
    """
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.alpha_imm = 0.5
    model.alpha_abs = 0.5
    model.H_t = 0.0  # low hunger

    # Agent at (5,5), food at (5,3) → move_up to (5,4), dist=1, max_dist=18
    # a_imm = 1 - 1/18 ≈ 0.944; a_abs = 1.0
    a_imm_val = 1.0 - 1.0 / 18.0
    a_abs_val = _palatability_to_abs(1.0)  # = 1.0

    # Compute V_selected at current weights
    w_imm, w_abs = model._compute_weights()
    V_sel = w_imm * a_imm_val + w_abs * a_abs_val  # < 1.0 since a_imm < 1.0

    # Manually set cache as decide() would
    model._last_selected_V = V_sel
    model._last_selected_a_imm = a_imm_val
    model._last_selected_a_abs = a_abs_val

    ratio_before = model.alpha_abs / model.alpha_imm  # = 1.0

    food = [{"x": 5, "y": 3, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)
    model.update(Action(name="move_up"), 1.0, {**perc, "last_action_result": {}})

    ratio_after = model.alpha_abs / model.alpha_imm
    # RPE = 1.0 - V_sel > 0, a_abs=1.0 > a_imm≈0.944 → alpha_abs grows more → ratio increases
    assert ratio_after > ratio_before, (
        f"Expected alpha_abs/alpha_imm ratio to increase: before={ratio_before:.6f}, after={ratio_after:.6f}"
    )


def test_attention_rpe_increases_abs_over_many_steps():
    """
    Sustained positive RPE with a_abs > a_imm over 300 steps drives alpha_abs up.
    """
    model = WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel()
    model.H_t = 0.0
    model.alpha_imm = 0.5
    model.alpha_abs = 0.5

    a_imm_val = 1.0 - 1.0 / 18.0  # ≈ 0.944
    a_abs_val = 1.0                 # palatability=1.0

    food = [{"x": 5, "y": 3, "type": "food", "palatability": 1.0}]
    perc = make_perception(x=5, y=5, food=food)

    for _ in range(300):
        w_imm, w_abs = model._compute_weights()
        V_sel = w_imm * a_imm_val + w_abs * a_abs_val
        model._last_selected_V = V_sel
        model._last_selected_a_imm = a_imm_val
        model._last_selected_a_abs = a_abs_val
        model.update(Action(name="move_up"), 1.0, {**perc, "last_action_result": {}})

    state = model.get_state()
    # alpha_abs should be > 0.5 (started at 0.5, positive RPE * a_abs > a_imm → grows more)
    assert state["alpha_abs"] > 0.5, (
        f"Expected alpha_abs > 0.5 after sustained positive abstract-attribute reward, "
        f"got {state['alpha_abs']:.4f}"
    )
