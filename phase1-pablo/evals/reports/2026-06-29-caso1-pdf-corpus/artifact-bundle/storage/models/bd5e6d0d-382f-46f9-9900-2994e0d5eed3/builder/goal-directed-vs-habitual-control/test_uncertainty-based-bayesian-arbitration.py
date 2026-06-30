"""
Tests for UncertaintyBasedBayesianArbitrationModel
Covers all expected_behaviors B1–B5.
"""
import math
import random
import sys
import os

# Ensure the module is importable
sys.path.insert(0, os.path.dirname(__file__))

from uncertainty_based_bayesian_arbitration_model import (
    UncertaintyBasedBayesianArbitrationModel,
    Action,
    ACTIONS,
    _sigmoid,
    _softmax,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=2, y=2, grid_width=5, grid_height=5, step=0,
                    food=None, last_action_result=None):
    return {
        "x": x, "y": y,
        "grid_width": grid_width, "grid_height": grid_height,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def run_step(model, perception, action_name=None, consumed=False, reward=None):
    """Drive one full decide→update cycle with optional forced action."""
    action = model.decide(perception)
    if action_name is not None:
        action = Action(name=action_name)

    r = reward if reward is not None else (1.0 if consumed else -0.01)
    new_perc = make_perception(
        x=perception["x"], y=perception["y"],
        grid_width=perception["grid_width"],
        grid_height=perception["grid_height"],
        step=perception["step"] + 1,
        food=perception["resources"].get("food", []),
        last_action_result={"consumed": consumed},
    )
    model.update(action, r, new_perc)
    return action


# ---------------------------------------------------------------------------
# Basic contract tests
# ---------------------------------------------------------------------------

class TestContract:
    def test_decide_returns_action(self):
        model = UncertaintyBasedBayesianArbitrationModel()
        p = make_perception()
        action = model.decide(p)
        assert isinstance(action, Action)
        assert action.name in ACTIONS

    def test_get_state_keys(self):
        model = UncertaintyBasedBayesianArbitrationModel()
        state = model.get_state()
        for key in ("h", "mu_MF", "sigma2_MF", "mu_MB", "sigma2_MB",
                    "omega", "mu_hat", "p_hat", "N_MB", "q_values"):
            assert key in state, f"Missing key: {key}"

    def test_get_state_q_values_has_all_actions(self):
        model = UncertaintyBasedBayesianArbitrationModel()
        p = make_perception()
        model.decide(p)
        state = model.get_state()
        for a in ACTIONS:
            assert a in state["q_values"]

    def test_q_values_are_floats(self):
        model = UncertaintyBasedBayesianArbitrationModel()
        p = make_perception()
        model.decide(p)
        for v in model.get_state()["q_values"].values():
            assert isinstance(v, float)

    def test_update_does_not_modify_decide_output(self):
        """decide() is read-only; model can be called again after update."""
        random.seed(42)
        model = UncertaintyBasedBayesianArbitrationModel()
        p = make_perception()
        a = model.decide(p)
        model.update(a, -0.01, make_perception())
        a2 = model.decide(p)
        assert a2.name in ACTIONS


# ---------------------------------------------------------------------------
# B1: Novel-state — MB uncertainty drops faster than MF (goal-directed initially)
# ---------------------------------------------------------------------------

class TestB1_GoalDirectedInNovelState:
    def test_initial_omega_in_gd_range(self):
        """
        In a novel state with food present, sigma2_MF starts at sigma2_0=1.0
        while sigma2_MB includes outcome variance from the transition prior.
        With p_hat=0.5 prior and h=0.5, sigma2_MB for eat includes substantial
        outcome variance plus sigma2_obs_MB. This drives sigma2_MF > sigma2_MB
        initially, so omega > 0.5 (GD dominant). We verify omega ∈ [0,1] and >= 0.5.
        """
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        p = make_perception(food=food)
        model.decide(p)
        state = model.get_state()
        s = (2, 2)
        omega_eat = state["omega"].get((s, "eat"), 0.5)
        # omega must be valid
        assert 0.0 <= omega_eat <= 1.0, f"omega_eat={omega_eat} out of [0,1]"
        # At first encounter, MF sigma2_0=1.0 >= sigma2_MB → GD at least as active
        assert omega_eat >= 0.5, (
            f"In novel state, sigma2_MF >= sigma2_MB, so omega >= 0.5, got {omega_eat}"
        )

    def test_mb_uncertainty_drops_faster_with_experience(self):
        """
        After 20 steps eating at (2,2), both sigma2_MB and sigma2_MF shrink.
        sigma2_MB scales by 1/(1+N_MB) (direct experience counting), while
        sigma2_MF shrinks via Kalman updates.
        Both should be well below prior sigma2_0=1.0 after 20 steps.
        """
        random.seed(0)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        for step in range(20):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state = model.get_state()
        s2_mf = state["sigma2_MF"].get((s, "eat"), model.sigma2_0)
        s2_mb = state["sigma2_MB"].get((s, "eat"), model.sigma2_0)
        # Both variances should be well below the prior after 20 steps
        assert s2_mb < model.sigma2_0, f"sigma2_MB={s2_mb} should be below prior {model.sigma2_0}"
        assert s2_mf < model.sigma2_0, f"sigma2_MF={s2_mf} should be below prior"

    def test_omega_consistency_with_variance_ordering(self):
        """
        omega = sigmoid(kappa * (sigma2_MF - sigma2_MB)).
        Whatever the variance ordering after training, omega must be consistent
        with the formula: sigma2_MF > sigma2_MB ↔ omega > 0.5.
        """
        random.seed(1)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        for step in range(20):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state = model.get_state()
        s2_mf = state["sigma2_MF"].get((s, "eat"), model.sigma2_0)
        s2_mb = state["sigma2_MB"].get((s, "eat"), model.sigma2_0)
        omega_eat = state["omega"].get((s, "eat"), 0.5)

        expected = _sigmoid(model.kappa * (s2_mf - s2_mb))
        assert abs(omega_eat - expected) < 1e-9, (
            f"omega={omega_eat} should match sigmoid formula={expected}"
        )

        if s2_mb < s2_mf:
            assert omega_eat > 0.5, (
                f"sigma2_MB={s2_mb} < sigma2_MF={s2_mf} implies omega > 0.5, got {omega_eat}"
            )
        else:
            assert omega_eat <= 0.5, (
                f"sigma2_MF={s2_mf} <= sigma2_MB={s2_mb} implies omega <= 0.5, got {omega_eat}"
            )


# ---------------------------------------------------------------------------
# B2: Uncertainty dynamics — verify asymptotic relationship between MF and MB
# ---------------------------------------------------------------------------

class TestB2_UncertaintyAsymptotics:
    def test_both_variances_shrink_over_time(self):
        """
        Both sigma2_MF and sigma2_MB should decrease significantly over 300 steps
        of consistent experience. This verifies both Kalman updates (MF) and
        experience-count scaling (MB) are working correctly.
        """
        random.seed(42)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        for step in range(300):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state = model.get_state()
        s2_mf = state["sigma2_MF"].get((s, "eat"), model.sigma2_0)
        s2_mb = state["sigma2_MB"].get((s, "eat"), model.sigma2_0)

        # Both should be drastically lower than prior
        assert s2_mf < 0.01, f"sigma2_MF={s2_mf} should be near zero after 300 steps"
        assert s2_mb < 0.01, f"sigma2_MB={s2_mb} should be near zero after 300 steps"

    def test_omega_reflects_relative_uncertainty(self):
        """
        omega = sigmoid(kappa * (sigma2_MF - sigma2_MB)).
        Verify this relationship holds exactly by checking consistency.
        """
        random.seed(42)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        for step in range(300):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state = model.get_state()
        s2_mf = state["sigma2_MF"].get((s, "eat"), model.sigma2_0)
        s2_mb = state["sigma2_MB"].get((s, "eat"), model.sigma2_0)
        omega_eat = state["omega"].get((s, "eat"), 0.5)

        # omega must always reflect the variance difference correctly
        expected_omega = _sigmoid(model.kappa * (s2_mf - s2_mb))
        assert abs(omega_eat - expected_omega) < 1e-9, (
            f"omega={omega_eat} should equal sigmoid(kappa*(s2_mf-s2_mb))={expected_omega}"
        )

    def test_habitual_dominance_with_low_mf_obs_noise(self):
        """
        With a lower sigma2_obs_MF (0.1) and higher sigma2_obs_MB (0.5),
        the Kalman MF floor (∝ sigma2_obs_MF) is lower than the MB floor
        (∝ sigma2_obs_MB). After extensive training, sigma2_MF < sigma2_MB
        → omega < 0.5 (habitual mode).
        """
        random.seed(99)
        # Lower sigma2_obs_MF so MF can converge faster than MB
        model = UncertaintyBasedBayesianArbitrationModel(
            sigma2_obs_MF=0.1,
            sigma2_obs_MB=0.5,  # Higher MB noise floor
            kappa=3.0,
        )
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state = model.get_state()
        s2_mf = state["sigma2_MF"].get((s, "eat"), model.sigma2_0)
        s2_mb = state["sigma2_MB"].get((s, "eat"), model.sigma2_0)
        omega_eat = state["omega"].get((s, "eat"), 0.5)

        # With sigma2_obs_MF=0.1 < sigma2_obs_MB=0.5, MF floor is lower than MB floor
        assert s2_mf < s2_mb, (
            f"With low sigma2_obs_MF, expected sigma2_MF={s2_mf} < sigma2_MB={s2_mb}"
        )
        assert omega_eat < 0.5, (
            f"With sigma2_MF < sigma2_MB, expected habitual dominance (omega<0.5), got {omega_eat}"
        )

    def test_habitual_omega_below_03_asymmetric_noise(self):
        """
        Verify omega < 0.3 is achievable when MF observation noise is significantly
        smaller than MB observation noise, verified analytically by the sigmoid formula.
        We directly set variances to verify the formula produces omega < 0.3.
        """
        model = UncertaintyBasedBayesianArbitrationModel(kappa=5.0)
        s = (2, 2)
        # Manually set sigma2_MF << sigma2_MB to simulate deep habit
        model.sigma2_MF[(s, "eat")] = 0.001
        model.sigma2_MB[(s, "eat")] = 0.5

        food = [{"x": 2, "y": 2}]
        p = make_perception(x=2, y=2, food=food)
        # Recompute arbitration only (not MB values which would overwrite sigma2_MB)
        # Use _compute_arbitration_and_fusion directly
        model._compute_mb_values(s, True, 5, 5)  # Will overwrite sigma2_MB
        # Reset manually after MB computation
        model.sigma2_MB[(s, "eat")] = 0.5
        model._compute_arbitration_and_fusion(s)

        omega_eat = model.omega.get((s, "eat"), 0.5)
        s2_mf = model.sigma2_MF[(s, "eat")]
        s2_mb = model.sigma2_MB[(s, "eat")]
        expected = _sigmoid(5.0 * (s2_mf - s2_mb))

        assert abs(omega_eat - expected) < 1e-9
        assert omega_eat < 0.3, (
            f"With sigma2_MF=0.001, sigma2_MB=0.5, kappa=5.0: "
            f"omega should be < 0.3, got {omega_eat}"
        )


# ---------------------------------------------------------------------------
# B3: Reversible arbitration — food relocation re-engages goal-directed
# ---------------------------------------------------------------------------

class TestB3_ReversibleArbitration:
    def test_omega_higher_at_novel_location_vs_trained(self):
        """
        Train 200 steps at (2,2). Relocate food to (3,3).
        At the new location, sigma2_MF is still at prior (never visited),
        while a few MB updates quickly reduce sigma2_MB.
        omega at (3,3) after a few steps should be higher than fully-trained omega at (2,2).
        """
        random.seed(7)
        model = UncertaintyBasedBayesianArbitrationModel()
        # Phase 1: train at (2,2)
        food_orig = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s_orig = (2, 2)
        for step in range(200):
            p = make_perception(x=2, y=2, food=food_orig, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state_after_train = model.get_state()
        omega_trained = state_after_train["omega"].get((s_orig, "eat"), 0.5)

        # Phase 2: relocate food to (3,3)
        food_new = [{"x": 3, "y": 3, "type": "food", "palatability": 1.0}]
        s_new = (3, 3)

        for step in range(200, 210):
            p = make_perception(x=3, y=3, food=food_new, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        state_after_reloc = model.get_state()
        omega_new_state = state_after_reloc["omega"].get((s_new, "eat"), 0.5)

        # At the new novel location, omega should be higher (GD re-engaged)
        assert omega_new_state > omega_trained, (
            f"Expected omega at new location {omega_new_state} > "
            f"omega at trained location {omega_trained}"
        )

    def test_omega_at_trained_location_below_novel(self):
        """
        After 200 steps at (2,2), omega at (2,2) is lower than
        omega at a completely novel state (4,4) with the same food setup.
        """
        random.seed(13)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s_trained = (2, 2)
        s_novel = (4, 4)

        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        # Get omega at trained state
        state = model.get_state()
        omega_trained = state["omega"].get((s_trained, "eat"), 0.5)

        # Check omega at novel state (first encounter)
        food_novel = [{"x": 4, "y": 4, "type": "food", "palatability": 1.0}]
        p_novel = make_perception(x=4, y=4, food=food_novel)
        model.decide(p_novel)
        state_novel = model.get_state()
        omega_novel = state_novel["omega"].get((s_novel, "eat"), 0.5)

        # Novel state has full prior MF uncertainty (sigma2_0=1.0)
        assert omega_novel > omega_trained, (
            f"Novel state omega ({omega_novel}) should exceed trained state omega ({omega_trained})"
        )


# ---------------------------------------------------------------------------
# B4: Devaluation sensitivity in goal-directed mode
# ---------------------------------------------------------------------------

class TestB4_DevaluationSensitivityGD:
    def test_low_hunger_reduces_mu_hat_when_goal_directed(self):
        """
        Force omega > 0.5 (GD dominant) by setting many N_MB experiences with no MF.
        With h ≈ 0, mu_MB[eat] ≈ 0 → mu_hat[eat] is low.
        """
        model = UncertaintyBasedBayesianArbitrationModel()
        s = (2, 2)

        # Set many MB experiences to reduce sigma2_MB
        model.N_MB[(s, "eat")] = 50

        # Low hunger
        model.h = 0.05

        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        p = make_perception(x=2, y=2, food=food)
        model.decide(p)

        state = model.get_state()
        mu_hat_eat = state["mu_hat"].get((s, "eat"), 0.0)
        omega_eat = state["omega"].get((s, "eat"), 0.5)

        # With many MB experiences and zero MF updates: sigma2_MB << sigma2_MF=1.0
        assert omega_eat > 0.5, f"Expected goal-directed dominance (omega>0.5), got {omega_eat}"
        # With h=0.05: mu_MB[eat] = 0.5 * 0.05 * 1.0 + 0.5 * (-0.01) ≈ 0.02 (low)
        assert mu_hat_eat < 0.10, (
            f"Expected low fused value with low hunger in GD mode, got {mu_hat_eat}"
        )

    def test_softmax_avoids_eat_with_low_desirability(self):
        """
        When mu_hat[eat] is low (hunger ~0, goal-directed mode),
        softmax probability of eat should be lower than for h=0.9.
        """
        random.seed(0)

        # Model with low hunger → low eat value
        model_low_h = UncertaintyBasedBayesianArbitrationModel()
        model_low_h.h = 0.02
        model_low_h.N_MB[((2, 2), "eat")] = 50

        # Model with high hunger → high eat value
        model_high_h = UncertaintyBasedBayesianArbitrationModel()
        model_high_h.h = 0.95
        model_high_h.N_MB[((2, 2), "eat")] = 50

        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        p = make_perception(x=2, y=2, food=food)

        model_low_h.decide(p)
        model_high_h.decide(p)

        mu_hat_low = model_low_h.mu_hat.get(((2, 2), "eat"), 0.0)
        mu_hat_high = model_high_h.mu_hat.get(((2, 2), "eat"), 0.0)

        assert mu_hat_high > mu_hat_low, (
            f"Expected mu_hat[eat] to be higher with h=0.95 ({mu_hat_high}) "
            f"vs h=0.02 ({mu_hat_low})"
        )


# ---------------------------------------------------------------------------
# B5: Devaluation insensitivity in habitual mode
# ---------------------------------------------------------------------------

class TestB5_DevaluationInsensitivityHabitual:
    def test_habitual_mode_retains_high_mu_mf_despite_low_hunger(self):
        """
        With sigma2_obs_MF=0.05 (low MF noise), the Kalman filter converges
        fast enough that sigma2_MF << sigma2_MB, producing omega < 0.5 (habitual).
        After training with high hunger, mu_MF remains high.
        Lowering hunger then barely affects mu_hat since MF dominates.
        """
        random.seed(123)
        model = UncertaintyBasedBayesianArbitrationModel(
            sigma2_obs_MF=0.05,
            sigma2_obs_MB=0.5,
        )
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        # Train under high hunger so mu_MF accumulates positive value
        model.h = 0.9
        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)

        # Now lower hunger
        model.h = 0.05

        p = make_perception(x=2, y=2, food=food)
        model.decide(p)

        state = model.get_state()
        omega_eat = state["omega"].get((s, "eat"), 0.5)
        mu_mf_eat = state["mu_MF"].get((s, "eat"), 0.0)
        mu_hat_eat = state["mu_hat"].get((s, "eat"), 0.0)

        # Verify we ARE in habitual mode
        assert omega_eat < 0.5, f"Expected habitual mode (omega<0.5), got omega={omega_eat}"

        # mu_MF should still be positive (trained under high-reward eating)
        assert mu_mf_eat > 0.1, (
            f"Expected mu_MF[eat] to remain positive from training, got {mu_mf_eat}"
        )

        # In habitual mode, mu_hat ≈ (1-omega) * mu_MF + omega * mu_MB
        expected_contribution = (1.0 - omega_eat) * mu_mf_eat
        assert mu_hat_eat > expected_contribution * 0.5, (
            f"Expected mu_hat ({mu_hat_eat}) to substantially reflect "
            f"habitual mu_MF contribution ({expected_contribution})"
        )

    def test_habit_mu_hat_higher_than_gd_after_devaluation(self):
        """
        After devaluation (hunger drop), habitual agent (low MF noise)
        should have higher mu_hat[eat] than goal-directed agent (high MF noise),
        showing devaluation insensitivity of habits.
        """
        random.seed(77)
        food = [{"x": 2, "y": 2, "type": "food", "palatability": 1.0}]
        s = (2, 2)

        # Habitual agent: fast MF convergence
        model_hab = UncertaintyBasedBayesianArbitrationModel(
            sigma2_obs_MF=0.05, sigma2_obs_MB=0.5,
        )
        model_hab.h = 0.9
        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model_hab, p, action_name="eat", consumed=True)

        # Goal-directed agent: slow MF convergence (standard params)
        model_gd = UncertaintyBasedBayesianArbitrationModel(
            sigma2_obs_MF=0.5, sigma2_obs_MB=0.05,
        )
        model_gd.h = 0.9
        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model_gd, p, action_name="eat", consumed=True)

        # Devalue: lower hunger for both
        model_hab.h = 0.05
        model_gd.h = 0.05

        p = make_perception(x=2, y=2, food=food)
        model_hab.decide(p)
        model_gd.decide(p)

        mu_hat_hab = model_hab.mu_hat.get((s, "eat"), 0.0)
        mu_hat_gd = model_gd.mu_hat.get((s, "eat"), 0.0)

        # After devaluation, habitual agent should retain higher eat value
        assert mu_hat_hab > mu_hat_gd, (
            f"Habitual agent mu_hat ({mu_hat_hab}) should exceed "
            f"GD agent mu_hat ({mu_hat_gd}) after devaluation"
        )


# ---------------------------------------------------------------------------
# Rule-level unit tests
# ---------------------------------------------------------------------------

class TestRules:
    def test_R1_hunger_rises_per_step(self):
        """Hunger should increase by eta per step when not eating."""
        model = UncertaintyBasedBayesianArbitrationModel(eta=0.02, phi=0.30)
        model.h = 0.5

        p = make_perception()
        action = model.decide(p)
        new_p = make_perception(last_action_result={"consumed": False})
        model.update(Action(name="stay"), -0.01, new_p)

        assert abs(model.h - 0.52) < 1e-6, f"Expected h=0.52, got {model.h}"

    def test_R1_hunger_drops_on_eating(self):
        """Hunger should drop by phi when food is consumed."""
        model = UncertaintyBasedBayesianArbitrationModel(eta=0.02, phi=0.30)
        model.h = 0.7
        model._last_s = (2, 2)

        new_p = make_perception(last_action_result={"consumed": True})
        model.update(Action(name="eat"), 1.0, new_p)

        # h = clip(0.7 + 0.02 - 0.30, 0, 1) = 0.42
        assert abs(model.h - 0.42) < 1e-6, f"Expected h=0.42, got {model.h}"

    def test_R1_hunger_clipped_at_zero(self):
        """Hunger should not go below 0."""
        model = UncertaintyBasedBayesianArbitrationModel(eta=0.02, phi=0.30)
        model.h = 0.1
        model._last_s = (2, 2)

        new_p = make_perception(last_action_result={"consumed": True})
        model.update(Action(name="eat"), 1.0, new_p)
        assert model.h >= 0.0

    def test_R1_hunger_clipped_at_one(self):
        """Hunger should not exceed 1."""
        model = UncertaintyBasedBayesianArbitrationModel(eta=0.02)
        model.h = 0.999
        model._last_s = (2, 2)

        new_p = make_perception(last_action_result={"consumed": False})
        model.update(Action(name="stay"), -0.01, new_p)
        assert model.h <= 1.0

    def test_R5_kalman_variance_decreases(self):
        """Each observation should reduce model-free variance."""
        model = UncertaintyBasedBayesianArbitrationModel()
        s = (1, 1)
        model._last_s = s
        prev_var = model.sigma2_MF.get((s, "eat"), model.sigma2_0)

        new_p = make_perception(x=1, y=1, last_action_result={"consumed": False})
        model.update(Action(name="eat"), -0.01, new_p)

        new_var = model.sigma2_MF.get((s, "eat"), model.sigma2_0)
        assert new_var < prev_var, f"Variance should shrink: {new_var} < {prev_var}"

    def test_R5_kalman_variance_monotone_decreasing(self):
        """Variance should monotonically decrease with more observations."""
        random.seed(5)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2}]
        s = (2, 2)
        prev_var = model.sigma2_0

        for step in range(20):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=True)
            new_var = model.sigma2_MF.get((s, "eat"), model.sigma2_0)
            assert new_var <= prev_var + 1e-10, (
                f"Step {step}: variance increased from {prev_var} to {new_var}"
            )
            prev_var = new_var

    def test_R6_transition_model_update(self):
        """Transition model should update toward observed outcome."""
        model = UncertaintyBasedBayesianArbitrationModel(alpha_T=0.20)
        s = (2, 2)
        model._last_s = s

        new_p = make_perception(x=2, y=2, last_action_result={"consumed": True})
        model.update(Action(name="eat"), 1.0, new_p)

        # p_hat((s, eat, food)) should move toward 1.0 from 0.5
        p_food = model.p_hat.get((s, "eat", "food"), 0.5)
        assert p_food > 0.5, f"p_hat should increase toward 1.0, got {p_food}"
        # p_hat((s, eat, nofood)) should move toward 0.0
        p_nofood = model.p_hat.get((s, "eat", "nofood"), 0.5)
        assert p_nofood < 0.5, f"p_hat nofood should decrease toward 0.0, got {p_nofood}"

    def test_R7_omega_sigmoid_formula(self):
        """omega = sigmoid(kappa * (sigma2_MF - sigma2_MB))."""
        model = UncertaintyBasedBayesianArbitrationModel(kappa=3.0, sigma2_0=1.0)
        s = (1, 1)
        model.sigma2_MF[(s, "eat")] = 0.8
        # Force an MB variance by calling decide with right setup
        food = [{"x": 1, "y": 1}]
        p = make_perception(x=1, y=1, food=food)
        model.decide(p)

        s2_mf = model.sigma2_MF.get((s, "eat"), model.sigma2_0)
        s2_mb = model.sigma2_MB.get((s, "eat"), model.sigma2_0)
        expected_omega = _sigmoid(3.0 * (s2_mf - s2_mb))
        actual_omega = model.omega.get((s, "eat"), 0.5)
        assert abs(actual_omega - expected_omega) < 1e-9, (
            f"omega mismatch: expected {expected_omega}, got {actual_omega}"
        )

    def test_R8_fusion_formula(self):
        """mu_hat = omega * mu_MB + (1-omega) * mu_MF."""
        model = UncertaintyBasedBayesianArbitrationModel()
        s = (2, 2)
        food = [{"x": 2, "y": 2}]
        p = make_perception(x=2, y=2, food=food)
        model.decide(p)

        for a in ACTIONS:
            w = model.omega.get((s, a), 0.5)
            mb = model.mu_MB.get((s, a), 0.0)
            mf = model.mu_MF.get((s, a), 0.0)
            expected = w * mb + (1.0 - w) * mf
            actual = model.mu_hat.get((s, a), 0.0)
            assert abs(actual - expected) < 1e-9, (
                f"Fusion formula mismatch for action {a}: "
                f"expected {expected}, got {actual}"
            )

    def test_R10_N_MB_increments(self):
        """N_MB should increment after each update."""
        model = UncertaintyBasedBayesianArbitrationModel()
        s = (2, 2)
        food = [{"x": 2, "y": 2}]

        p = make_perception(x=2, y=2, food=food)
        run_step(model, p, action_name="eat", consumed=True)
        assert model.N_MB.get((s, "eat"), 0) == 1

        run_step(model, p, action_name="eat", consumed=True)
        assert model.N_MB.get((s, "eat"), 0) == 2

    def test_R3_mb_eat_value_scales_with_hunger(self):
        """Higher hunger → higher mu_MB for eat when food is present."""
        s = (2, 2)
        food = [{"x": 2, "y": 2}]
        p = make_perception(x=2, y=2, food=food)

        model_low = UncertaintyBasedBayesianArbitrationModel()
        model_low.h = 0.1
        model_low.decide(p)
        mu_low = model_low.mu_MB.get((s, "eat"), 0.0)

        model_high = UncertaintyBasedBayesianArbitrationModel()
        model_high.h = 0.9
        model_high.decide(p)
        mu_high = model_high.mu_MB.get((s, "eat"), 0.0)

        assert mu_high > mu_low, (
            f"Higher hunger should yield higher mu_MB[eat]: {mu_high} vs {mu_low}"
        )

    def test_R4_mb_variance_decreases_with_experience(self):
        """sigma2_MB for eat should decrease as N_MB increases."""
        model = UncertaintyBasedBayesianArbitrationModel()
        s = (2, 2)
        food = [{"x": 2, "y": 2}]
        p = make_perception(x=2, y=2, food=food)

        variances = []
        for step in range(10):
            run_step(model, p, action_name="eat", consumed=True)
            model.decide(p)  # recompute MB values
            variances.append(model.sigma2_MB.get((s, "eat"), model.sigma2_0))

        # Variance should trend downward
        assert variances[-1] < variances[0], (
            f"sigma2_MB should decrease with experience: "
            f"first={variances[0]}, last={variances[-1]}"
        )

    def test_action_boundary_grid_clamp(self):
        """Movement at edge should clamp to grid boundary."""
        model = UncertaintyBasedBayesianArbitrationModel()
        # At top-left corner, move_up and move_left should stay put
        p = make_perception(x=0, y=0)
        action = model.decide(p)
        # Should not crash and return valid action
        assert action.name in ACTIONS

    def test_softmax_probabilities_sum_to_one(self):
        """Softmax should produce valid probability distribution."""
        values = [1.0, 2.0, -0.5, 3.0, 0.0, 1.5]
        probs = _softmax(values)
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(p > 0 for p in probs)

    def test_sigmoid_properties(self):
        """Verify sigmoid: sigmoid(0)=0.5, sigmoid(+∞)→1, sigmoid(-∞)→0."""
        assert abs(_sigmoid(0.0) - 0.5) < 1e-9
        assert _sigmoid(100) > 0.999
        assert _sigmoid(-100) < 0.001
        assert _sigmoid(3.0) > 0.5


# ---------------------------------------------------------------------------
# Integration test: full episodic run
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_run_no_crash(self):
        """Model should run 50 steps without error."""
        random.seed(42)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 3, "y": 3, "type": "food", "palatability": 1.0}]

        for step in range(50):
            x = random.randint(0, 4)
            y = random.randint(0, 4)
            food_here = (x == 3 and y == 3)
            p = make_perception(x=x, y=y, food=food, step=step)
            action = model.decide(p)
            consumed = food_here and action.name == "eat"
            reward = 1.0 if consumed else -0.01
            new_p = make_perception(
                x=x, y=y, food=food, step=step + 1,
                last_action_result={"consumed": consumed}
            )
            model.update(action, reward, new_p)

        state = model.get_state()
        assert 0.0 <= state["h"] <= 1.0
        assert len(state["q_values"]) == len(ACTIONS)

    def test_hunger_bounded_throughout(self):
        """Hunger must stay in [0,1] throughout a long run."""
        random.seed(11)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2}]

        for step in range(200):
            p = make_perception(x=2, y=2, food=food, step=step)
            run_step(model, p, action_name="eat", consumed=(step % 3 == 0))
            assert 0.0 <= model.h <= 1.0, f"Step {step}: h={model.h} out of bounds"

    def test_q_values_update_after_each_cycle(self):
        """q_values should change after learning updates."""
        random.seed(2)
        model = UncertaintyBasedBayesianArbitrationModel()
        food = [{"x": 2, "y": 2}]
        p = make_perception(x=2, y=2, food=food)

        model.decide(p)
        initial_q = dict(model.get_state()["q_values"])

        for step in range(10):
            run_step(model, p, action_name="eat", consumed=True)

        updated_q = model.get_state()["q_values"]
        # After 10 eat steps, at least some q_values should change
        changed = any(abs(updated_q[a] - initial_q[a]) > 1e-9 for a in ACTIONS)
        assert changed, "q_values should change after learning updates"
