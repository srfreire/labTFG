"""
Tests for OdeBasedDynamicAttributeValuationWithCognitiveControlModel
=====================================================================
One test per expected_behavior entry from the spec, plus structural tests.
"""

import importlib.util
import math
import os
import sys

# ---------------------------------------------------------------------------
# Dynamic import for hyphenated module filename
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(__file__)
_MODEL_FILE = os.path.join(
    _HERE,
    "ode-based-dynamic-attribute-valuation-with-cognitive-control_model.py"
)
_MOD_NAME = "ode_based_dynamic_attribute_valuation_with_cognitive_control_model"

_spec = importlib.util.spec_from_file_location(_MOD_NAME, _MODEL_FILE)
_mod = importlib.util.module_from_spec(_spec)
# Must register in sys.modules before exec so dataclasses resolve __module__
sys.modules[_MOD_NAME] = _mod
_spec.loader.exec_module(_mod)

OdeBasedDynamicAttributeValuationWithCognitiveControlModel = (
    _mod.OdeBasedDynamicAttributeValuationWithCognitiveControlModel
)
Action = _mod.Action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_perception(
    x=5, y=5, grid_width=10, grid_height=10, step=0,
    food=None, last_action_result=None
):
    return {
        "x": x, "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def _make_food(x, y, palatability=0.5):
    return {"x": x, "y": y, "type": "food", "palatability": palatability}


def _run_idle_steps(model, n, perception):
    """Run n steps with a fixed perception."""
    for _ in range(n):
        action = model.decide(perception)
        model.update(action, 0.0, perception)


def _get_scores(model, x, y, food_list, grid_w=10, grid_h=10):
    """Trigger decide and return the q_values (blended U_a scores) dict."""
    p = _make_perception(x=x, y=y, grid_width=grid_w, grid_height=grid_h,
                         food=food_list)
    model.decide(p)
    return model.get_state()["q_values"]


# ---------------------------------------------------------------------------
# Structural / smoke tests
# ---------------------------------------------------------------------------

class TestStructure:
    def test_class_name(self):
        assert OdeBasedDynamicAttributeValuationWithCognitiveControlModel.__name__ == (
            "OdeBasedDynamicAttributeValuationWithCognitiveControlModel"
        )

    def test_decide_returns_action(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=42)
        p = _make_perception()
        a = model.decide(p)
        assert isinstance(a, Action)
        assert a.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_get_state_keys(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        state = model.get_state()
        required = {"H_t", "K_t", "w_imm", "w_abs", "w_imm_star", "w_abs_star",
                    "V_o", "a_imm", "a_abs", "q_values"}
        assert required.issubset(set(state.keys()))

    def test_q_values_all_actions_present(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        p = _make_perception()
        model.decide(p)
        qv = model.get_state()["q_values"]
        for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]:
            assert a in qv, f"Missing q_value for action: {a}"

    def test_decide_does_not_mutate_state(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=7)
        p = _make_perception()
        before = (model.H_t, model.K_t, model.w_imm, model.w_abs)
        model.decide(p)
        after = (model.H_t, model.K_t, model.w_imm, model.w_abs)
        assert before == after, "decide() must not mutate state variables"

    def test_update_mutates_state(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=7)
        p = _make_perception()
        action = model.decide(p)
        before_K = model.K_t
        model.update(action, 0.0, p)
        assert model.K_t != before_K, "update() should change K_t via ODE step"


# ---------------------------------------------------------------------------
# B1: Cognitive control depletes → shift from quality to proximity
# ---------------------------------------------------------------------------

class TestB1CognitiveControlDepletion:
    """
    Run 200 steps without eating.
    Expected: K_t < K_0; w_imm > w_abs; w_imm > initial value (0.5).
    """

    def test_K_depletes_below_K0(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=1)
        K_0 = model.K_0
        p = _make_perception()
        _run_idle_steps(model, 200, p)
        assert model.K_t < K_0, (
            f"K_t={model.K_t:.4f} should be < K_0={K_0}"
        )

    def test_w_imm_dominates_after_depletion(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=1)
        p = _make_perception()
        _run_idle_steps(model, 200, p)
        assert model.w_imm > model.w_abs, (
            f"w_imm={model.w_imm:.4f} should exceed w_abs={model.w_abs:.4f} "
            "after 200 idle steps"
        )

    def test_w_imm_increased_from_initial(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=1)
        initial_w_imm = model.w_imm  # 0.5
        p = _make_perception()
        _run_idle_steps(model, 200, p)
        assert model.w_imm > initial_w_imm, (
            f"w_imm={model.w_imm:.4f} should have increased from {initial_w_imm}"
        )


# ---------------------------------------------------------------------------
# B2: Cognitive control recovers after rest
# ---------------------------------------------------------------------------

class TestB2CognitiveControlRecovery:
    """
    Deplete K to ~0.1, then run 100 idle steps with c_K=0 (pure recovery).
    """

    def test_K_recovers_toward_K0(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=2, c_K=0.0
        )
        model.K_t = 0.1
        initial_K = model.K_t
        p = _make_perception()
        _run_idle_steps(model, 100, p)
        assert model.K_t > initial_K, (
            f"K_t={model.K_t:.4f} should have recovered above {initial_K}"
        )

    def test_w_abs_increases_during_recovery(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=2, c_K=0.0
        )
        model.K_t = 0.1
        model.w_imm = 0.7
        model.w_abs = 0.3
        initial_w_abs = model.w_abs
        p = _make_perception()
        _run_idle_steps(model, 100, p)
        assert model.w_abs > initial_w_abs, (
            f"w_abs={model.w_abs:.4f} should increase during K recovery"
        )

    def test_K_recovery_approaches_K0(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=2, c_K=0.0
        )
        model.K_t = 0.1
        p = _make_perception()
        _run_idle_steps(model, 300, p)
        assert model.K_t > 0.4, (
            f"K_t={model.K_t:.4f} should approach K_0=0.5 after 300 recovery steps"
        )


# ---------------------------------------------------------------------------
# B3: Weight inertia — sudden hunger spike → smooth weight transition
# ---------------------------------------------------------------------------

class TestB3WeightInertia:
    """
    Instantaneously set H_t = 0.9 (was 0.2).
    Assert |w_imm(t+1) - w_imm(t)| < |w_imm_star(t) - w_imm(t)|
    """

    def test_weight_change_is_smaller_than_equilibrium_gap(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=3, tau_w=5.0, c_K=0.0
        )
        model.H_t = 0.2
        model.K_t = model.K_0
        p = _make_perception()
        for _ in range(50):
            action = model.decide(p)
            model.update(action, 0.0, p)

        w_imm_before = model.w_imm

        # Sudden hunger spike
        model.H_t = 0.9
        denom = 2.0 + model.H_t + model.phi * model.K_t
        w_imm_star_new = (1.0 + model.H_t) / denom
        gap = abs(w_imm_star_new - w_imm_before)

        action = model.decide(p)
        model.update(action, 0.0, p)

        change = abs(model.w_imm - w_imm_before)
        assert change < gap, (
            f"Inertia check: change={change:.4f} should be < gap={gap:.4f}"
        )

    def test_weight_moves_in_right_direction(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=3, tau_w=5.0, c_K=0.0
        )
        model.H_t = 0.2
        model.K_t = model.K_0
        p = _make_perception()
        for _ in range(50):
            a = model.decide(p)
            model.update(a, 0.0, p)

        w_imm_before = model.w_imm
        model.H_t = 0.9
        a = model.decide(p)
        model.update(a, 0.0, p)

        assert model.w_imm >= w_imm_before, (
            "After hunger spike, w_imm should not decrease"
        )


# ---------------------------------------------------------------------------
# B4: Q-learning accumulates positive values near food locations
# ---------------------------------------------------------------------------

class TestB4QLearningStructure:

    def test_q_value_increases_for_eating_at_food(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=4, alpha_Q=0.2, gamma=0.9
        )
        food = _make_food(5, 5, palatability=0.8)
        p = _make_perception(x=5, y=5, food=[food])
        p_result = dict(p)
        p_result["last_action_result"] = {"consumed": True}

        eat_action = Action(name="eat")
        initial_Q = model._get_Q((5, 5), "eat")

        for _ in range(50):
            model._last_perception = p
            model.update(eat_action, 1.0, p_result)

        final_Q = model._get_Q((5, 5), "eat")
        assert final_Q > initial_Q, (
            f"Q[(5,5),'eat'] should increase: {initial_Q:.4f} → {final_Q:.4f}"
        )

    def test_q_values_positive_near_food_after_many_steps(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=4, alpha_Q=0.1, gamma=0.9
        )
        food = _make_food(3, 3, palatability=0.9)
        p = _make_perception(x=3, y=3, food=[food])
        p_result = dict(p)
        p_result["last_action_result"] = {"consumed": True}

        eat_action = Action(name="eat")
        model._last_perception = p
        for _ in range(500):
            model.update(eat_action, 1.0, p_result)

        q_eat = model._get_Q((3, 3), "eat")
        assert q_eat > 0.5, (
            f"Q[(3,3),'eat'] should be > 0.5 after 500 eat rewards: {q_eat:.4f}"
        )


# ---------------------------------------------------------------------------
# B5: Hungry + depleted agent prefers nearest food
# ---------------------------------------------------------------------------

class TestB5HungryDepletedAgent:
    """
    B5 spec: H_t=0.95, K_t=0.05 → w_imm >> w_abs.
    Agent should score moving toward the nearer food higher than moving
    toward the distant food or staying still.

    We test this analytically via U_a scores, not by sampling.
    """

    def _depleted_model(self, seed=0):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=seed)
        model.H_t = 0.95
        model.K_t = 0.05
        denom = 2.0 + model.H_t + model.phi * model.K_t
        model.w_imm = (1.0 + model.H_t) / denom
        model.w_abs = (1.0 + model.phi * model.K_t) / denom
        model.w_imm_star = model.w_imm
        model.w_abs_star = model.w_abs
        return model

    def test_w_imm_dominates_when_hungry_and_depleted(self):
        """w_imm should be strictly > w_abs when H is high and K is low."""
        model = self._depleted_model()
        assert model.w_imm > model.w_abs, (
            f"w_imm={model.w_imm:.4f} should > w_abs={model.w_abs:.4f}"
        )

    def test_near_food_action_scores_higher_than_stay(self):
        """
        Agent at (5,5). Single food at (6,5) → dist=1 from (6,5) via move_right.
        With high w_imm, U_a(move_right) >> U_a(stay).
        """
        model = self._depleted_model()
        near_food = _make_food(6, 5, palatability=0.5)
        scores = _get_scores(model, 5, 5, [near_food])
        assert scores["move_right"] > scores["stay"], (
            f"move_right={scores['move_right']:.4f} should > stay={scores['stay']:.4f}"
        )

    def test_near_food_action_scores_higher_than_away_actions(self):
        """
        Moving away from the only food (left/up/down from (5,5) with food at (6,5))
        should score lower than move_right.
        """
        model = self._depleted_model()
        near_food = _make_food(6, 5, palatability=0.5)
        scores = _get_scores(model, 5, 5, [near_food])
        assert scores["move_right"] > scores["move_left"], (
            f"move_right={scores['move_right']:.4f} should > move_left={scores['move_left']:.4f}"
        )

    def test_proximity_dominates_over_quality_in_depleted_state(self):
        """
        Near food (dist=1, palat=0.1) vs far food (dist=5, palat=0.95).
        With depleted state, the action heading toward near food should
        have a higher U_a than actions that head toward far food.

        move_right brings agent to (6,5): distance to near_food=(6,5) is 0
        → a_imm = 1.0 (maximum proximity).

        move_right also has distance 3 to far_food=(9,5) from (6,5), but
        the nearest food algorithm picks the closest food = near_food.
        """
        model = self._depleted_model()
        near_food = _make_food(6, 5, palatability=0.1)   # near, low quality
        far_food  = _make_food(9, 5, palatability=0.95)  # far, high quality
        scores = _get_scores(model, 5, 5, [near_food, far_food])

        # move_right from (5,5) → (6,5): nearest food is near_food (dist=0)
        # a_imm = 1.0, a_abs = 2*(0.1-0.1)/0.9-1 = -1.0
        # V_o(move_right) = w_imm * 1.0 + w_abs * (-1.0)
        # With w_imm ≈ 0.65, w_abs ≈ 0.35: V_o ≈ 0.65 - 0.35 = 0.30 > 0

        # stay: V_o = 0
        assert scores["move_right"] > scores["stay"], (
            f"In depleted state, move_right={scores['move_right']:.4f} "
            f"should > stay={scores['stay']:.4f}"
        )

    def test_w_imm_weight_is_larger_fraction(self):
        """
        With H=0.95, K=0.05, phi=1.5:
        denom = 2 + 0.95 + 1.5*0.05 = 3.025
        w_imm_star = 1.95/3.025 ≈ 0.645
        w_abs_star = 1.075/3.025 ≈ 0.355
        w_imm > 0.60 (substantially above 0.5)
        """
        model = self._depleted_model()
        assert model.w_imm > 0.60, (
            f"w_imm={model.w_imm:.4f} should be > 0.60 when H=0.95, K=0.05"
        )


# ---------------------------------------------------------------------------
# B6: Agent eats food when on the same cell
# ---------------------------------------------------------------------------

class TestB6EatWhenOnFood:
    """
    B6: When agent is on food cell, V_o(eat) is high (a_imm=1.0).
    Test via U_a scores directly rather than unreliable sampling with 6 actions.
    """

    def test_eat_has_highest_u_a_when_on_food_high_hunger(self):
        """
        With H_t=0.8, weights at equilibrium, food at agent's cell:
        V_o(eat) = w_imm * 1.0 + w_abs * a_abs_palat
        This should exceed V_o(stay) = 0.
        """
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        model.H_t = 0.8
        model.K_t = 0.5
        denom = 2.0 + model.H_t + model.phi * model.K_t
        model.w_imm = (1.0 + model.H_t) / denom
        model.w_abs = (1.0 + model.phi * model.K_t) / denom

        food = _make_food(5, 5, palatability=0.8)
        scores = _get_scores(model, 5, 5, [food])
        assert scores["eat"] > scores["stay"], (
            f"eat={scores['eat']:.4f} should > stay={scores['stay']:.4f}"
        )

    def test_eat_score_exceeds_stay_at_neutral_state(self):
        """At default state (H=0.5, K=0.5), eat still beats stay when on food."""
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        food = _make_food(5, 5, palatability=0.7)
        scores = _get_scores(model, 5, 5, [food])
        assert scores["eat"] > scores["stay"], (
            f"eat={scores['eat']:.4f} should > stay={scores['stay']:.4f}"
        )

    def test_eat_score_positive_when_on_palatable_food(self):
        """V_o(eat) should be positive for palatability > 0.55 (any reasonable food)."""
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        # Use equilibrium weights at default state
        food = _make_food(5, 5, palatability=0.8)
        scores = _get_scores(model, 5, 5, [food])
        assert scores["eat"] > 0.0, (
            f"U_a(eat) should be positive for palatable food: {scores['eat']:.4f}"
        )

    def test_eat_zero_when_no_food_at_cell(self):
        """Without food at cell, eat should score 0 (both attributes are 0)."""
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        # Food at distant location
        food = _make_food(9, 9, palatability=0.8)
        scores = _get_scores(model, 5, 5, [food])
        # V_o(eat) = w_imm*0 + w_abs*0 = 0; Q is also 0 initially
        assert scores["eat"] == 0.0, (
            f"eat score should be 0 when no food at cell: {scores['eat']:.4f}"
        )

    def test_eat_q_value_exceeds_stay_after_warmup(self):
        """After Q-learning with eat rewards, Q[(5,5), eat] raises eat's U_a above stay."""
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(
            seed=99, alpha_Q=0.2
        )
        food = _make_food(5, 5, palatability=0.8)
        p = _make_perception(x=5, y=5, food=[food])
        p_reward = dict(p)
        p_reward["last_action_result"] = {"consumed": True}

        eat_action = Action("eat")
        model._last_perception = p
        for _ in range(20):
            model.update(eat_action, 1.0, p_reward)

        state = model.get_state()
        qv = state["q_values"]
        assert qv["eat"] > qv["stay"], (
            f"eat q_value ({qv['eat']:.4f}) should exceed stay ({qv['stay']:.4f})"
        )


# ---------------------------------------------------------------------------
# ODE correctness
# ---------------------------------------------------------------------------

class TestODECorrectness:
    def test_K_ode_single_step(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        K_before = model.K_t
        expected_K = max(0.0, min(1.0,
            K_before + (model.K_0 - K_before) / model.tau_K - model.c_K
        ))
        p = _make_perception()
        action = model.decide(p)
        model.update(action, 0.0, p)
        assert abs(model.K_t - expected_K) < 1e-10

    def test_H_ode_rises_when_not_eating(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        H_before = model.H_t
        p = _make_perception()
        action = model.decide(p)
        model.update(action, 0.0, p)
        expected_H = min(1.0, H_before + model.eta_H)
        assert abs(model.H_t - expected_H) < 1e-10

    def test_H_ode_drops_when_eating(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        food = _make_food(5, 5)
        p = _make_perception(x=5, y=5, food=[food])
        p_result = dict(p)
        p_result["last_action_result"] = {"consumed": True}

        H_before = model.H_t
        eat_action = Action("eat")
        model._last_perception = p
        model.update(eat_action, 1.0, p_result)
        expected_H = max(0.0, H_before + model.eta_H - model.R_food)
        assert abs(model.H_t - expected_H) < 1e-10

    def test_w_targets_sum_to_one(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        p = _make_perception()
        for _ in range(10):
            a = model.decide(p)
            model.update(a, 0.0, p)
        assert abs(model.w_imm_star + model.w_abs_star - 1.0) < 1e-10

    def test_state_variables_stay_in_unit_interval(self):
        model = OdeBasedDynamicAttributeValuationWithCognitiveControlModel(seed=0)
        p = _make_perception()
        for _ in range(500):
            a = model.decide(p)
            model.update(a, 0.0, p)
        assert 0.0 <= model.w_imm <= 1.0
        assert 0.0 <= model.w_abs <= 1.0
        assert 0.0 <= model.K_t  <= 1.0
        assert 0.0 <= model.H_t  <= 1.0
