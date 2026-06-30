"""
Tests for RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel
Covers all 6 expected behaviors (B1–B6).
"""

import math
import random
import sys
import os

# PYTHONPATH is pre-configured; import from module name
sys.path.insert(0, os.path.dirname(__file__))

from rescorlawagner_cached_value_agent_with_softmax_action_selection_model import (
    RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel,
    Action,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, grid_w=10, grid_h=10, food=None, last_action_result=None):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_w,
        "grid_height": grid_h,
        "step": 0,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def make_food(x, y):
    return {"x": x, "y": y, "type": "food", "palatability": 1.0}


# ---------------------------------------------------------------------------
# B1 – Hunger increases without eating
# ---------------------------------------------------------------------------

class TestB1HungerGrowthWithoutFood:
    """Hunger grows by alpha_h per step toward 1.0 when no food is eaten."""

    def test_hunger_increases_50_steps_no_food(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        initial_h = model.h_t  # 0.5

        for _ in range(50):
            p = make_perception()
            action = Action(name="stay")
            model.update(action, 0.0, p)

        # Expect h_t > initial; bounded at 1.0
        expected = min(1.0, initial_h + 50 * 0.02)
        assert model.h_t > initial_h, f"Hunger should have increased, got {model.h_t}"
        assert abs(model.h_t - expected) < 1e-9, (
            f"Expected h_t ≈ {expected:.4f}, got {model.h_t:.4f}"
        )

    def test_hunger_clips_at_1(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.h_t = 1.0
        p = make_perception()
        model.update(Action(name="stay"), 0.0, p)
        assert model.h_t == 1.0, "Hunger must clip at 1.0"


# ---------------------------------------------------------------------------
# B2 – Value learning at food locations
# ---------------------------------------------------------------------------

class TestB2ValueLearningAtFoodCell:
    """After repeated eating at (5,5), V[(5,5)] should converge toward r_food=1.0."""

    def test_v_increases_after_eating_10_times(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        food = [make_food(5, 5)]

        for _ in range(10):
            p = make_perception(x=5, y=5, food=food, last_action_result={"consumed": True})
            model.update(Action(name="eat"), 1.0, p)

        v = model.V.get((5, 5), 0.0)
        assert v > 0.8, f"V[(5,5)] should be > 0.8 after 10 rewarded visits, got {v:.4f}"

    def test_v_does_not_exceed_r_max(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        food = [make_food(5, 5)]

        for _ in range(200):
            p = make_perception(x=5, y=5, food=food, last_action_result={"consumed": True})
            model.update(Action(name="eat"), 1.0, p)

        v = model.V.get((5, 5), 0.0)
        assert v <= model.R_max, f"V[(5,5)] exceeded R_max: {v}"


# ---------------------------------------------------------------------------
# B3 – Approach bias toward high-V cells
# ---------------------------------------------------------------------------

class TestB3ApproachBias:
    """Agent at (5,5) prefers moving toward (3,3) (high V) over (7,7) (low V)."""

    def test_more_moves_toward_high_v(self):
        random.seed(42)
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel(beta=5.0)
        # Set V so cells to the upper-left are high value
        model.V[(4, 5)] = 1.0  # move_left destination
        model.V[(5, 4)] = 1.0  # move_up destination
        model.V[(6, 5)] = 0.0  # move_right destination
        model.V[(5, 6)] = 0.0  # move_down destination
        model.h_t = 0.8

        counts = {a: 0 for a in ["move_left", "move_up", "move_right", "move_down"]}
        p = make_perception(x=5, y=5, food=[], last_action_result={})

        for _ in range(200):
            action = model.decide(p)
            if action.name in counts:
                counts[action.name] += 1

        toward_high = counts["move_left"] + counts["move_up"]
        toward_low = counts["move_right"] + counts["move_down"]
        assert toward_high > toward_low, (
            f"Expected more moves toward high-V cells, got high={toward_high}, low={toward_low}"
        )


# ---------------------------------------------------------------------------
# B4 – Hunger modulates approach probability
# ---------------------------------------------------------------------------

class TestB4HungerModulatesApproach:
    """Higher hunger increases P(approach to food-rich cell)."""

    def test_high_hunger_increases_eat_probability(self):
        # With food at current cell, eat value = mu * h_t * V(pos)
        # Higher h_t → higher Q_Pav['eat'] → higher P_a['eat']

        model_low = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model_low.h_t = 0.1
        model_low.V[(5, 5)] = 1.0

        model_high = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model_high.h_t = 0.9
        model_high.V[(5, 5)] = 1.0

        food = [make_food(5, 5)]
        p = make_perception(x=5, y=5, food=food)

        q_low = model_low._compute_qpav(p)
        p_low = model_low._softmax(q_low)

        q_high = model_high._compute_qpav(p)
        p_high = model_high._softmax(q_high)

        assert p_high["eat"] > p_low["eat"], (
            f"High hunger should increase P(eat): low={p_low['eat']:.4f}, high={p_high['eat']:.4f}"
        )

    def test_high_hunger_increases_approach_to_food_cell(self):
        # Place food at (6,5); agent at (5,5); move_right approaches it
        model_low = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model_low.h_t = 0.1
        model_low.V[(6, 5)] = 1.0

        model_high = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model_high.h_t = 0.9
        model_high.V[(6, 5)] = 1.0

        p = make_perception(x=5, y=5, food=[])

        q_low = model_low._compute_qpav(p)
        pa_low = model_low._softmax(q_low)

        q_high = model_high._compute_qpav(p)
        pa_high = model_high._softmax(q_high)

        assert pa_high["move_right"] > pa_low["move_right"], (
            f"High hunger should raise P(move_right toward V=1 cell): "
            f"low={pa_low['move_right']:.4f}, high={pa_high['move_right']:.4f}"
        )


# ---------------------------------------------------------------------------
# B5 – Extinction: V decreases without reward
# ---------------------------------------------------------------------------

class TestB5Extinction:
    """After training V[(5,5)]=1.0, visiting without food causes V to decay below 0.5."""

    def test_v_decreases_over_20_unrewarded_visits(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.V[(5, 5)] = 1.0  # Pre-trained

        for _ in range(20):
            p = make_perception(x=5, y=5, food=[], last_action_result={})
            model.update(Action(name="stay"), 0.0, p)

        v = model.V.get((5, 5), 0.0)
        assert v < 0.5, f"V[(5,5)] should be < 0.5 after 20 unrewarded visits, got {v:.4f}"

    def test_v_never_goes_below_zero(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.V[(5, 5)] = 0.01

        for _ in range(50):
            p = make_perception(x=5, y=5, food=[], last_action_result={})
            model.update(Action(name="stay"), 0.0, p)

        v = model.V.get((5, 5), 0.0)
        assert v >= 0.0, f"V[(5,5)] should not go below 0.0, got {v:.6f}"


# ---------------------------------------------------------------------------
# B6 – Softmax stochasticity with moderate beta
# ---------------------------------------------------------------------------

class TestB6SoftmaxStochasticity:
    """With moderate beta, sub-optimal actions are occasionally selected."""

    def test_non_greedy_actions_selected(self):
        random.seed(0)
        # Use lower beta for more exploration
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel(beta=2.0)
        # Strong value gradient: only move_right has high V
        model.V[(6, 5)] = 1.0
        model.h_t = 0.8

        p = make_perception(x=5, y=5, food=[])

        action_counts = {}
        for _ in range(200):
            a = model.decide(p)
            action_counts[a.name] = action_counts.get(a.name, 0) + 1

        # move_right should dominate but others must appear
        greedy_count = action_counts.get("move_right", 0)
        non_greedy = sum(v for k, v in action_counts.items() if k != "move_right")
        assert greedy_count > 0, "Greedy action should be chosen sometimes"
        assert non_greedy > 0, (
            f"Non-greedy actions should be chosen occasionally; "
            f"counts={action_counts}"
        )

    def test_all_valid_actions_can_be_chosen(self):
        """With very low beta (high temperature), all valid actions should appear."""
        random.seed(7)
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel(beta=0.1)
        model.h_t = 0.5

        p = make_perception(x=5, y=5, food=[])
        action_counts = {}
        for _ in range(500):
            a = model.decide(p)
            action_counts[a.name] = action_counts.get(a.name, 0) + 1

        # At near-uniform temperature, at least 4 valid move actions + stay should appear
        # (eat will be -1e9, so effectively probability 0)
        valid_actions = {"move_up", "move_down", "move_left", "move_right", "stay"}
        chosen_valid = valid_actions.intersection(action_counts.keys())
        assert len(chosen_valid) >= 4, (
            f"At low beta, many actions should appear; got counts={action_counts}"
        )


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

class TestStructural:
    """Verify model contract compliance."""

    def test_get_state_has_q_values(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        state = model.get_state()
        assert "q_values" in state, "get_state() must return 'q_values' key"
        assert isinstance(state["q_values"], dict), "q_values must be a dict"

    def test_q_values_map_to_floats(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        p = make_perception(x=5, y=5)
        model.update(Action("stay"), 0.0, p)
        state = model.get_state()
        for k, v in state["q_values"].items():
            assert isinstance(k, str), f"q_values key must be str, got {type(k)}"
            assert isinstance(v, float), f"q_values value must be float, got {type(v)}"

    def test_decide_returns_action(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        p = make_perception(x=3, y=3)
        action = model.decide(p)
        assert isinstance(action, Action)
        assert action.name in model.ACTION_NAMES

    def test_decide_does_not_mutate_state(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.h_t = 0.6
        model.V[(3, 3)] = 0.7
        p = make_perception(x=3, y=3)
        h_before = model.h_t
        v_before = model.V.get((3, 3))
        model.decide(p)
        assert model.h_t == h_before, "decide() must not mutate h_t"
        assert model.V.get((3, 3)) == v_before, "decide() must not mutate V"

    def test_rpe_rule_r1(self):
        """delta_t = r_t - V(s) (R1)."""
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.V[(2, 3)] = 0.4
        p = make_perception(x=2, y=3)
        model.update(Action("stay"), 0.7, p)
        # delta_t computed before V update; should be 0.7 - 0.4 = 0.3
        # But V is updated during update(), so check delta_t stored
        assert abs(model.delta_t - 0.3) < 1e-9, (
            f"Expected delta_t=0.3, got {model.delta_t}"
        )

    def test_value_update_rule_r2(self):
        """V(s) = clip(V(s) + alpha * delta_t, 0, R_max) (R2)."""
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel(alpha=0.15)
        model.V[(2, 3)] = 0.4
        p = make_perception(x=2, y=3)
        model.update(Action("stay"), 0.7, p)
        expected_v = 0.4 + 0.15 * (0.7 - 0.4)  # 0.4 + 0.045 = 0.445
        assert abs(model.V[(2, 3)] - expected_v) < 1e-9, (
            f"Expected V=0.445, got {model.V[(2, 3)]}"
        )

    def test_hunger_decreases_on_eat_success(self):
        """Hunger decreases by gamma_sat when eat succeeds (R3)."""
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        model.h_t = 0.8
        p = make_perception(x=5, y=5, food=[make_food(5, 5)],
                            last_action_result={"consumed": True})
        model.update(Action("eat"), 1.0, p)
        expected_h = model._clip(0.8 + 0.02 - 0.20, 0.0, 1.0)  # 0.62
        assert abs(model.h_t - expected_h) < 1e-9, (
            f"Expected h_t={expected_h:.3f}, got {model.h_t:.3f}"
        )

    def test_oob_actions_penalized(self):
        """Out-of-bounds movement should get Q_Pav = -1e9."""
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        p = make_perception(x=0, y=0, grid_w=10, grid_h=10)
        q = model._compute_qpav(p)
        assert q["move_left"] == -1e9, "move_left from x=0 should be -1e9"
        assert q["move_up"] == -1e9, "move_up from y=0 should be -1e9"

    def test_softmax_probabilities_sum_to_one(self):
        model = RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel()
        p = make_perception(x=5, y=5, food=[make_food(5, 5)])
        q = model._compute_qpav(p)
        probs = model._softmax(q)
        total = sum(probs.values())
        assert abs(total - 1.0) < 1e-9, f"Softmax probabilities must sum to 1.0, got {total}"
