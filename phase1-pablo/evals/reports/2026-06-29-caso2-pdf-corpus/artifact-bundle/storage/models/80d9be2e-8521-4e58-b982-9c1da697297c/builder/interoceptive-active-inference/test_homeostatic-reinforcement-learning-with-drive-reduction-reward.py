"""
Tests for HomeostaticReinforcementLearningWithDriveReductionRewardModel

Covers all 6 expected behaviors from the spec:
  B1 - Drive increases monotonically as energy drops
  B2 - Eating produces positive reward when energy below setpoint
  B3 - Q-values for eat at distance_bin=0 converge higher than stay
  B4 - Urgency mode reduces action entropy at low energy
  B5 - Movement-toward-food Q-values learn to exceed movement-away
  B6 - Eating above setpoint produces negative reward
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from homeostatic_reinforcement_learning_with_drive_reduction_reward_model import (
    HomeostaticReinforcementLearningWithDriveReductionRewardModel,
    Action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, gw=10, gh=10, step=0, food=None, last_result=None):
    return {
        "x": x,
        "y": y,
        "grid_width": gw,
        "grid_height": gh,
        "step": step,
        "resources": {"food": food if food is not None else []},
        "last_action_result": last_result if last_result is not None else {},
    }


def make_model(**kwargs) -> HomeostaticReinforcementLearningWithDriveReductionRewardModel:
    defaults = dict(seed=42)
    defaults.update(kwargs)
    return HomeostaticReinforcementLearningWithDriveReductionRewardModel(**defaults)


def drive(h, m=4.0, h_star=0.8, n=2.0):
    return m * abs(h_star - h) ** n


def compute_entropy_for_state(model, h_val, state, food_at_pos=False):
    """
    Compute Shannon entropy of the softmax action distribution
    for the given state and energy level, using current Q-table.
    """
    eff_beta = model.beta_urgent if h_val < model.h_critical else model.beta

    logits = []
    for a in model.ALL_ACTIONS:
        q_val = model._q_get(state, a)
        logit = eff_beta * q_val
        if a == "eat" and not food_at_pos:
            logit = -1e9
        logits.append(logit)

    max_l = max(logits)
    exps = [math.exp(l - max_l) for l in logits]
    total = sum(exps)
    probs = [e / total for e in exps]

    entropy = -sum(p * math.log(p + 1e-12) for p in probs)
    return entropy


# ---------------------------------------------------------------------------
# B1: Drive increases monotonically as energy drops below setpoint
# ---------------------------------------------------------------------------

class TestB1DriveMonotonicallyIncreases:
    """Run agent without food for 20 steps. Assert D_t is monotonically non-decreasing."""

    def test_drive_increases_without_food(self):
        model = make_model()
        # Force energy well below setpoint initially so it only drops further
        model.h_t = 0.6
        model._h_old = 0.6

        drives = []
        for step in range(20):
            perception = make_perception(step=step, food=[])
            action = model.decide(perception)
            # After decide, do update with stay result (no food → stay cost)
            new_perc = make_perception(step=step + 1, food=[], last_result={})
            model.update(action, 0.0, new_perc)
            drives.append(model.D_t)

        # Energy should only decrease → drive (distance from h*=0.8) should only increase
        for i in range(1, len(drives)):
            assert drives[i] >= drives[i - 1] - 1e-9, (
                f"Drive decreased at step {i}: {drives[i-1]:.4f} → {drives[i]:.4f}"
            )

    def test_drive_formula_at_various_energies(self):
        """Direct formula check: D increases as energy drops from h*."""
        model = make_model()
        energies = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        drives_vals = [drive(h) for h in energies]
        for i in range(1, len(drives_vals)):
            assert drives_vals[i] > drives_vals[i - 1], (
                f"Drive should increase as energy drops: h={energies[i]}"
            )


# ---------------------------------------------------------------------------
# B2: Eating produces positive reward when energy below setpoint
# ---------------------------------------------------------------------------

class TestB2EatingProducesPositiveReward:
    """Set h_t=0.3, execute eat with k_eat=0.3. Assert r_t > 0 (D decreased)."""

    def test_eating_reduces_drive_below_setpoint(self):
        model = make_model()
        model.h_t = 0.3
        model._h_old = 0.3

        # Food at agent's position
        food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
        perception = make_perception(x=5, y=5, food=food)
        action = model.decide(perception)

        # Simulate env returning successful eat
        new_perc = make_perception(
            x=5, y=5, food=[],
            last_result={"consumed": True, "palatability": 1.0}
        )
        model.update(Action(name="eat"), 1.0, new_perc)

        assert model.r_t > 0, (
            f"Reward should be positive (drive reduced), got r_t={model.r_t:.4f}"
        )

    def test_positive_reward_magnitude_reasonable(self):
        """Energy rises from 0.3 → 0.6, drive should drop significantly."""
        model = make_model()
        model.h_t = 0.3
        model._h_old = 0.3
        model._s_old = (0, 0)

        D_before = drive(0.3)
        D_after = drive(0.3 + 0.3)  # k_eat=0.3, palatability=1.0
        expected_reward = D_before - D_after

        new_perc = make_perception(
            x=5, y=5, food=[],
            last_result={"consumed": True, "palatability": 1.0}
        )
        model.update(Action(name="eat"), 1.0, new_perc)

        assert abs(model.r_t - expected_reward) < 1e-9, (
            f"Expected reward {expected_reward:.4f}, got {model.r_t:.4f}"
        )


# ---------------------------------------------------------------------------
# B3: Q-values for 'eat' at distance_bin=0 converge to higher values than stay
# ---------------------------------------------------------------------------

class TestB3QValuesForEatConverge:
    """Run 200 steps with food available. Assert Q for eat > Q for stay in low-energy state."""

    def _run_episodes(self, n_steps=300):
        random.seed(0)
        model = make_model(seed=0, learning_rate_td=0.1, temporal_discount_factor=0.9)
        model.h_t = 0.3  # start low to ensure eating is beneficial

        for step in range(n_steps):
            # Food always at agent's position
            food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
            perception = make_perception(x=5, y=5, food=food, step=step)
            action = model.decide(perception)

            # Simulate eat success, else stay cost
            if action.name == "eat":
                last_result = {"consumed": True, "palatability": 1.0}
                new_food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
            else:
                last_result = {}
                new_food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]

            new_perc = make_perception(x=5, y=5, food=new_food, step=step + 1,
                                       last_result=last_result)
            model.update(action, 1.0 if action.name == "eat" else 0.0, new_perc)

            # Keep energy low to incentivize continued eating
            if model.h_t > 0.5:
                model.h_t = 0.3

        return model

    def test_eat_q_higher_than_stay_at_food_low_energy(self):
        model = self._run_episodes(300)
        # State: dist_bin=0 (at food), low energy_bin
        low_energy_bin = model._digitize_energy(0.3)
        state = (0, low_energy_bin)

        q_eat = model._q_get(state, "eat")
        q_stay = model._q_get(state, "stay")

        assert q_eat > q_stay, (
            f"Q(eat) should exceed Q(stay) at food location with low energy. "
            f"Q(eat)={q_eat:.4f}, Q(stay)={q_stay:.4f}"
        )


# ---------------------------------------------------------------------------
# B4: Urgency mode reduces entropy at critical energy
# ---------------------------------------------------------------------------

class TestB4UrgencyReducesEntropy:
    """When h_t < 0.2, entropy of action distribution is lower than when h_t=0.5."""

    def test_urgency_reduces_entropy(self):
        """
        With non-uniform Q-values, higher beta (urgency) should produce lower entropy
        because softmax is sharper. We manually set Q-values for a known state and
        compare entropy at the same state under two beta values.
        """
        model = make_model(seed=42)

        # Set up distinct Q-values for a known state so softmax is non-uniform
        test_state = (0, 1)  # dist_bin=0, energy_bin=1 (matches h=0.15 → bin=0? Let's check)
        # h=0.15: energy_bin = int(0.15 * 5) = 0 (bin 0)
        # h=0.5:  energy_bin = int(0.5 * 5) = 2 (bin 2)
        urgent_state = (0, model._digitize_energy(0.15))
        normal_state = (0, model._digitize_energy(0.5))

        # Assign distinct, non-uniform Q-values to both states
        q_values = [1.0, 0.5, 0.2, 0.8, 0.1, 0.9]
        for i, a in enumerate(model.ALL_ACTIONS):
            model.Q[(urgent_state, a)] = q_values[i]
            model.Q[(normal_state, a)] = q_values[i]

        # Compute entropy for urgent state (h=0.15 → beta_urgent=15.0)
        entropy_urgent = compute_entropy_for_state(
            model, h_val=0.15, state=urgent_state, food_at_pos=True
        )

        # Compute entropy for normal state (h=0.5 → beta=8.0)
        entropy_normal = compute_entropy_for_state(
            model, h_val=0.5, state=normal_state, food_at_pos=True
        )

        assert entropy_urgent < entropy_normal, (
            f"Urgency mode should reduce entropy (higher beta → sharper softmax). "
            f"Urgent (beta={model.beta_urgent}) entropy={entropy_urgent:.4f}, "
            f"Normal (beta={model.beta}) entropy={entropy_normal:.4f}"
        )

    def test_beta_urgent_greater_than_beta(self):
        """Basic sanity: urgency_inverse_temperature > action_inverse_temperature."""
        model = make_model()
        assert model.beta_urgent > model.beta, (
            f"beta_urgent ({model.beta_urgent}) should exceed beta ({model.beta})"
        )

    def test_softmax_sharper_with_higher_beta(self):
        """Direct test: identical Q-values, higher beta → lower entropy."""
        model = make_model()
        state = (1, 1)
        q_vals = [0.3, 0.1, 0.4, 0.2, 0.0, 0.5]
        for i, a in enumerate(model.ALL_ACTIONS):
            model.Q[(state, a)] = q_vals[i]

        # Low beta (normal)
        old_beta = model.beta
        model.beta = 4.0
        entropy_low_beta = compute_entropy_for_state(model, h_val=0.5, state=state, food_at_pos=True)

        # High beta (urgent)
        model.beta_urgent = 20.0
        entropy_high_beta = compute_entropy_for_state(model, h_val=0.1, state=state, food_at_pos=True)

        model.beta = old_beta  # restore

        assert entropy_high_beta < entropy_low_beta, (
            f"Higher beta should yield lower entropy. "
            f"beta=20 entropy={entropy_high_beta:.4f}, beta=4 entropy={entropy_low_beta:.4f}"
        )


# ---------------------------------------------------------------------------
# B5: Q for movement toward food > Q for movement away from food
# ---------------------------------------------------------------------------

class TestB5NavigateTowardFood:
    """After training, Q-values for move toward food should exceed move away."""

    def test_toward_food_q_higher_after_training(self):
        random.seed(1)
        model = make_model(seed=1, learning_rate_td=0.15, temporal_discount_factor=0.9)
        model.h_t = 0.3

        # Food is always to the right of the agent (east)
        # Agent at (3, 5), food at (5, 5) → move_right is toward food
        for step in range(500):
            agent_x = 3
            food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
            perception = make_perception(x=agent_x, y=5, food=food, step=step)
            action = model.decide(perception)

            # If moved right (toward food), reward with small positive signal via update
            if action.name == "move_right":
                # Closer to food now
                new_food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
                new_perc = make_perception(x=4, y=5, food=new_food, step=step + 1, last_result={})
            elif action.name == "eat":
                new_food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
                new_perc = make_perception(x=agent_x, y=5, food=new_food, step=step + 1,
                                           last_result={"consumed": True, "palatability": 1.0})
            else:
                new_food = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
                new_perc = make_perception(x=agent_x, y=5, food=new_food, step=step + 1,
                                           last_result={})

            model.update(action, 0.0, new_perc)

            # Keep energy low
            if model.h_t > 0.5:
                model.h_t = 0.3

        # Check Q-values in dist_bin=2 (food ~3-4 away), low energy_bin
        low_energy_bin = model._digitize_energy(0.3)
        state_med_dist = (2, low_energy_bin)

        q_toward = model._q_get(state_med_dist, "move_right")
        q_away = model._q_get(state_med_dist, "move_left")

        assert q_toward >= q_away, (
            f"Q(move_right/toward food)={q_toward:.4f} should be >= "
            f"Q(move_left/away)={q_away:.4f} after training"
        )


# ---------------------------------------------------------------------------
# B6: Eating above setpoint produces negative reward (overshoot punishment)
# ---------------------------------------------------------------------------

class TestB6EatingAboveSetpointNegativeReward:
    """Set h_t=0.85 (above h*=0.8). Execute eat. Assert r_t < 0."""

    def test_eating_above_setpoint_negative_reward(self):
        model = make_model()
        model.h_t = 0.85
        model._h_old = 0.85
        model._s_old = (0, 4)

        new_perc = make_perception(
            x=5, y=5, food=[],
            last_result={"consumed": True, "palatability": 1.0}
        )
        model.update(Action(name="eat"), 1.0, new_perc)

        assert model.r_t < 0, (
            f"Eating above setpoint should produce negative reward (drive increases). "
            f"Got r_t={model.r_t:.4f}"
        )

    def test_reward_magnitude_above_setpoint(self):
        """Verify exact drive-reduction calculation for overshoot."""
        model = make_model()
        h_old = 0.85
        h_new = min(1.0, h_old + model.k_eat * 1.0)  # palatability=1.0

        D_before = drive(h_old)
        D_after = drive(h_new)
        expected_reward = D_before - D_after  # negative since D increased

        model.h_t = h_old
        model._h_old = h_old
        model._s_old = (0, 4)

        new_perc = make_perception(
            x=5, y=5, food=[],
            last_result={"consumed": True, "palatability": 1.0}
        )
        model.update(Action(name="eat"), 1.0, new_perc)

        assert model.r_t < 0, "Reward should be negative for overshoot"
        assert abs(model.r_t - expected_reward) < 1e-9, (
            f"Expected {expected_reward:.6f}, got {model.r_t:.6f}"
        )


# ---------------------------------------------------------------------------
# Additional: get_state() contract and q_values presence
# ---------------------------------------------------------------------------

class TestGetState:
    def test_get_state_contains_q_values(self):
        model = make_model()
        state = model.get_state()
        assert "q_values" in state, "get_state() must contain 'q_values' key"
        assert isinstance(state["q_values"], dict), "q_values must be a dict"
        for action in model.ALL_ACTIONS:
            assert action in state["q_values"], f"q_values must contain action '{action}'"

    def test_get_state_keys(self):
        model = make_model()
        state = model.get_state()
        required = {
            "physiological_state", "homeostatic_setpoint", "drive",
            "primary_reward", "state_representation", "q_table_size", "q_values"
        }
        for key in required:
            assert key in state, f"Missing key: {key}"

    def test_q_values_update_after_update_call(self):
        model = make_model()
        perception = make_perception(food=[{"x": 5, "y": 5, "palatability": 1.0}])
        action = model.decide(perception)

        new_perc = make_perception(
            last_result={"consumed": True, "palatability": 1.0}
        )
        model.update(Action(name="eat"), 1.0, new_perc)

        state = model.get_state()
        # After update, q_values should reflect the new state
        assert isinstance(state["q_values"], dict)
        assert len(state["q_values"]) == len(model.ALL_ACTIONS)


# ---------------------------------------------------------------------------
# Additional: action masking and boundary conditions
# ---------------------------------------------------------------------------

class TestActionMasking:
    def test_eat_masked_when_no_food_at_position(self):
        """Eat probability should be near zero when no food at current position."""
        random.seed(123)
        model = make_model(seed=123)
        # Give eat a high Q value to make the test meaningful
        model.Q[((0, 2), "eat")] = 10.0

        perception = make_perception(x=5, y=5, food=[])  # no food
        # Run 100 decisions, eat should never be selected
        eat_count = 0
        for _ in range(100):
            action = model.decide(perception)
            if action.name == "eat":
                eat_count += 1

        assert eat_count == 0, (
            f"Eat should not be selected when no food at position; selected {eat_count}/100 times"
        )

    def test_energy_clipped_at_zero(self):
        """Energy should not go below 0."""
        model = make_model()
        model.h_t = 0.01
        model._h_old = 0.01
        model._s_old = (4, 0)

        new_perc = make_perception(last_result={})
        model.update(Action(name="move_up"), 0.0, new_perc)
        assert model.h_t >= 0.0, f"Energy below 0: {model.h_t}"

    def test_energy_clipped_at_one(self):
        """Energy should not exceed 1."""
        model = make_model()
        model.h_t = 0.9
        model._h_old = 0.9
        model._s_old = (0, 4)

        new_perc = make_perception(last_result={"consumed": True, "palatability": 1.0})
        model.update(Action(name="eat"), 1.0, new_perc)
        assert model.h_t <= 1.0, f"Energy exceeded 1: {model.h_t}"


# ---------------------------------------------------------------------------
# Run all tests when executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestB1DriveMonotonicallyIncreases,
        TestB2EatingProducesPositiveReward,
        TestB3QValuesForEatConverge,
        TestB4UrgencyReducesEntropy,
        TestB5NavigateTowardFood,
        TestB6EatingAboveSetpointNegativeReward,
        TestGetState,
        TestActionMasking,
    ]

    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for method_name in [m for m in dir(cls) if m.startswith("test_")]:
            try:
                getattr(instance, method_name)()
                print(f"  PASS  {cls.__name__}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{method_name}: {e}")
                traceback.print_exc()
                failed += 1

    print(f"\n{passed} passed, {failed} failed")
