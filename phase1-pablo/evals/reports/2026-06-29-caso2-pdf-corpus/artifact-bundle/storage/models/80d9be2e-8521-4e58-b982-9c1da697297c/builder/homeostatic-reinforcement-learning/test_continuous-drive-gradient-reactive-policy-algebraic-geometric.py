"""
Tests for ContinuousDriveGradientReactivePolicyAlgebraicGeometricModel

Expected behaviors tested:
  B1 - Hungry agent moves toward nearest food
  B2 - Sated agent is indifferent to food location (alliesthesia)
  B3 - Eating gated by satiation threshold
  B4 - Hunger drifts upward without food consumption
  B5 - Higher hunger leads to more directed movement probability toward food
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from continuous_drive_gradient_reactive_policy_algebraic_geometric_model import (
    ContinuousDriveGradientReactivePolicyAlgebraicGeometricModel as Model,
    Action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, grid_w=10, grid_h=10, food=None, last_action_result=None):
    """Build a minimal perception dict."""
    return {
        "x": x,
        "y": y,
        "grid_width": grid_w,
        "grid_height": grid_h,
        "step": 0,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def make_food(x, y, nutrition=3.0):
    return {"x": x, "y": y, "nutrition": nutrition}


def run_update(model, action_name, new_perception, consumed=False):
    """Helper to call update with appropriate last_action_result."""
    new_perception = dict(new_perception)
    new_perception["last_action_result"] = {"consumed": consumed} if action_name == "eat" else {}
    model.update(Action(name=action_name), 0.0, new_perception)


# ---------------------------------------------------------------------------
# B1: Hungry agent moves toward nearest food over 5 steps
# ---------------------------------------------------------------------------

class TestB1HungryAgentMovesTowardFood:
    def test_hungry_agent_moves_toward_food(self):
        """
        With h_t=8.0, food placed 5 cells to the right, run 5 steps.
        Expect Manhattan distance to food strictly decreases (or at least ends lower).
        """
        random.seed(42)
        model = Model(beta=20.0)  # high beta for near-deterministic selection
        model.h_t = 8.0

        # Agent at (0,5), food at (5,5) — 5 cells to the right
        food = [make_food(5, 5)]
        agent_x, agent_y = 0, 5

        initial_dist = abs(agent_x - 5) + abs(agent_y - 5)  # 5

        for _ in range(5):
            perception = make_perception(x=agent_x, y=agent_y, grid_w=10, grid_h=10, food=food)
            action = model.decide(perception)
            # Apply action to move agent
            dx, dy = {"move_right": (1, 0), "move_left": (-1, 0),
                       "move_up": (0, -1), "move_down": (0, 1),
                       "stay": (0, 0), "eat": (0, 0)}.get(action.name, (0, 0))
            agent_x = max(0, min(9, agent_x + dx))
            agent_y = max(0, min(9, agent_y + dy))
            new_perception = make_perception(x=agent_x, y=agent_y, grid_w=10, grid_h=10, food=food)
            run_update(model, action.name, new_perception, consumed=False)

        final_dist = abs(agent_x - 5) + abs(agent_y - 5)
        assert final_dist < initial_dist, (
            f"Expected agent to move closer to food (initial_dist={initial_dist}, "
            f"final_dist={final_dist})"
        )


# ---------------------------------------------------------------------------
# B2: Sated agent is indifferent to food location (alliesthesia)
# ---------------------------------------------------------------------------

class TestB2SatedAgentIndifferentToFood:
    def test_movement_utilities_near_zero_when_sated(self):
        """
        When h_t=0.0 (fully sated), drive D_t=0.
        Movement utilities U_move = w_prox * D_t * Prox_a = 0 for all directions.
        """
        model = Model()
        model.h_t = 0.0  # fully sated

        # Food at (9,5) — far away
        food = [make_food(9, 5)]
        perception = make_perception(x=0, y=5, grid_w=10, grid_h=10, food=food)

        utilities, D_t, _, _ = model._compute_utilities(perception)

        # All movement utilities should be exactly 0 (drive is 0)
        for move in ["move_up", "move_down", "move_left", "move_right"]:
            assert abs(utilities[move]) < 1e-10, (
                f"Expected U_{move}≈0 when sated, got {utilities[move]}"
            )
        assert D_t == 0.0, f"Expected D_t=0 when sated, got {D_t}"


# ---------------------------------------------------------------------------
# B3: Eating gated by satiation threshold
# ---------------------------------------------------------------------------

class TestB3EatingSatiationGate:
    def test_eat_selected_with_high_probability_when_hungry(self):
        """
        h_t=5.0, on food cell, beta=20 → eat should be the highest-utility action
        and selected with high probability.
        """
        random.seed(0)
        model = Model(beta=20.0)
        model.h_t = 5.0

        food = [make_food(3, 3)]
        perception = make_perception(x=3, y=3, grid_w=10, grid_h=10, food=food)

        utilities, _, _, _ = model._compute_utilities(perception)
        assert utilities["eat"] > -1e8, "Eat utility should not be suppressed when hungry"
        assert utilities["eat"] > max(
            utilities["move_up"], utilities["move_down"],
            utilities["move_left"], utilities["move_right"],
            utilities["stay"]
        ), "Eat should have highest utility when hungry on food cell"

        # Check eat is selected frequently
        eat_count = sum(
            1 for _ in range(200)
            if model.decide(perception).name == "eat"
        )
        assert eat_count > 150, f"Expected eat to dominate; got {eat_count}/200"

    def test_eat_suppressed_when_sated(self):
        """
        h_t=0.2 < eta=0.5 → eat utility must be -1e9 (satiation gate).
        """
        model = Model(eta=0.5)
        model.h_t = 0.2  # below threshold

        food = [make_food(3, 3)]
        perception = make_perception(x=3, y=3, grid_w=10, grid_h=10, food=food)

        utilities, D_t, _, _ = model._compute_utilities(perception)
        assert utilities["eat"] == -1e9, (
            f"Expected eat=-1e9 when sated (h_t={model.h_t}, eta={model.eta}), "
            f"got {utilities['eat']}"
        )

    def test_eat_suppressed_no_food_at_position(self):
        """
        Even if hungry, eat is suppressed when not on a food cell.
        """
        model = Model(eta=0.5)
        model.h_t = 8.0

        food = [make_food(9, 9)]  # food far away
        perception = make_perception(x=3, y=3, grid_w=10, grid_h=10, food=food)

        utilities, _, _, _ = model._compute_utilities(perception)
        assert utilities["eat"] == -1e9, (
            f"Expected eat=-1e9 when not on food cell, got {utilities['eat']}"
        )


# ---------------------------------------------------------------------------
# B4: Hunger drifts upward without food consumption
# ---------------------------------------------------------------------------

class TestB4HungerDriftsUpward:
    def test_hunger_increases_by_drift_each_step(self):
        """
        Run 50 update steps without eating.
        h_t should equal min(50 * lambda_drift, h_max).
        """
        model = Model(lambda_drift=0.1, h_max=10.0)
        model.h_t = 0.0

        food = [make_food(9, 9)]  # food far away, never on food cell
        for step in range(50):
            # Simulate update with a non-eat action
            new_perc = make_perception(x=0, y=0, grid_w=10, grid_h=10, food=food)
            new_perc["last_action_result"] = {}
            model.update(Action(name="stay"), 0.0, new_perc)

        expected = min(50 * 0.1, 10.0)
        assert abs(model.h_t - expected) < 1e-9, (
            f"Expected h_t={expected:.4f}, got {model.h_t:.4f}"
        )

    def test_hunger_caps_at_h_max(self):
        """
        After enough steps without eating, h_t should not exceed h_max.
        """
        model = Model(lambda_drift=0.5, h_max=5.0)
        model.h_t = 0.0

        food = [make_food(9, 9)]
        for _ in range(20):
            new_perc = make_perception(x=0, y=0, grid_w=10, grid_h=10, food=food)
            new_perc["last_action_result"] = {}
            model.update(Action(name="stay"), 0.0, new_perc)

        assert model.h_t <= 5.0, f"h_t={model.h_t} exceeded h_max=5.0"
        assert abs(model.h_t - 5.0) < 1e-9, f"Expected h_t=5.0, got {model.h_t}"


# ---------------------------------------------------------------------------
# B5: Higher hunger → higher utility for moving toward food (drive-proportional)
# ---------------------------------------------------------------------------

class TestB5DriveProportionalApproach:
    def _toward_food_utility(self, h_t: float) -> float:
        """
        Compute utility for the food-approaching direction directly via
        _compute_utilities() — analytical, no sampling needed.
        Agent at (4,5), food at (9,5): move_right is the optimal approach.
        """
        model = Model()
        model.h_t = h_t
        food = [make_food(9, 5)]
        perception = make_perception(x=4, y=5, grid_w=10, grid_h=10, food=food)
        utilities, _, _, _ = model._compute_utilities(perception)
        return utilities["move_right"]

    def test_higher_hunger_gives_higher_approach_utility(self):
        """
        U_move_right(h=8) > U_move_right(h=2), because U = w_prox * D_t * Prox_a
        and D_t is monotonically increasing with h_t.
        """
        u_low = self._toward_food_utility(h_t=2.0)
        u_high = self._toward_food_utility(h_t=8.0)
        assert u_high > u_low, (
            f"Expected U_move_right(h=8) > U_move_right(h=2), "
            f"got {u_high:.4f} vs {u_low:.4f}"
        )

    def _p_move_toward_food(self, h_t: float, n_samples: int = 2000) -> float:
        """
        Estimate P(move toward food) via sampling.
        Agent at (4,5), food at (9,5). move_right reduces distance.
        Use moderate beta so both hunger levels produce observable probabilities.
        """
        random.seed(99)
        # Use lower beta so softmax doesn't fully saturate at either h level
        model = Model(beta=2.0)
        model.h_t = h_t
        food = [make_food(9, 5)]
        perception = make_perception(x=4, y=5, grid_w=10, grid_h=10, food=food)
        count = sum(
            1 for _ in range(n_samples)
            if model.decide(perception).name == "move_right"
        )
        return count / n_samples

    def test_higher_hunger_increases_toward_food_probability(self):
        """
        P(move_right | h_t=8) > P(move_right | h_t=2) when food is to the right.
        Uses low beta=2.0 to avoid probability saturation at both levels.
        """
        p_low = self._p_move_toward_food(h_t=2.0)
        p_high = self._p_move_toward_food(h_t=8.0)
        assert p_high > p_low, (
            f"Expected P(move_right|h=8) > P(move_right|h=2), "
            f"got {p_high:.3f} vs {p_low:.3f}"
        )


# ---------------------------------------------------------------------------
# Structural / get_state tests
# ---------------------------------------------------------------------------

class TestGetState:
    def test_get_state_contains_q_values(self):
        """get_state() must include q_values dict with all action keys."""
        model = Model()
        state = model.get_state()
        assert "q_values" in state
        expected_keys = {"move_up", "move_down", "move_left", "move_right", "stay", "eat"}
        assert set(state["q_values"].keys()) == expected_keys

    def test_q_values_updated_after_update_call(self):
        """q_values should reflect utilities computed from new_perception after update()."""
        model = Model()
        model.h_t = 5.0
        food = [make_food(3, 4)]
        new_perc = make_perception(x=3, y=4, grid_w=10, grid_h=10, food=food)
        new_perc["last_action_result"] = {}
        model.update(Action(name="stay"), 0.0, new_perc)
        state = model.get_state()
        # eat utility should not be -1e9 (we're on food cell and hungry)
        assert state["q_values"]["eat"] > -1e8, (
            f"Expected eat utility > -1e8 after update on food cell, got {state['q_values']['eat']}"
        )

    def test_state_contains_all_variables(self):
        """get_state() must contain all specified state variables."""
        model = Model()
        state = model.get_state()
        required_keys = [
            "hunger_level", "homeostatic_setpoint", "drive",
            "position", "resource_positions", "nearest_food_distance",
            "action_utility", "eat_drive_reduction", "proximity_gain",
            "ate_food_flag", "q_values",
        ]
        for k in required_keys:
            assert k in state, f"Missing key '{k}' in get_state()"


# ---------------------------------------------------------------------------
# Rule correctness tests
# ---------------------------------------------------------------------------

class TestDriveFormula:
    def test_drive_quadratic(self):
        """D(h) = m * |h - h_star|^n should be quadratic by default."""
        model = Model(m=1.0, n=2, h_star=0.0)
        assert abs(model._drive(3.0) - 9.0) < 1e-9
        assert model._drive(0.0) == 0.0
        assert abs(model._drive(2.0) - 4.0) < 1e-9   # |2|^2 = 4

    def test_stay_utility_always_negative(self):
        """Staying always incurs drift cost → U_stay <= 0."""
        model = Model()
        for h in [0.0, 1.0, 5.0, 9.9]:
            model.h_t = h
            food = [make_food(9, 9)]
            perception = make_perception(x=0, y=0, food=food)
            utilities, _, _, _ = model._compute_utilities(perception)
            assert utilities["stay"] <= 0.0, (
                f"U_stay={utilities['stay']} > 0 at h_t={h}"
            )


# ---------------------------------------------------------------------------
# Test: ate_food_flag and hunger reduction on eat
# ---------------------------------------------------------------------------

class TestHungerReductionOnEat:
    def test_eating_reduces_hunger(self):
        """
        Successful eat (consumed=True) should reduce h_t by K (minus drift).
        """
        model = Model(K=3.0, lambda_drift=0.1, h_max=10.0)
        model.h_t = 5.0
        initial_h = model.h_t

        food = [make_food(2, 2)]
        new_perc = make_perception(x=2, y=2, grid_w=10, grid_h=10, food=food)
        new_perc["last_action_result"] = {"consumed": True}
        model.update(Action(name="eat"), 1.0, new_perc)

        expected_h = max(0.0, initial_h + 0.1 - 3.0)  # 5 + 0.1 - 3.0 = 2.1
        assert abs(model.h_t - expected_h) < 1e-9, (
            f"Expected h_t={expected_h:.4f} after eating, got {model.h_t:.4f}"
        )
        assert model.ate_food_flag == 1

    def test_failed_eat_does_not_reduce_hunger(self):
        """
        Failed eat (consumed=False) should only apply drift.
        """
        model = Model(K=3.0, lambda_drift=0.1, h_max=10.0)
        model.h_t = 5.0

        food = [make_food(2, 2)]
        new_perc = make_perception(x=2, y=2, grid_w=10, grid_h=10, food=food)
        new_perc["last_action_result"] = {"consumed": False}
        model.update(Action(name="eat"), 0.0, new_perc)

        expected_h = 5.0 + 0.1  # only drift, no reduction
        assert abs(model.h_t - expected_h) < 1e-9, (
            f"Expected h_t={expected_h:.4f} after failed eat, got {model.h_t:.4f}"
        )
        assert model.ate_food_flag == 0
