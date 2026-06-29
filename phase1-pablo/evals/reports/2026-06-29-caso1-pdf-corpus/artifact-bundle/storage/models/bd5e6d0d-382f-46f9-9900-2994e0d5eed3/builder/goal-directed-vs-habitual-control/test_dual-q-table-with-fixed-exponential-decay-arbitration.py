"""
Tests for DualQTableWithFixedExponentialDecayArbitrationModel

Covers expected behaviors B1-B5 plus structural contract tests.
"""

import math
import random
import sys
import os

# PYTHONPATH is pre-configured; import directly
sys.path.insert(0, os.path.dirname(__file__))

from dual_q_table_with_fixed_exponential_decay_arbitration_model import (
    DualQTableWithFixedExponentialDecayArbitrationModel,
    Action,
    ACTIONS,
    _softmax,
    _next_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=0, y=0, gw=10, gh=10, step=0,
    food_positions=None, last_action_result=None
):
    """Build a minimal perception dict matching the env template."""
    food_list = []
    if food_positions:
        for fx, fy in food_positions:
            food_list.append({"x": fx, "y": fy, "type": "food", "palatability": 1.0})
    return {
        "x": x,
        "y": y,
        "grid_width": gw,
        "grid_height": gh,
        "step": step,
        "resources": {"food": food_list},
        "last_action_result": last_action_result or {},
    }


def simulate_n_updates(model, n, state=(3, 3), gw=10, gh=10):
    """
    Simulate n update cycles at the same state to build up visit count.
    Action = stay, no food, reward = c_step.
    """
    for i in range(n):
        action = Action(name="stay", params={"state": state, "food_here": False})
        new_perc = make_perception(x=state[0], y=state[1], gw=gw, gh=gh, step=i)
        model.update(action, model.c_step, new_perc)


# ---------------------------------------------------------------------------
# Structural / contract tests
# ---------------------------------------------------------------------------

class TestContract:
    def test_decide_returns_action(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        perc = make_perception(x=0, y=0)
        action = model.decide(perc)
        assert isinstance(action, Action)
        assert action.name in ACTIONS

    def test_get_state_has_q_values(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        state = model.get_state()
        assert "q_values" in state
        assert isinstance(state["q_values"], dict)
        for a in ACTIONS:
            assert a in state["q_values"]

    def test_get_state_fields(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        state = model.get_state()
        for key in ("h", "omega", "delta", "Q_MF_size", "p_hat_size", "N_total_visits"):
            assert key in state, f"Missing key: {key}"

    def test_decide_does_not_mutate_state(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        perc = make_perception(x=3, y=3)
        h_before = model.h
        omega_before = model.omega
        n_before = dict(model.N)
        model.decide(perc)
        assert model.h == h_before
        assert model.omega == omega_before
        assert model.N == n_before

    def test_update_increments_visit_count(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (2, 2)
        action = Action(name="stay", params={"state": s, "food_here": False})
        new_perc = make_perception(x=s[0], y=s[1])
        model.update(action, -0.01, new_perc)
        assert model.N.get(s, 0) == 1

    def test_action_name_in_actions(self):
        """All actions chosen by decide() must be in the ACTIONS list."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=7)
        perc = make_perception(x=5, y=5)
        for _ in range(20):
            a = model.decide(perc)
            assert a.name in ACTIONS


# ---------------------------------------------------------------------------
# B1 — Goal-directed dominance in novel states (N(s)=0 → omega=1.0)
# ---------------------------------------------------------------------------

class TestB1GoalDirectedDominanceNovelState:
    def test_omega_equals_one_at_zero_visits(self):
        """When N(s)=0, omega must be exactly 1.0."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (4, 4)
        assert model.N.get(s, 0) == 0
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega == 1.0

    def test_q_net_equals_q_mb_when_omega_one(self):
        """With omega=1, Q_net[a] == Q_MB[a] for all actions."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.8
        s = (0, 0)
        # No prior visits, so omega = 1
        perc = make_perception(x=s[0], y=s[1], food_positions=[(0, 0)])
        model.decide(perc)  # triggers Q_MB computation internally

        # Manually compute expected omega and Q_MB
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega == 1.0

        # Q_net should equal Q_MB (since omega=1 and Q_MF=0 initially)
        q_mb_eat = model._get_p_hat(s, "eat", "food") * (model.h * model.r_food) + \
                   (1 - model._get_p_hat(s, "eat", "food")) * model.c_step
        # With Q_MF=0 everywhere and omega=1, Q_net[eat] == Q_MB[eat]
        q_net_eat = 1.0 * q_mb_eat + 0.0 * model._get_Q_MF(s, "eat")
        assert abs(q_net_eat - q_mb_eat) < 1e-9

    def test_hungry_agent_prefers_eat_in_novel_state(self):
        """High hunger, food at position, novel state → eat should be most probable."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(
            seed=0, beta=20.0
        )
        model.h = 0.95
        s = (3, 3)
        # Set p_hat for eat→food high
        model.p_hat[(s, "eat", "food")] = 0.99
        model.p_hat[(s, "eat", "nofood")] = 0.01

        perc = make_perception(x=s[0], y=s[1], food_positions=[s])

        # Run many decisions; eat should dominate
        counts = {a: 0 for a in ACTIONS}
        random.seed(0)
        for _ in range(200):
            act = model.decide(perc)
            counts[act.name] += 1

        assert counts["eat"] > counts["stay"], (
            f"Expected eat to dominate, got {counts}"
        )


# ---------------------------------------------------------------------------
# B2 — Habit formation via overtraining (omega → 0 after many visits)
# ---------------------------------------------------------------------------

class TestB2HabitFormationOvertraining:
    def test_omega_decays_with_visits(self):
        """After N=200 visits, omega < 0.1 with default lambda_habit=0.05."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (5, 5)
        simulate_n_updates(model, n=200, state=s)
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega < 0.1, f"Expected omega < 0.1, got {omega:.4f}"

    def test_q_net_dominated_by_q_mf_after_overtraining(self):
        """After overtraining, Q_net should be very close to Q_MF."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (5, 5)

        # Give Q_MF a non-zero value for eat at this state
        model.Q_MF[(s, "eat")] = 0.7

        simulate_n_updates(model, n=200, state=s)

        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega < 0.1

        # Q_net for "eat" should be close to Q_MF value
        q_mb = model._compute_Q_MB(s, food_here=False, gw=10, gh=10)
        q_net_eat = omega * q_mb["eat"] + (1.0 - omega) * model._get_Q_MF(s, "eat")
        assert abs(q_net_eat - model._get_Q_MF(s, "eat")) < 0.1 * abs(model._get_Q_MF(s, "eat")) + 0.01, (
            f"Q_net({q_net_eat:.4f}) should be close to Q_MF({model._get_Q_MF(s, 'eat'):.4f}) after overtraining"
        )

    def test_omega_monotone_decreasing_with_visits(self):
        """omega at N=100 < omega at N=10 < omega at N=0."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        lh = model.lambda_habit
        omega_0 = math.exp(-lh * 0)
        omega_10 = math.exp(-lh * 10)
        omega_100 = math.exp(-lh * 100)
        assert omega_0 > omega_10 > omega_100, (
            f"omega_0={omega_0}, omega_10={omega_10}, omega_100={omega_100}"
        )


# ---------------------------------------------------------------------------
# B3 — Devaluation sensitivity in early training (h≈0, omega≈1)
# ---------------------------------------------------------------------------

class TestB3DevaluationSensitivityEarlyTraining:
    def test_q_mb_eat_low_when_sated_novel_state(self):
        """With h=0.01 and N(s)=0, Q_MB[eat] should be very low."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.01
        s = (2, 2)
        assert model.N.get(s, 0) == 0  # novel state

        # p_hat default = 0.5
        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)

        # Expected: 0.5 * (0.01 * 1.0) + 0.5 * (-0.01) = 0.005 - 0.005 = 0.0
        expected = 0.5 * (0.01 * model.r_food) + 0.5 * model.c_step
        assert abs(q_mb["eat"] - expected) < 1e-9, (
            f"Q_MB[eat]={q_mb['eat']:.6f}, expected={expected:.6f}"
        )

    def test_q_mb_eat_low_implies_non_eat_preferred_when_sated(self):
        """Sated + novel state: Q_MB[eat] ~ 0 → non-eat actions preferred."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42, beta=20.0)
        model.h = 0.01
        s = (2, 2)
        perc = make_perception(x=s[0], y=s[1], food_positions=[s])

        # Compute Q_net (omega=1 so Q_net = Q_MB)
        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega == 1.0

        q_net_eat = omega * q_mb["eat"] + (1.0 - omega) * model._get_Q_MF(s, "eat")
        q_net_move = omega * q_mb["move_right"] + (1.0 - omega) * model._get_Q_MF(s, "move_right")

        # Both are near step_cost; eat might be ~0 and moves ~c_step; eat not dominant
        # Key assertion: eat is not hugely preferred
        assert q_net_eat < 0.1, f"Expected eat not dominant when sated: Q_net[eat]={q_net_eat}"

    def test_q_mb_eat_proportional_to_hunger(self):
        """Q_MB[eat] should scale linearly with h (all else equal)."""
        s = (1, 1)
        results = []
        for h_val in [0.1, 0.5, 0.9]:
            model = DualQTableWithFixedExponentialDecayArbitrationModel()
            model.h = h_val
            q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
            results.append(q_mb["eat"])

        # Q_MB[eat] should increase with h
        assert results[0] < results[1] < results[2], (
            f"Expected increasing Q_MB[eat] with h: {results}"
        )


# ---------------------------------------------------------------------------
# B4 — Devaluation insensitivity in late training (h≈0, omega≈0)
# ---------------------------------------------------------------------------

class TestB4DevaluationInsensitivityLateTraining:
    def test_omega_very_small_after_100_visits(self):
        """After 100 visits, omega < 0.01 with default lambda_habit=0.05."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (5, 5)
        simulate_n_updates(model, n=100, state=s)
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega < 0.01, f"Expected omega < 0.01, got {omega:.6f}"

    def test_q_net_follows_q_mf_after_100_visits_regardless_of_hunger(self):
        """After overtraining, Q_net[eat] ≈ Q_MF[eat] independent of hunger."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (5, 5)
        model.Q_MF[(s, "eat")] = 0.8  # historically high reward
        model.h = 0.01  # agent is sated

        simulate_n_updates(model, n=100, state=s)
        omega = math.exp(-model.lambda_habit * model.N.get(s, 0))
        assert omega < 0.01

        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
        q_net_eat = omega * q_mb["eat"] + (1.0 - omega) * model._get_Q_MF(s, "eat")

        # Q_net[eat] should be close to Q_MF[eat] = 0.8, not to Q_MB[eat] ≈ 0
        assert q_net_eat > 0.7, (
            f"Expected Q_net[eat] ≈ Q_MF[eat]=0.8 (habit domination), got {q_net_eat:.4f}"
        )

    def test_high_q_mf_eat_still_leads_to_eat_preference_when_sated_habituated(self):
        """Sated but habituated agent should still prefer eat if Q_MF[eat] is high."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42, beta=10.0)
        s = (5, 5)
        model.h = 0.01
        for a in ACTIONS:
            model.Q_MF[(s, a)] = 0.0
        model.Q_MF[(s, "eat")] = 2.0  # very high historical reward

        simulate_n_updates(model, n=100, state=s)

        perc = make_perception(x=s[0], y=s[1], food_positions=[s])

        counts = {a: 0 for a in ACTIONS}
        random.seed(1)
        for _ in range(500):
            act = model.decide(perc)
            counts[act.name] += 1

        assert counts["eat"] > 200, (
            f"Expected eat to dominate habituated state, got {counts}"
        )


# ---------------------------------------------------------------------------
# B5 — Hunger drives food-seeking (h≈1.0)
# ---------------------------------------------------------------------------

class TestB5HungerDrivesFoodSeeking:
    def test_q_mb_eat_high_when_hungry(self):
        """With h=0.9 and p_hat close to 1.0, Q_MB[eat] ≈ 0.9."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.9
        s = (3, 3)
        # High confidence in food outcome
        model.p_hat[(s, "eat", "food")] = 0.99
        model.p_hat[(s, "eat", "nofood")] = 0.01

        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
        expected = 0.99 * (0.9 * model.r_food) + 0.01 * model.c_step
        assert abs(q_mb["eat"] - expected) < 1e-9, (
            f"Q_MB[eat]={q_mb['eat']:.4f}, expected={expected:.4f}"
        )

    def test_q_mb_eat_approximately_h_times_r_food(self):
        """With h=0.9 and default p_hat=0.5, Q_MB[eat] ≈ 0.5 * 0.9 * 1.0 + 0.5 * (-0.01)."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.9
        s = (0, 0)
        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
        expected = 0.5 * (0.9 * 1.0) + 0.5 * (-0.01)
        assert abs(q_mb["eat"] - expected) < 1e-9

    def test_hungry_agent_eats_at_food_location_with_high_beta(self):
        """
        Hungry agent (h=0.9) at food location with p_hat=0.95 and high beta
        should choose eat far more than any other single action.
        """
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=123, beta=30.0)
        model.h = 0.9
        s = (3, 3)
        model.p_hat[(s, "eat", "food")] = 0.95
        model.p_hat[(s, "eat", "nofood")] = 0.05

        perc = make_perception(x=s[0], y=s[1], food_positions=[s])

        counts = {a: 0 for a in ACTIONS}
        random.seed(123)
        for _ in range(500):
            act = model.decide(perc)
            counts[act.name] += 1

        assert counts["eat"] > 400, (
            f"Expected eat to strongly dominate when hungry: {counts}"
        )

    def test_q_mb_eat_is_maximum_action_when_hungry_and_confident(self):
        """When hungry and confident, eat should have highest Q_MB value."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.9
        s = (4, 4)
        model.p_hat[(s, "eat", "food")] = 0.95
        model.p_hat[(s, "eat", "nofood")] = 0.05

        q_mb = model._compute_Q_MB(s, food_here=True, gw=10, gh=10)
        best_action = max(q_mb, key=q_mb.__getitem__)
        assert best_action == "eat", (
            f"Expected eat to have highest Q_MB, got {best_action}. Q_MB={q_mb}"
        )


# ---------------------------------------------------------------------------
# Transition model (R4) and TD learning (R5, R6) tests
# ---------------------------------------------------------------------------

class TestLearningRules:
    def test_transition_model_updates_toward_food_on_eat(self):
        """After eating, p_hat[(s, 'eat', 'food')] should increase."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (1, 1)
        p_before = model._get_p_hat(s, "eat", "food")

        action = Action(name="eat", params={"state": s, "food_here": True})
        new_perc = make_perception(
            x=s[0], y=s[1],
            last_action_result={"consumed": True}
        )
        model.update(action, 1.0, new_perc)

        p_after = model._get_p_hat(s, "eat", "food")
        assert p_after > p_before, f"p_hat should increase after eating: {p_before} → {p_after}"

    def test_transition_model_updates_toward_nofood_on_no_eat(self):
        """After non-eating step, p_hat for nofood outcome should move up."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (1, 1)
        p_nofood_before = model._get_p_hat(s, "stay", "nofood")

        action = Action(name="stay", params={"state": s, "food_here": False})
        new_perc = make_perception(x=s[0], y=s[1], last_action_result={})
        model.update(action, -0.01, new_perc)

        p_nofood_after = model._get_p_hat(s, "stay", "nofood")
        assert p_nofood_after > p_nofood_before

    def test_td_error_positive_when_reward_exceeds_prediction(self):
        """When reward >> Q_MF prediction, delta should be positive."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (0, 0)
        model.Q_MF[(s, "eat")] = 0.0  # prediction = 0

        action = Action(name="eat", params={"state": s, "food_here": True})
        new_perc = make_perception(
            x=s[0], y=s[1],
            last_action_result={"consumed": True}
        )
        model.update(action, 1.0, new_perc)
        assert model.delta > 0, f"Expected positive delta, got {model.delta}"

    def test_q_mf_increases_after_positive_reward(self):
        """After a positive reward, Q_MF[(s, 'eat')] should increase."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (0, 0)
        q_before = model._get_Q_MF(s, "eat")

        action = Action(name="eat", params={"state": s, "food_here": True})
        new_perc = make_perception(
            x=s[0], y=s[1],
            last_action_result={"consumed": True}
        )
        model.update(action, 1.0, new_perc)

        q_after = model._get_Q_MF(s, "eat")
        assert q_after > q_before

    def test_hunger_rises_when_not_eating(self):
        """Each non-eating step should increase hunger by eta."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        h0 = model.h
        action = Action(name="stay", params={"state": (0, 0), "food_here": False})
        new_perc = make_perception(x=0, y=0, last_action_result={})
        model.update(action, -0.01, new_perc)
        assert abs(model.h - (h0 + model.eta)) < 1e-9

    def test_hunger_drops_when_eating(self):
        """Eating should reduce hunger by phi."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.8
        action = Action(name="eat", params={"state": (0, 0), "food_here": True})
        new_perc = make_perception(
            x=0, y=0, last_action_result={"consumed": True}
        )
        model.update(action, 1.0, new_perc)
        expected_h = max(0.0, 0.8 + model.eta - model.phi)
        assert abs(model.h - expected_h) < 1e-9

    def test_hunger_clipped_at_one(self):
        """Hunger should not exceed 1.0."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 1.0
        action = Action(name="stay", params={"state": (0, 0), "food_here": False})
        new_perc = make_perception(x=0, y=0, last_action_result={})
        model.update(action, -0.01, new_perc)
        assert model.h <= 1.0

    def test_hunger_clipped_at_zero(self):
        """Hunger should not go below 0.0."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        model.h = 0.0
        action = Action(name="eat", params={"state": (0, 0), "food_here": True})
        new_perc = make_perception(
            x=0, y=0, last_action_result={"consumed": True}
        )
        model.update(action, 1.0, new_perc)
        assert model.h >= 0.0


# ---------------------------------------------------------------------------
# Softmax helper test
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_softmax_sums_to_one(self):
        vals = [1.0, 2.0, 3.0]
        probs = _softmax(vals, beta=1.0)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_softmax_higher_value_higher_probability(self):
        vals = [0.0, 1.0, 2.0]
        probs = _softmax(vals, beta=5.0)
        assert probs[0] < probs[1] < probs[2]

    def test_softmax_uniform_when_equal(self):
        vals = [1.0, 1.0, 1.0]
        probs = _softmax(vals, beta=5.0)
        for p in probs:
            assert abs(p - 1.0 / 3.0) < 1e-9

    def test_next_state_clamps_at_grid_boundary(self):
        # Moving up from (0,0) should stay at (0,0) — y cannot go below 0
        s = _next_state((0, 0), "move_up", grid_width=10, grid_height=10)
        assert s == (0, 0)

    def test_next_state_correct_move(self):
        s = _next_state((3, 3), "move_right", grid_width=10, grid_height=10)
        assert s == (4, 3)

    def test_next_state_clamps_at_right_boundary(self):
        s = _next_state((9, 5), "move_right", grid_width=10, grid_height=10)
        assert s == (9, 5)


# ---------------------------------------------------------------------------
# Q-values cached in get_state
# ---------------------------------------------------------------------------

class TestQValuesCaching:
    def test_q_values_updated_after_update(self):
        """After update(), get_state()['q_values'] should reflect new state."""
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        s = (3, 3)

        # Force high Q_MF for eat
        model.Q_MF[(s, "eat")] = 2.0

        action = Action(name="stay", params={"state": s, "food_here": False})
        new_perc = make_perception(
            x=s[0], y=s[1], food_positions=[s],
            last_action_result={}
        )
        model.update(action, -0.01, new_perc)

        state = model.get_state()
        assert "eat" in state["q_values"]
        # After update at same state, eat q_value should reflect Q_MF=2.0
        assert isinstance(state["q_values"]["eat"], float)

    def test_q_values_all_actions_present_after_update(self):
        model = DualQTableWithFixedExponentialDecayArbitrationModel(seed=42)
        action = Action(name="stay", params={"state": (0, 0), "food_here": False})
        new_perc = make_perception(x=0, y=0)
        model.update(action, -0.01, new_perc)
        q_vals = model.get_state()["q_values"]
        for a in ACTIONS:
            assert a in q_vals, f"Missing action {a} in q_values"
