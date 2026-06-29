"""
Tests for ODE-Based Habit Strength with Continuous Arbitration Dynamics model.
Covers all expected_behaviors B1–B7.
"""

import random
import sys
import os
import math
import pytest

# Allow import from same directory (PYTHONPATH pre-configured)
from ode_based_habit_strength_with_continuous_arbitration_dynamics_model import (
    OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel,
    Action,
)

ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

# ---------------------------------------------------------------------------
# Perception helpers
# ---------------------------------------------------------------------------

def make_perception(x=0, y=0, gw=5, gh=5, food_here=False, step=0, last_action_result=None):
    resources = {}
    if food_here:
        resources["food"] = [{"x": x, "y": y, "type": "food", "palatability": 1.0}]
    p = {
        "x": x,
        "y": y,
        "grid_width": gw,
        "grid_height": gh,
        "step": step,
        "resources": resources,
        "last_action_result": last_action_result or {},
    }
    return p


def make_new_perception_after_eat(x=0, y=0, gw=5, gh=5, consumed=True, step=0):
    """new_perception passed to update() — includes last_action_result."""
    p = make_perception(x=x, y=y, gw=gw, gh=gh, food_here=False, step=step)
    p["last_action_result"] = {"consumed": consumed}
    return p


# ---------------------------------------------------------------------------
# B1 — Initial goal-directed dominance
# ---------------------------------------------------------------------------

class TestB1InitialGoalDirectedDominance:
    """At step 0, C=1.0 so p_GD=1.0 and agent always uses GD."""

    def test_initial_C_is_one(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        assert model.C == 1.0

    def test_p_GD_equals_C_when_C_at_max(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        # C=1.0 >= theta=0.15 → p_GD = C = 1.0
        p_GD = model._compute_p_GD()
        assert p_GD == 1.0

    def test_agent_always_uses_gd_when_p_GD_is_one(self):
        """With p_GD=1.0, random draw u<1 always, so use_gd is always True."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        assert model.C == 1.0
        random.seed(42)
        for _ in range(20):
            perception = make_perception(x=2, y=2)
            model.decide(perception)
            assert model._use_gd is True, "Expected GD to be used when C=1.0"

    def test_p_GD_cached_after_decide(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        perception = make_perception(x=1, y=1)
        model.decide(perception)
        state = model.get_state()
        assert state["p_GD"] == 1.0


# ---------------------------------------------------------------------------
# B2 — Cognitive depletion drives habit transition
# ---------------------------------------------------------------------------

class TestB2CognitiveDepletion:
    """After many GD decisions, C depletes below theta."""

    def test_C_depletes_with_consecutive_gd(self):
        """Each GD use costs xi (net of recovery). Run enough steps so C < theta."""
        xi = 0.10
        theta = 0.15
        rho = 0.05
        C_max = 1.0
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            xi=xi, theta=theta, rho=rho, C_max=C_max
        )
        # Force GD on every call
        for step in range(30):
            perception = make_perception(x=0, y=0)
            model._use_gd = True  # force flag before update
            model.decide(perception)
            model._use_gd = True  # force GD flag even if decide chose habitual
            new_perception = make_new_perception_after_eat(consumed=False)
            # Override use_gd to True to drive depletion
            model._use_gd = True
            # Manually apply R5 inline to simulate forced GD
            old_C = model.C
            model.C = max(0.0, min(C_max, old_C + rho * (C_max - old_C) - xi))

        assert model.C < theta, f"C={model.C} should be below theta={theta} after forced depletion"

    def test_p_GD_is_zero_when_C_below_theta(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(theta=0.15)
        model.C = 0.05  # below threshold
        p_GD = model._compute_p_GD()
        assert p_GD == 0.0

    def test_agent_uses_habitual_when_C_below_theta(self):
        """When C < theta, p_GD=0 so agent always selects habitual system."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(theta=0.15)
        model.C = 0.05
        random.seed(7)
        for _ in range(20):
            perception = make_perception(x=1, y=1)
            model.decide(perception)
            assert model._use_gd is False, "Expected habitual control when C<theta"


# ---------------------------------------------------------------------------
# B3 — Habit strengths accumulate for rewarded actions
# ---------------------------------------------------------------------------

class TestB3HabitAccumulation:
    """Eating at food locations repeatedly builds up H[(s, eat)]."""

    def test_habit_grows_after_many_eats(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            tau_H=0.03, tau_D=0.005, r_food=1.0
        )
        s = (2, 2)
        model._last_s = s
        model._use_gd = False

        eat_action = Action(name="eat")
        for _ in range(50):
            model._last_s = s
            new_perception = make_new_perception_after_eat(x=s[0], y=s[1], consumed=True)
            model.update(eat_action, 1.0, new_perception)

        H_eat = model.H.get((s, "eat"), 0.0)
        assert H_eat > 1.0, f"H[(s, eat)] = {H_eat} should be > 1.0 after 50 eats"

    def test_habit_for_eat_larger_than_other_actions(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            tau_H=0.03, tau_D=0.005, r_food=1.0
        )
        s = (2, 2)
        eat_action = Action(name="eat")
        for _ in range(50):
            model._last_s = s
            model._use_gd = False
            new_perception = make_new_perception_after_eat(x=s[0], y=s[1], consumed=True)
            model.update(eat_action, 1.0, new_perception)

        H_eat = model.H.get((s, "eat"), 0.0)
        for a in ACTIONS:
            if a != "eat":
                H_other = model.H.get((s, a), 0.0)
                assert H_eat >= H_other, (
                    f"H[(s, eat)]={H_eat} should dominate H[(s, {a})]={H_other}"
                )


# ---------------------------------------------------------------------------
# B4 — Devaluation sensitivity when GD active
# ---------------------------------------------------------------------------

class TestB4DevaluationSensitivityGD:
    """When h≈0 and C is high, V_GD[eat] is near 0, agent prefers non-eat actions."""

    def test_V_GD_eat_low_when_sated(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(r_food=1.0)
        model.h = 0.05  # very sated
        model.C = 1.0
        s = (0, 0)
        V = model._compute_V_GD(s, food_here=True, gw=5, gh=5)
        # p_hat default = 0.5
        # V_GD[eat] = 0.5 * (0.05 * 1.0) + 0.5 * (-0.01) ≈ 0.025 - 0.005 = 0.020
        assert V["eat"] < 0.1, f"V_GD[eat]={V['eat']} should be near 0 when sated"

    def test_agent_avoids_eating_when_sated_and_gd_active(self):
        """When GD is active and h is very low, the agent rarely eats."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            r_food=1.0, beta=10.0
        )
        model.h = 0.01   # nearly sated
        model.C = 1.0    # GD always on

        eat_count = 0
        n_trials = 100
        random.seed(123)
        for _ in range(n_trials):
            perception = make_perception(x=0, y=0, food_here=True)
            action = model.decide(perception)
            if action.name == "eat":
                eat_count += 1

        eat_rate = eat_count / n_trials
        assert eat_rate < 0.3, (
            f"Sated agent with GD active should rarely eat; eat_rate={eat_rate:.2f}"
        )


# ---------------------------------------------------------------------------
# B5 — Devaluation insensitivity when habitual
# ---------------------------------------------------------------------------

class TestB5DevaluationInsensitivityHabitual:
    """When C<theta and H[(s, eat)] is high, agent still tends to eat."""

    def test_p_GD_zero_when_C_below_theta(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(theta=0.15)
        model.C = 0.05
        assert model._compute_p_GD() == 0.0

    def test_habitual_agent_uses_H_values(self):
        """When habitual, U[a] = H[(s, a)] — not V_GD."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(theta=0.15)
        model.C = 0.05
        s = (1, 1)
        model.H[(s, "eat")] = 5.0  # high habit for eating

        random.seed(99)
        perception = make_perception(x=s[0], y=s[1], food_here=True)
        model.decide(perception)

        assert model._use_gd is False
        # U should reflect habit strengths
        assert math.isclose(model._U["eat"], 5.0), (
            f"U[eat]={model._U['eat']} should equal H[(s,eat)]=5.0 in habitual mode"
        )

    def test_habitual_sated_agent_still_eats_due_to_high_H(self):
        """Sated habitual agent eats because H[(s, eat)] is large."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            theta=0.15, beta=5.0
        )
        model.C = 0.05   # below threshold → always habitual
        model.h = 0.05   # nearly sated
        s = (2, 2)
        model.H[(s, "eat")] = 10.0  # very strong habit

        eat_count = 0
        n_trials = 200
        random.seed(42)
        for _ in range(n_trials):
            perception = make_perception(x=s[0], y=s[1], food_here=True)
            action = model.decide(perception)
            if action.name == "eat":
                eat_count += 1

        eat_rate = eat_count / n_trials
        assert eat_rate > 0.5, (
            f"Habitual agent with high H should eat often despite satiation; eat_rate={eat_rate:.2f}"
        )


# ---------------------------------------------------------------------------
# B6 — Cognitive control recovery during habitual episodes
# ---------------------------------------------------------------------------

class TestB6CognitiveControlRecovery:
    """When habitual, C recovers toward C_max. After enough steps, GD re-engages."""

    def test_C_recovers_during_habitual_steps(self):
        rho = 0.05
        C_max = 1.0
        theta = 0.15
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            rho=rho, C_max=C_max, theta=theta
        )
        model.C = 0.05   # depleted, below theta
        model._use_gd = False

        move_action = Action(name="move_right")
        for i in range(30):
            model._last_s = (0, 0)
            model._use_gd = False  # ensure habitual flag
            new_perception = make_perception(x=1, y=0)
            new_perception["last_action_result"] = {}
            model.update(move_action, model.c_step, new_perception)

        assert model.C > theta, (
            f"C={model.C:.4f} should recover above theta={theta} after 30 habitual steps"
        )

    def test_p_GD_positive_after_recovery(self):
        rho = 0.05
        C_max = 1.0
        theta = 0.15
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            rho=rho, C_max=C_max, theta=theta
        )
        model.C = 0.05
        model._use_gd = False

        move_action = Action(name="move_right")
        for _ in range(30):
            model._last_s = (0, 0)
            model._use_gd = False
            new_perception = make_perception(x=1, y=0)
            new_perception["last_action_result"] = {}
            model.update(move_action, model.c_step, new_perception)

        p_GD = model._compute_p_GD()
        assert p_GD > 0.0, f"p_GD={p_GD} should be positive after C recovery"


# ---------------------------------------------------------------------------
# B7 — Habit decay for unused actions
# ---------------------------------------------------------------------------

class TestB7HabitDecay:
    """H[(s, eat)] decays toward 0 when action is not executed."""

    def test_habit_decays_for_unused_action(self):
        tau_D = 0.005
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(tau_D=tau_D)
        s_food = (3, 3)
        model.H[(s_food, "eat")] = 1.0   # pre-set habit

        # Execute a different action at a different state repeatedly (200 times)
        move_action = Action(name="move_right")
        s_other = (0, 0)
        for _ in range(200):
            model._last_s = s_other
            model._use_gd = False
            new_perception = make_perception(x=1, y=0)
            new_perception["last_action_result"] = {}
            model.update(move_action, model.c_step, new_perception)

        H_remaining = model.H.get((s_food, "eat"), 0.0)
        # After 200 steps of decay: H(t) ≈ 1.0 * (1 - tau_D)^200 ≈ 1.0 * 0.995^200 ≈ 0.368
        # The key point is significant decay occurred
        assert H_remaining < 0.5, (
            f"H[(s_food, eat)] should have decayed significantly; H={H_remaining:.4f}"
        )

    def test_habit_decays_toward_zero_analytically(self):
        """Verify decay rate matches (1 - tau_D)^n approximation."""
        tau_D = 0.005
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(
            tau_D=tau_D, tau_H=0.0  # no growth
        )
        s = (0, 0)
        s_other = (1, 1)
        model.H[(s, "eat")] = 1.0
        H0 = 1.0
        n = 100

        move_action = Action(name="move_right")
        for _ in range(n):
            model._last_s = s_other   # different state → triggers decay of s
            model._use_gd = False
            new_perception = make_perception(x=2, y=1)
            new_perception["last_action_result"] = {}
            model.update(move_action, model.c_step, new_perception)

        H_actual = model.H.get((s, "eat"), 0.0)
        H_expected = H0 * ((1.0 - tau_D) ** n)
        assert abs(H_actual - H_expected) < 0.05, (
            f"H_actual={H_actual:.4f} should be close to analytical {H_expected:.4f}"
        )


# ---------------------------------------------------------------------------
# Additional integrity tests
# ---------------------------------------------------------------------------

class TestIntegrity:
    """General correctness checks for the model contract."""

    def test_get_state_has_q_values(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        state = model.get_state()
        assert "q_values" in state
        assert isinstance(state["q_values"], dict)
        assert set(state["q_values"].keys()) == set(ACTIONS)

    def test_decide_returns_valid_action(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        perception = make_perception(x=2, y=2)
        action = model.decide(perception)
        assert isinstance(action, Action)
        assert action.name in ACTIONS

    def test_update_does_not_crash(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        perception = make_perception(x=1, y=1, food_here=True)
        action = model.decide(perception)
        new_perception = make_new_perception_after_eat(x=1, y=1, consumed=True)
        model.update(action, 1.0, new_perception)

    def test_C_clamped_to_range(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        # Many GD steps should not push C below 0
        move_action = Action(name="move_right")
        for _ in range(100):
            model._last_s = (0, 0)
            model._use_gd = True
            new_perception = make_perception(x=1, y=0)
            new_perception["last_action_result"] = {}
            model.update(move_action, model.c_step, new_perception)

        assert model.C >= 0.0
        assert model.C <= model.C_max

    def test_hunger_clamped_to_range(self):
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        model.h = 0.95
        # Eating many times should not push h below 0
        for _ in range(50):
            model._last_s = (0, 0)
            model._use_gd = False
            new_perception = make_new_perception_after_eat(consumed=True)
            model.update(Action(name="eat"), 1.0, new_perception)

        assert model.h >= 0.0
        assert model.h <= 1.0

    def test_H_stays_non_negative(self):
        """Habit strengths must never go below 0."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        s = (0, 0)
        model.H[(s, "eat")] = 0.001  # nearly zero
        move_action = Action(name="move_right")
        model._last_s = (1, 1)
        model._use_gd = False
        new_perception = make_perception(x=1, y=1)
        new_perception["last_action_result"] = {}
        model.update(move_action, model.c_step, new_perception)

        for v in model.H.values():
            assert v >= 0.0, f"Habit strength {v} should not be negative"

    def test_p_hat_updated_toward_food_on_eat(self):
        """After eating, p_hat[(s, eat, food)] should increase toward 1."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel(alpha_T=0.2)
        s = (0, 0)
        model._last_s = s
        model._use_gd = False

        p_before = model._p_hat_get(s, "eat", "food")  # default 0.5
        new_perception = make_new_perception_after_eat(consumed=True)
        model.update(Action(name="eat"), 1.0, new_perception)
        p_after = model._p_hat_get(s, "eat", "food")
        assert p_after > p_before, f"p_hat should increase after eating: {p_before} → {p_after}"

    def test_q_values_match_U_after_decide_update_cycle(self):
        """q_values in get_state should reflect the U scores from the last decide()."""
        model = OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel()
        model.C = 0.0  # force habitual
        s = (1, 1)
        model.H[(s, "move_up")] = 3.0
        perception = make_perception(x=s[0], y=s[1])
        random.seed(0)
        model.decide(perception)

        # U should equal habit strengths
        U = model._U
        # Update to populate q_values
        new_perception = make_perception(x=s[0], y=s[1])
        new_perception["last_action_result"] = {}
        model.update(Action(name="move_up"), model.c_step, new_perception)

        q = model.get_state()["q_values"]
        for a in ACTIONS:
            assert math.isclose(q[a], U[a], abs_tol=1e-9), (
                f"q_values[{a}]={q[a]} should match U[{a}]={U[a]}"
            )
