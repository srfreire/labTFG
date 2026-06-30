"""
Tests for IncentiveSalienceDualProcessAgentWantinglikingDissociationModel

One test per expected_behavior entry (B1–B6), plus basic interface tests.
"""

import importlib.util
import math
import random
import sys
import os

# ---------------------------------------------------------------------------
# Dynamic import: handle hyphenated filename by loading via importlib
# The module must be registered in sys.modules BEFORE exec_module so that
# @dataclass can resolve its __module__ reference.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODEL_FILE = os.path.join(
    _HERE,
    "incentive-salience-dual-process-agent-wantingliking-dissociation_model.py",
)
_MODULE_NAME = "incentive_salience_dual_process_agent_wantingliking_dissociation_model"

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODEL_FILE)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod   # register BEFORE exec so @dataclass resolves __module__
_spec.loader.exec_module(_mod)

IncentiveSalienceDualProcessAgentWantinglikingDissociationModel = (
    _mod.IncentiveSalienceDualProcessAgentWantinglikingDissociationModel
)
Action = _mod.Action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, grid_w=10, grid_h=10, food_cells=None, last_result=None):
    food_list = []
    if food_cells:
        for fx, fy in food_cells:
            food_list.append({"x": fx, "y": fy, "type": "food", "palatability": 1.0})
    return {
        "x": x,
        "y": y,
        "grid_width": grid_w,
        "grid_height": grid_h,
        "step": 0,
        "resources": {"food": food_list},
        "last_action_result": last_result or {},
    }


def simulate_eat(model, x=5, y=5, grid_w=10, grid_h=10, n=1):
    """Simulate n successful eat actions at (x,y)."""
    for _ in range(n):
        action = Action(name="eat")
        new_perception = make_perception(x, y, grid_w, grid_h, food_cells=[(x, y)],
                                         last_result={"consumed": True})
        model.update(action, model.r_food, new_perception)


def simulate_visit_no_food(model, x=5, y=5, grid_w=10, grid_h=10, n=1):
    """Simulate n steps at (x,y) without food (reward=0)."""
    for _ in range(n):
        action = Action(name="stay")
        new_perception = make_perception(x, y, grid_w, grid_h, food_cells=[],
                                         last_result={})
        model.update(action, 0.0, new_perception)


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------

class TestInterface:
    def test_decide_returns_action(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        perception = make_perception()
        action = model.decide(perception)
        assert isinstance(action, Action)
        assert action.name in model.ALL_ACTIONS

    def test_get_state_keys(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        state = model.get_state()
        for key in ("wanting_values", "liking_values", "hunger_level",
                    "wanting_prediction_error", "liking_prediction_error",
                    "combined_action_values", "action_probabilities", "q_values"):
            assert key in state, f"Missing key: {key}"

    def test_q_values_in_get_state(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        state = model.get_state()
        assert isinstance(state["q_values"], dict)
        simulate_eat(model)
        state = model.get_state()
        assert len(state["q_values"]) > 0

    def test_decide_does_not_mutate_state(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        h_before = model.hunger_level
        w_before = dict(model.W)
        model.decide(make_perception())
        assert model.hunger_level == h_before
        assert model.W == w_before

    def test_action_dataclass(self):
        a = Action(name="eat")
        assert a.name == "eat"
        assert a.params == {}
        b = Action(name="move_up", params={"speed": 1})
        assert b.params == {"speed": 1}


# ---------------------------------------------------------------------------
# B1: Wanting–liking dissociation — W converges faster than L
# ---------------------------------------------------------------------------

class TestB1WantingLikingDissociation:
    def test_W_greater_than_L_after_training(self):
        """
        After 20 eat steps at (5,5), W[(5,5)] should be > L[(5,5)]
        because alpha_W (0.12) > alpha_L (0.05).
        """
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        simulate_eat(model, x=5, y=5, n=20)

        w = model.W.get((5, 5), 0.0)
        l = model.L.get((5, 5), 0.0)
        assert w > 0.0, f"Wanting should be > 0 after 20 eats, got {w}"
        assert l > 0.0, f"Liking should be > 0 after 20 eats, got {l}"
        assert w > l, (
            f"W={w:.4f} should be greater than L={l:.4f} after training "
            f"(alpha_W=0.12 > alpha_L=0.05)"
        )

    def test_learning_rate_ratio(self):
        """W should converge proportionally faster than L."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        simulate_eat(model, x=3, y=3, n=10)
        w = model.W.get((3, 3), 0.0)
        l = model.L.get((3, 3), 0.0)
        assert w > l, f"Expected W={w:.4f} > L={l:.4f}"


# ---------------------------------------------------------------------------
# B2: Hunger suppresses approach (wanting channel)
# ---------------------------------------------------------------------------

class TestB2HungerModulatesApproach:
    def _approach_prob(self, model, trials=2000):
        """
        Estimate P(move_right) from (4,5) — this reaches (5,5) where W is high.
        """
        count = 0
        perception = make_perception(x=4, y=5, food_cells=[])
        for _ in range(trials):
            action = model.decide(perception)
            if action.name == "move_right":
                count += 1
        return count / trials

    def test_low_hunger_low_approach(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        random.seed(42)
        model.W[(5, 5)] = 1.5
        model.hunger_level = 0.05

        p_low = self._approach_prob(model)
        # With h=0.05, Q_W for (5,5) = 1.5*0.05*1.5=0.1125 → small advantage
        # Should be modest / not dominating
        assert p_low < 0.50, f"Expected low approach prob with low hunger, got {p_low:.3f}"

    def test_high_hunger_high_approach(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        random.seed(42)
        model.W[(5, 5)] = 1.5
        model.hunger_level = 0.9

        p_high = self._approach_prob(model)
        # With h=0.9, Q_W = 1.5*0.9*1.5=2.025 → strong pull to move_right
        assert p_high > 0.35, f"Expected high approach prob with high hunger, got {p_high:.3f}"

    def test_hunger_ordering(self):
        """P(approach|high hunger) > P(approach|low hunger)."""
        model_low = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model_high = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        random.seed(0)

        model_low.W[(5, 5)] = 1.5
        model_low.hunger_level = 0.05

        model_high.W[(5, 5)] = 1.5
        model_high.hunger_level = 0.9

        p_low = self._approach_prob(model_low)
        p_high = self._approach_prob(model_high)

        assert p_high > p_low, (
            f"High hunger ({p_high:.3f}) should produce higher approach "
            f"probability than low hunger ({p_low:.3f})"
        )


# ---------------------------------------------------------------------------
# B3: Alliesthesia modulates liking PE
# ---------------------------------------------------------------------------

class TestB3Alliesthesia:
    def test_high_hunger_liking_pe(self):
        """delta_L = r_t * h_t^lam - L; with h=0.9, L=0 → delta_L = 0.9"""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.9

        action = Action(name="eat")
        new_perception = make_perception(5, 5, food_cells=[(5, 5)],
                                          last_result={"consumed": True})
        model.update(action, model.r_food, new_perception)

        expected = 1.0 * (0.9 ** 1.0) - 0.0
        assert abs(model.liking_prediction_error - expected) < 1e-6, (
            f"Expected delta_L ≈ {expected:.4f}, got {model.liking_prediction_error:.4f}"
        )

    def test_low_hunger_liking_pe(self):
        """With h=0.1, L=0 → delta_L = 0.1"""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.1

        action = Action(name="eat")
        new_perception = make_perception(5, 5, food_cells=[(5, 5)],
                                          last_result={"consumed": True})
        model.update(action, model.r_food, new_perception)

        expected = 1.0 * (0.1 ** 1.0) - 0.0
        assert abs(model.liking_prediction_error - expected) < 1e-6, (
            f"Expected delta_L ≈ {expected:.4f}, got {model.liking_prediction_error:.4f}"
        )

    def test_high_hunger_larger_than_low(self):
        """Alliesthesia: hungry delta_L > sated delta_L."""
        model_hungry = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model_sated = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()

        model_hungry.hunger_level = 0.9
        model_sated.hunger_level = 0.1

        action = Action(name="eat")
        new_p = make_perception(5, 5, food_cells=[(5, 5)], last_result={"consumed": True})
        model_hungry.update(action, 1.0, new_p)
        model_sated.update(action, 1.0, new_p)

        assert model_hungry.liking_prediction_error > model_sated.liking_prediction_error


# ---------------------------------------------------------------------------
# B4: Dual extinction — both W and L decay, W faster
# ---------------------------------------------------------------------------

class TestB4DualExtinction:
    def test_both_decay_without_food(self):
        """After training and removing food, both W and L should decrease."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        simulate_eat(model, x=5, y=5, n=30)

        w_trained = model.W.get((5, 5), 0.0)
        l_trained = model.L.get((5, 5), 0.0)
        assert w_trained > 0.01
        assert l_trained > 0.01

        simulate_visit_no_food(model, x=5, y=5, n=30)

        assert model.W.get((5, 5), 0.0) < w_trained
        assert model.L.get((5, 5), 0.0) < l_trained

    def test_W_decays_faster_than_L(self):
        """W (alpha=0.12) decays faster than L (alpha=0.05) during extinction."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        simulate_eat(model, x=5, y=5, n=50)

        w0 = model.W.get((5, 5), 0.0)
        l0 = model.L.get((5, 5), 0.0)

        simulate_visit_no_food(model, x=5, y=5, n=30)

        w1 = model.W.get((5, 5), 0.0)
        l1 = model.L.get((5, 5), 0.0)

        w_drop = (w0 - w1) / w0 if w0 > 1e-9 else 0.0
        l_drop = (l0 - l1) / l0 if l0 > 1e-9 else 0.0

        assert w_drop > l_drop, (
            f"W should extinguish faster: W_drop={w_drop:.4f} vs L_drop={l_drop:.4f}"
        )


# ---------------------------------------------------------------------------
# B5: Liking-driven approach (even with zero wanting)
# ---------------------------------------------------------------------------

class TestB5LikingDrivenApproach:
    def test_liking_alone_produces_positive_q(self):
        """W=0 at (3,3), L=1.5: Q_total for move_right toward (3,3) should be positive."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(3, 3)] = 0.0
        model.L[(3, 3)] = 1.5
        model.hunger_level = 0.5

        q = model._compute_q_total((2, 3), set(), 10, 10, model.hunger_level)
        # Q_W = 1.5*0.5*0 = 0; Q_L = 0.5^1 * 1.5 = 0.75
        # Q_total = 0.6*0 + 0.4*0.75 - 0.01 = 0.29
        assert q["move_right"] > 0.0, f"Q(move_right) = {q['move_right']:.4f}"

    def test_liking_produces_above_baseline_approach(self):
        """Approach prob to (3,3) via pure liking > uniform baseline."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        random.seed(123)
        model.W[(3, 3)] = 0.0
        model.L[(3, 3)] = 1.5
        model.hunger_level = 0.5

        perception = make_perception(x=2, y=3, food_cells=[])
        count = sum(1 for _ in range(2000) if model.decide(perception).name == "move_right")
        p_approach = count / 2000

        # Baseline uniform over 5 valid non-eat actions = 0.20
        assert p_approach > 0.25, f"Expected > 0.25, got {p_approach:.3f}"


# ---------------------------------------------------------------------------
# B6: Hunger dynamics
# ---------------------------------------------------------------------------

class TestB6HungerDynamics:
    def test_hunger_increases_without_eating(self):
        """50 steps without food: h_t increases."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.2
        h_before = model.hunger_level

        simulate_visit_no_food(model, n=50)

        assert model.hunger_level > h_before

    def test_hunger_decreases_upon_eating(self):
        """Single eat: h_t = h + alpha_h - gamma_sat."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.7

        action = Action(name="eat")
        new_perception = make_perception(5, 5, food_cells=[(5, 5)],
                                          last_result={"consumed": True})
        model.update(action, model.r_food, new_perception)

        expected = 0.7 + 0.02 - 0.20  # = 0.52
        assert abs(model.hunger_level - expected) < 1e-6, (
            f"Expected h_t ≈ {expected:.4f}, got {model.hunger_level:.4f}"
        )

    def test_three_eats_decrease_hunger_substantially(self):
        """3 eats decrease hunger by ~0.54 net."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 1.0
        simulate_eat(model, x=5, y=5, n=3)
        assert model.hunger_level - 1.0 < -0.40

    def test_hunger_clipped_to_zero(self):
        """Hunger cannot go below 0."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.05
        simulate_eat(model, x=5, y=5, n=5)
        assert model.hunger_level >= 0.0

    def test_hunger_clipped_to_one(self):
        """Hunger cannot exceed 1."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.hunger_level = 0.99
        simulate_visit_no_food(model, n=20)
        assert model.hunger_level <= 1.0


# ---------------------------------------------------------------------------
# Learning rule arithmetic
# ---------------------------------------------------------------------------

class TestLearningRules:
    def test_wanting_update_R1_R2(self):
        """R1/R2: delta_W = reward - W; W += alpha_W * delta_W."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(5, 5)] = 0.3

        action = Action(name="eat")
        new_p = make_perception(5, 5, food_cells=[(5, 5)], last_result={"consumed": True})
        model.update(action, reward=1.0, new_perception=new_p)

        assert abs(model.wanting_prediction_error - 0.7) < 1e-6
        expected_w = 0.3 + 0.12 * 0.7  # = 0.384
        assert abs(model.W[(5, 5)] - expected_w) < 1e-6

    def test_liking_update_R3_R4(self):
        """R3/R4: delta_L = reward*h^lam - L; L += alpha_L * delta_L."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.L[(5, 5)] = 0.2
        model.hunger_level = 0.8

        action = Action(name="eat")
        new_p = make_perception(5, 5, food_cells=[(5, 5)], last_result={"consumed": True})
        model.update(action, reward=1.0, new_perception=new_p)

        expected_delta_L = 1.0 * 0.8 - 0.2  # = 0.6
        assert abs(model.liking_prediction_error - expected_delta_L) < 1e-6
        expected_l = 0.2 + 0.05 * 0.6  # = 0.23
        assert abs(model.L[(5, 5)] - expected_l) < 1e-6

    def test_wanting_clipped_at_W_max(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(5, 5)] = 1.99
        action = Action(name="eat")
        new_p = make_perception(5, 5, food_cells=[(5, 5)], last_result={"consumed": True})
        model.update(action, reward=1.0, new_perception=new_p)
        assert model.W[(5, 5)] <= 2.0

    def test_wanting_clipped_at_zero(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(5, 5)] = 0.01
        action = Action(name="stay")
        new_p = make_perception(5, 5, food_cells=[], last_result={})
        model.update(action, reward=-5.0, new_perception=new_p)
        assert model.W[(5, 5)] >= 0.0

    def test_extinction_wanting_pe_negative(self):
        """Without reward, wanting PE is negative."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(5, 5)] = 0.5
        action = Action(name="stay")
        new_p = make_perception(5, 5, food_cells=[], last_result={})
        model.update(action, reward=0.0, new_perception=new_p)
        assert model.wanting_prediction_error < 0.0


# ---------------------------------------------------------------------------
# Combined Q computation tests
# ---------------------------------------------------------------------------

class TestCombinedQ:
    def test_q_total_formula(self):
        """Q_total = w_W*mu*h*W + w_L*h^lam*L - c_step (for movement)."""
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        model.W[(6, 5)] = 0.8
        model.L[(6, 5)] = 0.5
        model.hunger_level = 0.6

        q = model._compute_q_total((5, 5), set(), 10, 10, 0.6)

        Q_W = 1.5 * 0.6 * 0.8
        Q_L = (0.6 ** 1.0) * 0.5
        expected = 0.6 * Q_W + 0.4 * Q_L - 0.01
        assert abs(q["move_right"] - expected) < 1e-8

    def test_out_of_bounds_masked(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        q = model._compute_q_total((0, 0), set(), 10, 10, 0.5)
        assert q["move_up"] == -1e9
        assert q["move_left"] == -1e9

    def test_eat_masked_without_food(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        q = model._compute_q_total((5, 5), set(), 10, 10, 0.5)
        assert q["eat"] == -1e9

    def test_eat_available_with_food(self):
        model = IncentiveSalienceDualProcessAgentWantinglikingDissociationModel()
        q = model._compute_q_total((5, 5), {(5, 5)}, 10, 10, 0.5)
        assert q["eat"] > -1e8  # available (not masked)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
