"""
Tests for FreeEnergyMinimizingHomeostaticAgentProbabilisticBayesianModel

Covers all expected_behaviors (B1–B6) plus contract checks.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from free_energy_minimizing_homeostatic_agent_probabilistic_bayesian_model import (  # noqa: E501
    FreeEnergyMinimizingHomeostaticAgentProbabilisticBayesianModel as Model,
    Action,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=0, y=0, grid_width=10, grid_height=10, step=0,
    food=None, last_action_result=None
):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

class TestContract:
    def test_decide_returns_action(self):
        model = Model()
        p = make_perception()
        a = model.decide(p)
        assert isinstance(a, Action)
        assert a.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_get_state_has_required_keys(self):
        model = Model()
        state = model.get_state()
        for key in [
            "true_hunger", "believed_hunger_mean", "believed_hunger_variance",
            "hunger_observation", "position", "ate_food_flag",
            "pragmatic_value", "epistemic_value", "expected_free_energy",
            "q_values",
        ]:
            assert key in state, f"Missing key: {key}"

    def test_q_values_covers_all_actions(self):
        model = Model()
        p = make_perception()
        model.update(Action("stay"), 0.0, p)
        q = model.get_state()["q_values"]
        for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]:
            assert a in q, f"q_values missing action: {a}"
        assert all(isinstance(v, float) for v in q.values())

    def test_decide_does_not_mutate_state(self):
        model = Model()
        model.h_t = 3.0
        model.mu_h = 3.0
        p = make_perception()
        pre = model.get_state()
        model.decide(p)
        post = model.get_state()
        assert pre["true_hunger"] == post["true_hunger"]
        assert pre["believed_hunger_mean"] == post["believed_hunger_mean"]
        assert pre["believed_hunger_variance"] == post["believed_hunger_variance"]

    def test_update_increases_hunger_when_not_eating(self):
        model = Model()
        model.h_t = 2.0
        p = make_perception()
        model.update(Action("stay"), 0.0, p)
        # lambda_drift = 0.1 should increase true hunger
        assert model.h_t >= 2.0 - 1e-6

    def test_eating_reduces_true_hunger(self):
        model = Model(K=3.0, lambda_drift=0.1)
        model.h_t = 5.0
        p = make_perception(food=[{"x": 0, "y": 0}])
        p["last_action_result"] = {"consumed": True}
        model.update(Action("eat"), 1.0, p)
        # h_t = clip(5.0 + 0.1 - 3.0, 0, 10) = 2.1
        assert abs(model.h_t - 2.1) < 1e-6

    def test_true_hunger_clipped_to_zero(self):
        model = Model(K=3.0, lambda_drift=0.1)
        model.h_t = 0.0
        p = make_perception(food=[{"x": 0, "y": 0}])
        p["last_action_result"] = {"consumed": True}
        model.update(Action("eat"), 1.0, p)
        assert model.h_t >= 0.0

    def test_true_hunger_clipped_to_max(self):
        model = Model(lambda_drift=0.1, h_max=10.0)
        model.h_t = 10.0
        p = make_perception()
        model.update(Action("stay"), 0.0, p)
        assert model.h_t <= 10.0


# ---------------------------------------------------------------------------
# B1: Explores uncertain areas when hunger is low (epistemic drive)
# ---------------------------------------------------------------------------

class TestB1EpistemicExploration:
    """When hunger ≈ 0, the agent should prefer moving to high-entropy cells."""

    def test_prefers_uncertain_cell_over_known_empty_when_sated(self):
        """
        Place agent at (5,5). Set R_beliefs[6][5]=0.5 (max entropy ≈ 0.693) for
        move_right, and R_beliefs[4][5]=0.001 (low entropy) for move_left.
        With h_t=0 (sated), the epistemic term should favour move_right.
        """
        random.seed(42)
        model = Model(
            grid_width=10, grid_height=10,
            w_e=1.0,    # amplify epistemic weight for clarity
            beta_G=20.0,  # high determinism
        )
        model.h_t = 0.0
        model.mu_h = 0.0
        model.sigma_h_sq = 0.1

        # High entropy cell to the right
        model.R_beliefs[6][5] = 0.5   # binary_entropy ≈ 0.693
        # Low entropy cells in all other directions
        model.R_beliefs[4][5] = 0.001  # binary_entropy ≈ 0.007
        model.R_beliefs[5][4] = 0.001
        model.R_beliefs[5][6] = 0.001

        p = make_perception(x=5, y=5, grid_width=10, grid_height=10)

        counts = {a: 0 for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]}
        for _ in range(200):
            a = model.decide(p)
            counts[a.name] += 1

        assert counts["move_right"] > counts["move_left"], (
            f"Expected move_right (high entropy) > move_left (low entropy), got {counts}"
        )

    def test_G_epist_higher_for_uncertain_destination(self):
        model = Model(grid_width=10, grid_height=10)
        model.R_beliefs[1][0] = 0.5   # max entropy for move_right from (0,0)
        model.R_beliefs[0][1] = 0.001  # near-zero entropy for move_down from (0,0)

        G_vals = model._compute_G_values(
            mu_h=0.0, sigma_h_sq=0.5,
            food_at_position=False,
            s_t=(0, 0), grid_w=10, grid_h=10,
        )
        # move_right visits (1,0) with high entropy; move_down visits (0,1) with low entropy
        assert G_vals["move_right"] > G_vals["move_down"]


# ---------------------------------------------------------------------------
# B2: Exploits known food when hungry (pragmatic drive)
# ---------------------------------------------------------------------------

class TestB2PragmaticExploitation:
    """When very hungry with known food at current cell, eat should dominate."""

    def test_eat_dominates_when_very_hungry_and_food_present(self):
        random.seed(7)
        model = Model(
            grid_width=10, grid_height=10,
            beta_G=10.0,
            w_e=0.0,  # disable epistemic for pure pragmatic test
        )
        model.h_t = 7.0
        model.mu_h = 7.0
        model.sigma_h_sq = 0.1

        p = make_perception(x=3, y=3, food=[{"x": 3, "y": 3}])

        counts = {"eat": 0, "other": 0}
        for _ in range(300):
            a = model.decide(p)
            if a.name == "eat":
                counts["eat"] += 1
            else:
                counts["other"] += 1

        assert counts["eat"] > counts["other"], (
            f"Expected eat to dominate; counts={counts}"
        )

    def test_G_eat_highest_when_hungry_food_present(self):
        model = Model(
            grid_width=10, grid_height=10,
            w_e=0.0,
        )
        model.mu_h = 7.0
        model.sigma_h_sq = 0.1

        G_vals = model._compute_G_values(
            mu_h=7.0, sigma_h_sq=0.1,
            food_at_position=True,
            s_t=(5, 5), grid_w=10, grid_h=10,
        )
        assert G_vals["eat"] == max(G_vals.values()), (
            f"eat should have max G when hungry. G_vals={G_vals}"
        )

    def test_eat_suppressed_when_no_food(self):
        model = Model(grid_width=10, grid_height=10)
        G_vals = model._compute_G_values(
            mu_h=7.0, sigma_h_sq=0.1,
            food_at_position=False,
            s_t=(5, 5), grid_w=10, grid_h=10,
        )
        assert G_vals["eat"] < -1e8, "eat should be suppressed when no food"


# ---------------------------------------------------------------------------
# B3: Bayesian belief tracks true hunger
# ---------------------------------------------------------------------------

class TestB3BayesianTracking:
    """After many steps, mu_h should stay close to h_t (within ~2*sigma_obs)."""

    def test_belief_tracks_true_hunger_over_100_steps(self):
        random.seed(0)
        model = Model(
            grid_width=10, grid_height=10,
            sigma_obs=0.5, lambda_drift=0.1, K=3.0, h_max=10.0,
        )
        model.h_t = 0.0
        model.mu_h = 0.0

        errors = []
        x, y = 3, 3
        for step in range(100):
            p = make_perception(x=x, y=y)
            action = model.decide(p)
            p2 = make_perception(x=x, y=y)
            model.update(action, 0.0, p2)
            errors.append(abs(model.mu_h - model.h_t))

        mean_error = sum(errors) / len(errors)
        # Belief should be calibrated: mean error < 2 * sigma_obs
        assert mean_error < 2 * model.sigma_obs, (
            f"Mean |mu_h - h_t| = {mean_error:.3f} >= 2*sigma_obs={2*model.sigma_obs}"
        )

    def test_bayesian_update_reduces_variance(self):
        """After an observation, variance should decrease relative to the prior prediction."""
        model = Model(sigma_obs=0.5, sigma_process_sq=0.01)
        model.mu_h = 2.0
        model.sigma_h_sq = 1.0

        p = make_perception()
        model.update(Action("stay"), 0.0, p)

        # After Kalman update, variance should be less than prior + process noise
        sigma_prior = 1.0 + 0.01  # sigma_h_sq + sigma_process_sq
        assert model.sigma_h_sq < sigma_prior


# ---------------------------------------------------------------------------
# B4: Eating near setpoint yields near-zero pragmatic benefit (alliesthesia)
# ---------------------------------------------------------------------------

class TestB4AlliesthesiaEffect:
    """Alliesthesia via free energy: perceived benefit of eating depends on internal state.

    Mathematical analysis of G(a) = G_prag(a) + w_e * G_epist(a):
      G_prag(eat)  = -((mu_h + λ - K - h*)² + σ²) / σ_p²
      G_prag(stay) = -((mu_h + λ     - h*)² + σ²) / σ_p²
      advantage(eat vs stay) = G(eat) - G(stay)
                              = K * (2(mu_h + λ) - K) / σ_p²   [monotone increasing in mu_h]

    G(eat) itself is maximised at mu_h = K - λ (eating restores hunger to exactly h*=0),
    and is more negative for any deviation from that optimum.
    """

    def test_pragmatic_difference_smaller_near_setpoint_than_when_hungry(self):
        """
        The key alliesthesia property: at mu_h ≈ h* (sated, mu_h=0.1), |G(eat)-G(stay)|
        is smaller than at high hunger (mu_h=8), since eating when sated overshoots setpoint.
        """
        model = Model(h_star=0.0, sigma_p=1.0, K=3.0, lambda_drift=0.1)

        G_near = model._compute_G_values(
            mu_h=0.1, sigma_h_sq=0.1,
            food_at_position=True,
            s_t=(0, 0), grid_w=10, grid_h=10,
        )
        delta_near = abs(G_near["eat"] - G_near["stay"])

        G_hungry = model._compute_G_values(
            mu_h=8.0, sigma_h_sq=0.1,
            food_at_position=True,
            s_t=(0, 0), grid_w=10, grid_h=10,
        )
        delta_hungry = abs(G_hungry["eat"] - G_hungry["stay"])

        assert delta_hungry > delta_near, (
            f"Hungry delta ({delta_hungry:.3f}) should exceed sated delta ({delta_near:.3f})"
        )

    def test_G_eat_unimodal_maximised_near_K_minus_lambda(self):
        """
        G(eat) = -((mu_h + λ - K)² + σ²) / σ_p²
        is maximised (least negative, closest to 0) when mu_h + λ - K = 0
        → mu_h_optimal = K - λ = 3.0 - 0.1 = 2.9
        Values at 0 and 8 should be lower than at 2.9.
        """
        model = Model(h_star=0.0, sigma_p=1.0, K=3.0, lambda_drift=0.1, w_e=0.0)
        sigma_h_sq = 0.1

        def g_eat(mu):
            return model._compute_G_values(
                mu_h=mu, sigma_h_sq=sigma_h_sq,
                food_at_position=True,
                s_t=(5, 5), grid_w=10, grid_h=10,
            )["eat"]

        g_optimal = g_eat(2.9)   # mu_after_eat = 0.0 → minimal drive
        g_sated   = g_eat(0.0)   # mu_after_eat = -2.9 → overshoot
        g_hungry  = g_eat(8.0)   # mu_after_eat =  5.1 → undershoot

        assert g_optimal > g_sated, (
            f"G(eat) at optimal ({g_optimal:.3f}) should exceed sated ({g_sated:.3f})"
        )
        assert g_optimal > g_hungry, (
            f"G(eat) at optimal ({g_optimal:.3f}) should exceed very hungry ({g_hungry:.3f})"
        )

    def test_eat_advantage_over_stay_increases_monotonically_with_hunger(self):
        """
        advantage(mu) = G(eat) - G(stay) = K*(2*(mu+λ)-K)/σ_p²
        This is a linear function of mu, strictly increasing.
        Verify at a few sample points.
        """
        model = Model(h_star=0.0, sigma_p=1.0, K=3.0, lambda_drift=0.1, w_e=0.0)

        def advantage(mu):
            G = model._compute_G_values(
                mu_h=mu, sigma_h_sq=0.1,
                food_at_position=True,
                s_t=(5, 5), grid_w=10, grid_h=10,
            )
            return G["eat"] - G["stay"]

        hungers = [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0]
        advantages = [advantage(h) for h in hungers]

        for i in range(len(advantages) - 1):
            assert advantages[i] < advantages[i + 1], (
                f"Advantage not monotone at hunger={hungers[i]}: "
                f"adv={advantages[i]:.3f} vs next={advantages[i+1]:.3f}"
            )


# ---------------------------------------------------------------------------
# B5: Resource belief decay and persistence
# ---------------------------------------------------------------------------

class TestB5ResourceBeliefUpdate:
    """Empty cells should decay; food cells should stay at 1.0."""

    def test_empty_cell_belief_decays_significantly(self):
        model = Model(grid_width=10, grid_height=10, kappa=0.05, initial_resource_prior=0.5)
        model.R_beliefs[2][3] = 0.5
        # Repeatedly observe cell (2,3) as empty for 100 steps
        for _ in range(100):
            p = make_perception(x=2, y=3, food=[])
            model.update(Action("stay"), 0.0, p)

        # After 100 updates: 0.5 * (1-0.05)^100 ≈ 0.5 * 0.00592 ≈ 0.003
        assert model.R_beliefs[2][3] < 0.05, (
            f"Belief should decay significantly; got {model.R_beliefs[2][3]:.4f}"
        )

    def test_food_cell_belief_set_to_one(self):
        model = Model(grid_width=10, grid_height=10, initial_resource_prior=0.05)
        model.R_beliefs[4][7] = 0.1
        p = make_perception(x=4, y=7, food=[{"x": 4, "y": 7}])
        model.update(Action("stay"), 0.0, p)
        assert model.R_beliefs[4][7] == 1.0

    def test_other_cells_unchanged_after_update(self):
        model = Model(grid_width=10, grid_height=10, initial_resource_prior=0.05)
        prior = model.R_beliefs[7][2]
        p = make_perception(x=0, y=0, food=[])
        model.update(Action("stay"), 0.0, p)
        assert model.R_beliefs[7][2] == prior, "Unvisited cell should not change"


# ---------------------------------------------------------------------------
# B6: Smooth transition from exploration to exploitation as hunger rises
# ---------------------------------------------------------------------------

class TestB6ExplorationExploitationTransition:
    """As hunger increases, P(eat) should rise relative to P(explore)."""

    def test_crossover_exists_in_hunger_sweep(self):
        """
        At low hunger: G(move_to_uncertain_cell) > G(eat)
        At high hunger: G(eat) > G(move_to_uncertain_cell)
        → A crossover should occur.
        """
        model = Model(
            grid_width=10, grid_height=10,
            w_e=0.3, K=3.0, h_star=0.0, sigma_p=1.0,
        )
        # Set destination of move_right to high-entropy cell
        model.R_beliefs[6][5] = 0.5   # max entropy ≈ 0.693

        eat_wins_at_high_hunger = False
        explore_wins_at_low_hunger = False

        for hunger in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]:
            G_vals = model._compute_G_values(
                mu_h=hunger,
                sigma_h_sq=0.1,
                food_at_position=True,  # food always at position
                s_t=(5, 5),
                grid_w=10,
                grid_h=10,
            )
            g_eat = G_vals["eat"]
            g_right = G_vals["move_right"]

            if hunger <= 1.0 and g_right > g_eat:
                explore_wins_at_low_hunger = True
            if hunger >= 6.0 and g_eat > g_right:
                eat_wins_at_high_hunger = True

        assert explore_wins_at_low_hunger, "Exploration should dominate at low hunger"
        assert eat_wins_at_high_hunger, "Exploitation should dominate at high hunger"

    def test_p_eat_increases_with_hunger(self):
        """P(eat) from softmax should increase as mu_h increases."""
        model = Model(
            grid_width=10, grid_height=10,
            w_e=0.0,   # pure pragmatic
            beta_G=5.0,
        )
        prev_p_eat = None
        for hunger in [0.5, 2.0, 4.0, 6.0, 8.0]:
            G_vals = model._compute_G_values(
                mu_h=hunger,
                sigma_h_sq=0.1,
                food_at_position=True,
                s_t=(5, 5),
                grid_w=10,
                grid_h=10,
            )
            g_list = list(G_vals.values())
            actions = list(G_vals.keys())
            max_g = max(g_list)
            exp_vals = [math.exp(model.beta_G * (g - max_g)) for g in g_list]
            total = sum(exp_vals)
            idx_eat = actions.index("eat")
            p_eat = exp_vals[idx_eat] / total

            if prev_p_eat is not None:
                assert p_eat >= prev_p_eat - 1e-6, (
                    f"P(eat) should increase with hunger; hunger={hunger}, "
                    f"p_eat={p_eat:.4f} < prev={prev_p_eat:.4f}"
                )
            prev_p_eat = p_eat


# ---------------------------------------------------------------------------
# Additional: Belief variance stays above floor
# ---------------------------------------------------------------------------

class TestBeliefVarianceFloor:
    def test_variance_never_drops_below_floor(self):
        random.seed(1)
        model = Model(sigma_obs=0.01, sigma_process_sq=0.001)
        for _ in range(200):
            p = make_perception()
            a = model.decide(p)
            model.update(a, 0.0, p)
            assert model.sigma_h_sq >= 0.001, (
                f"sigma_h_sq dropped below floor: {model.sigma_h_sq}"
            )


# ---------------------------------------------------------------------------
# Additional: Grid boundary clamping
# ---------------------------------------------------------------------------

class TestGridBoundary:
    def test_agent_at_corner_can_still_act(self):
        model = Model(grid_width=5, grid_height=5)
        p = make_perception(x=0, y=0, grid_width=5, grid_height=5)
        a = model.decide(p)
        assert a.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_movement_clamped_at_boundary_is_finite(self):
        """G values for all actions at corner should be finite."""
        model = Model(grid_width=5, grid_height=5)
        G_vals = model._compute_G_values(
            mu_h=0.0, sigma_h_sq=0.5,
            food_at_position=False,
            s_t=(0, 0), grid_w=5, grid_h=5,
        )
        for a_name, g_val in G_vals.items():
            assert math.isfinite(g_val), f"{a_name} G-value is not finite: {g_val}"
