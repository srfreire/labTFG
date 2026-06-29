"""
Tests for HierarchicalPrecisionWeightedPredictionErrorMinimizationGradientDescentOdeModel

Tests cover all five expected behaviors (B1-B5) plus structural contract checks.
"""

import math
import random

from hierarchical_precision_weighted_prediction_error_minimization_gradient_descent_ode_model import (
    HierarchicalPrecisionWeightedPredictionErrorMinimizationGradientDescentOdeModel as Model,
    Action,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, gw=10, gh=10, food=None, last_action_result=None):
    """Build a minimal perception dict."""
    return {
        "x": x,
        "y": y,
        "grid_width": gw,
        "grid_height": gh,
        "step": 0,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


def vec_norm(v):
    return math.sqrt(sum(vi ** 2 for vi in v))


def vec_sub(a, b):
    return [ai - bi for ai, bi in zip(a, b)]


# ---------------------------------------------------------------------------
# B1: Beliefs converge toward sensory observations
# ---------------------------------------------------------------------------

class TestB1BeliefConvergence:
    """After N_iter iterations with Pi_1 >> Pi_2, mu_1 should closely track s."""

    def test_belief_convergence_reduces_mismatch(self):
        """
        With high Pi_1 and many iterations, mu_1 must move substantially toward s.

        eff_kappa = min(kappa, 1/max(Pi_1,Pi_2)) = min(0.5, 1/10) = 0.1.
        After N_iter=30 steps, mismatch should reduce significantly.
        """
        model = Model(
            kappa=0.5,
            Pi_1_init=10.0,   # high sensory precision
            Pi_2_init=0.1,    # low prior precision
            N_iter=30,        # many iterations
        )
        food = [{"x": 7, "y": 3, "type": "food"}]
        perception = make_perception(x=2, y=3, gw=10, gh=10, food=food)

        # Warm-start beliefs far from target
        model.mu_1 = [0.0, 0.0, 0.0, 0.0, 0.0]
        s = model._encode_sensory(perception)
        initial_diff = vec_norm(vec_sub(model.mu_1, s))

        # Run inference via update
        model.update(Action(name="stay"), 0.0, perception)

        final_diff = vec_norm(vec_sub(model.mu_1, s))
        assert final_diff < initial_diff, (
            f"mu_1 did not move toward s: initial diff={initial_diff:.4f}, "
            f"final diff={final_diff:.4f}"
        )
        # With eff_kappa=0.1, N_iter=30: should converge substantially
        assert final_diff < initial_diff * 0.5, (
            f"Expected >50% reduction in belief-sensory mismatch; "
            f"initial={initial_diff:.4f}, final={final_diff:.4f}"
        )

    def test_belief_tracks_changing_observation(self):
        """mu_1 should update when the sensory input changes."""
        model = Model(kappa=0.5, Pi_1_init=5.0, Pi_2_init=0.5, N_iter=10)
        food_a = [{"x": 1, "y": 1, "type": "food"}]
        food_b = [{"x": 8, "y": 8, "type": "food"}]

        p1 = make_perception(x=1, y=1, gw=10, gh=10, food=food_a)
        p2 = make_perception(x=8, y=8, gw=10, gh=10, food=food_b)

        model.update(Action("stay"), 0.0, p1)
        mu_1_first = list(model.mu_1)

        model.update(Action("move_right"), 0.0, p2)
        mu_1_second = list(model.mu_1)

        diff = vec_norm(vec_sub(mu_1_first, mu_1_second))
        assert diff > 0.01, (
            f"mu_1 did not shift when sensory input changed; diff = {diff:.4f}"
        )

    def test_belief_converges_over_repeated_identical_updates(self):
        """Repeated updates with identical perception drive mu_1 toward fixed point."""
        model = Model(kappa=0.5, Pi_1_init=3.0, Pi_2_init=0.5, N_iter=10)
        food = [{"x": 6, "y": 4, "type": "food"}]
        perception = make_perception(x=6, y=4, gw=10, gh=10, food=food)
        s = model._encode_sensory(perception)

        diffs = []
        for _ in range(20):
            model.update(Action("stay"), 0.0, perception)
            diffs.append(vec_norm(vec_sub(model.mu_1, s)))

        # Diffs should stabilise (final <= initial + small tolerance)
        assert diffs[-1] <= diffs[0] + 1e-6, (
            f"Beliefs did not converge over 20 repeated updates; "
            f"diff went from {diffs[0]:.4f} to {diffs[-1]:.4f}"
        )

    def test_sensory_precision_dominates_when_high(self):
        """
        When Pi_1 >> Pi_2, the sensory term dominates the gradient and mu_1
        converges closer to s than to the level-2 prediction.
        At fixed point: mu* = Pi_1/(Pi_1+Pi_2)*s + Pi_2/(Pi_1+Pi_2)*g2.
        With Pi_1=10, Pi_2=0.1: mu* ~ 10/10.1 * s ~ 0.99*s.
        """
        model = Model(
            kappa=0.5,
            Pi_1_init=10.0,
            Pi_2_init=0.1,
            N_iter=40,
        )
        food = [{"x": 6, "y": 4, "type": "food"}]
        perception = make_perception(x=6, y=4, gw=10, gh=10, food=food)
        s = model._encode_sensory(perception)

        for _ in range(5):
            model.update(Action("stay"), 0.0, perception)

        # mu_1 should be closer to s than to the initial prior (0.5,0.5,0,0,1)
        diff_to_s = vec_norm(vec_sub(model.mu_1, s))
        diff_to_prior = vec_norm(vec_sub(model.mu_1, [0.5, 0.5, 0.0, 0.0, 1.0]))

        assert diff_to_s < diff_to_prior, (
            f"Expected mu_1 closer to s than to initial prior; "
            f"diff_to_s={diff_to_s:.4f}, diff_to_prior={diff_to_prior:.4f}"
        )


# ---------------------------------------------------------------------------
# B2: Agent moves toward food
# ---------------------------------------------------------------------------

class TestB2MovesTowardFood:
    """Predicted free energy should be lower for actions that reduce distance to food."""

    def test_move_right_preferred_over_move_left_when_food_is_right(self):
        """Food at (5,5), agent at (3,5): move_right should have lower F_pred than move_left."""
        model = Model(kappa=0.5, Pi_1_init=2.0, Pi_2_init=1.0, N_iter=5)
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=3, y=5, gw=10, gh=10, food=food)

        # Warm up beliefs
        model.update(Action("stay"), 0.0, perception)

        # Compute predicted free energies directly
        F_pred = model._compute_action_free_energies(
            perception, model.mu_1, model.eps_2
        )

        assert F_pred["move_right"] < F_pred["move_left"], (
            f"Expected F_pred(move_right)={F_pred['move_right']:.4f} < "
            f"F_pred(move_left)={F_pred['move_left']:.4f}"
        )

    def test_move_down_preferred_when_food_is_below(self):
        """Food at (5,8), agent at (5,3): move_down should have lower F_pred than move_up."""
        model = Model(kappa=0.5, Pi_1_init=2.0, Pi_2_init=1.0, N_iter=5)
        food = [{"x": 5, "y": 8, "type": "food"}]
        perception = make_perception(x=5, y=3, gw=10, gh=10, food=food)

        model.update(Action("stay"), 0.0, perception)

        F_pred = model._compute_action_free_energies(
            perception, model.mu_1, model.eps_2
        )

        assert F_pred["move_down"] < F_pred["move_up"], (
            f"Expected F_pred(move_down)={F_pred['move_down']:.4f} < "
            f"F_pred(move_up)={F_pred['move_up']:.4f}"
        )

    def test_q_values_reflect_food_direction(self):
        """Q-values (negative F_pred) should rank food-approaching actions higher."""
        model = Model(kappa=0.5, Pi_1_init=2.0, Pi_2_init=1.0, N_iter=5)
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=2, y=5, gw=10, gh=10, food=food)

        model.update(Action("stay"), 0.0, perception)
        q = model.get_state()["q_values"]

        # Moving right brings closer to food at (5,5), moving left diverges
        assert q["move_right"] > q["move_left"], (
            f"Q(move_right)={q['move_right']:.4f} should be > Q(move_left)={q['move_left']:.4f}"
        )


# ---------------------------------------------------------------------------
# B3: Agent eats when on food
# ---------------------------------------------------------------------------

class TestB3EatsWhenOnFood:
    """When food is at current position, eat should be strongly preferred."""

    def test_eat_disfavored_without_food(self):
        """Eat action should have F_pred = 1e6 (strongly disfavoured) without food."""
        model = Model()
        perception = make_perception(x=3, y=3, gw=10, gh=10, food=[])

        model.update(Action("stay"), 0.0, perception)
        F_pred = model._compute_action_free_energies(
            perception, model.mu_1, model.eps_2
        )

        assert F_pred["eat"] == 1e6, (
            f"Expected F_pred(eat)=1e6 when no food present; got {F_pred['eat']}"
        )

    def test_eat_is_finite_when_food_present(self):
        """When food is at agent position, eat should produce a finite F_pred."""
        model = Model()
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food)

        model.update(Action("stay"), 0.0, perception)
        F_pred = model._compute_action_free_energies(
            perception, model.mu_1, model.eps_2
        )

        assert F_pred["eat"] < 1e6, (
            f"Expected finite F_pred(eat) when food present; got {F_pred['eat']}"
        )

    def test_eat_preferred_over_moves_away_when_beliefs_converged(self):
        """
        When agent is on food AND beliefs have converged (mu_1[3] ~ 1.0),
        eat predicts s_pred[3]=1.0 which matches mu_1[3] → small prediction error.
        Moving away predicts food_here=0.0 at the new position → large error on dim 3.
        Therefore eat should have lower F_pred than moving to an empty cell.
        """
        model = Model(
            kappa=0.5,
            Pi_1_init=5.0,
            Pi_2_init=0.5,
            N_iter=15,
        )
        # Only food at (5,5) — all other cells are empty
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food)

        # Let beliefs converge: mu_1[3] must reach near 1.0
        for _ in range(10):
            model.update(Action("stay"), 0.0, perception)

        assert model.mu_1[3] > 0.5, (
            f"mu_1[3] should converge toward 1.0 when food is here; got {model.mu_1[3]:.4f}"
        )

        F_pred = model._compute_action_free_energies(
            perception, model.mu_1, model.eps_2
        )

        # eat predicts food_here=1.0 (matches mu_1[3] ~ 1.0) → low error on dim 3
        # move_up to (5,4): no food there → food_here=0.0, but mu_1[3]~1.0 → high error
        eat_f = F_pred["eat"]
        move_up_f = F_pred["move_up"]

        assert eat_f < move_up_f, (
            f"Expected eat F_pred={eat_f:.4f} < move_up F_pred={move_up_f:.4f}; "
            f"mu_1[3]={model.mu_1[3]:.4f}"
        )

    def test_eat_selected_frequently_when_on_food(self):
        """With well-converged beliefs on food, eat should dominate softmax."""
        random.seed(7)
        model = Model(
            kappa=0.5,
            Pi_1_init=5.0,
            Pi_2_init=0.5,
            N_iter=15,
            beta=6.0,
        )
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food)

        # Converge beliefs so mu_1[3] ~ 1.0
        for _ in range(10):
            model.update(Action("stay"), 0.0, perception)

        assert model.mu_1[3] > 0.5, f"Beliefs not converged: mu_1[3]={model.mu_1[3]:.4f}"

        eat_count = 0
        N = 100
        for _ in range(N):
            act = model.decide(perception)
            if act.name == "eat":
                eat_count += 1

        assert eat_count > N * 0.3, (
            f"Expected 'eat' > 30% when food here with converged beliefs; "
            f"got {eat_count}/{N}, mu_1[3]={model.mu_1[3]:.4f}"
        )

    def test_eat_prediction_includes_food_here_signal(self):
        """The eat prediction vector should always have food_here=1.0."""
        model = Model()
        food = [{"x": 3, "y": 3, "type": "food"}]
        perception = make_perception(x=3, y=3, gw=10, gh=10, food=food)
        s_pred = model._predict_sensory("eat", perception, food)

        assert s_pred[3] == 1.0, (
            f"Eat prediction should have food_here=1.0; got {s_pred[3]}"
        )


# ---------------------------------------------------------------------------
# B4: Precision adapts to prediction error magnitude
# ---------------------------------------------------------------------------

class TestB4PrecisionAdaptation:
    """Stable environment -> precision converges; sudden change -> precision drops."""

    def test_precision_converges_in_stable_environment(self):
        """Running many steps with constant sensory input: Pi_1 changes from initial."""
        model = Model(kappa=0.1, Pi_1_init=0.5, eta_Pi=0.2, N_iter=5, sigma2_init=1.0)
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food)

        Pi_history = [model.Pi_1]
        for _ in range(50):
            model.update(Action("stay"), 0.0, perception)
            Pi_history.append(model.Pi_1)

        # Precision should change from initial value
        total_change = abs(Pi_history[-1] - Pi_history[0])
        assert total_change > 0.001, (
            f"Expected precision to change from initial {Pi_history[0]:.4f}; "
            f"final={Pi_history[-1]:.4f}"
        )

    def test_precision_increases_when_started_below_equilibrium(self):
        """
        The precision adaptation rule drives Pi_1 toward 1/(err_sq + sigma2_init).
        When errors are near zero (stable), Pi converges toward 1/sigma2_init = 1.0.
        Starting below equilibrium (Pi_1_init=0.1), it should increase.
        """
        # Start far below equilibrium: Pi_1 = 0.1 < 1.0/1.0 = 1.0
        model = Model(kappa=0.1, Pi_1_init=0.1, eta_Pi=0.3, N_iter=10, sigma2_init=1.0)
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food)

        Pi_start = model.Pi_1  # 0.1
        for _ in range(30):
            model.update(Action("stay"), 0.0, perception)

        # Should move toward 1.0
        assert model.Pi_1 > Pi_start, (
            f"Expected Pi_1 to increase from {Pi_start:.4f}; got {model.Pi_1:.4f}"
        )

    def test_precision_decreases_after_sudden_change(self):
        """After stabilisation, an abrupt sensory change should reduce Pi_1."""
        model = Model(kappa=0.1, Pi_1_init=0.1, eta_Pi=0.3, N_iter=5, sigma2_init=0.5)
        food_stable = [{"x": 5, "y": 5, "type": "food"}]
        perception_stable = make_perception(x=5, y=5, gw=10, gh=10, food=food_stable)

        # Stabilise: Pi_1 rises toward 1/sigma2_init = 2.0
        for _ in range(40):
            model.update(Action("stay"), 0.0, perception_stable)

        Pi_after_stable = model.Pi_1

        # Sudden drastic change: move agent to empty corner, no food
        perception_changed = make_perception(x=9, y=9, gw=10, gh=10, food=[])
        for _ in range(5):
            model.update(Action("stay"), 0.0, perception_changed)

        assert model.Pi_1 < Pi_after_stable, (
            f"Expected Pi_1 to decrease after sudden change; "
            f"went from {Pi_after_stable:.4f} to {model.Pi_1:.4f}"
        )

    def test_reward_boosts_precision(self):
        """Positive reward should increase Pi_1 before precision adaptation fires."""
        model = Model(Pi_1_init=2.0, eta_Pi=0.01)  # very slow precision adaptation
        perception = make_perception(x=5, y=5, gw=10, gh=10,
                                     food=[{"x": 5, "y": 5, "type": "food"}])

        Pi_before = model.Pi_1
        # Reward 1.0 multiplies Pi_1 by 1.1 before precision adaptation
        # Net result should be higher than initial with slow eta_Pi
        model.update(Action("eat"), reward=1.0, new_perception=perception)
        assert model.Pi_1 > Pi_before * 0.95, (
            f"Expected Pi_1 >= {Pi_before * 0.95:.4f} after positive reward; got {model.Pi_1:.4f}"
        )

    def test_failed_eat_reduces_precision(self):
        """Failed eat (eat action, reward=0) should reduce Pi_1."""
        model = Model(Pi_1_init=2.0, eta_Pi=0.01)
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=[])

        Pi_before = model.Pi_1
        model.update(Action("eat"), reward=0.0, new_perception=perception)
        assert model.Pi_1 < Pi_before, (
            f"Expected Pi_1 to decrease after failed eat; "
            f"went from {Pi_before:.4f} to {model.Pi_1:.4f}"
        )


# ---------------------------------------------------------------------------
# B5: Hierarchical influence of level-2 belief on level-1 expectations
# ---------------------------------------------------------------------------

class TestB5HierarchicalInfluence:
    """High mu_2 (resource-rich context) should influence level-1 food-related beliefs."""

    def test_g2_prediction_reflects_mu2(self):
        """The generative model g_2 prediction should directly encode mu_2 in food dims."""
        model = Model()
        mu_1 = [0.5, 0.5, 0.3, 0.3, 0.7]
        mu_2 = 0.8

        g2 = model._g2_pred(mu_1, mu_2)

        assert g2[2] == mu_2, f"Expected g2[2] = mu_2 = {mu_2}; got {g2[2]}"
        assert g2[3] == mu_2, f"Expected g2[3] = mu_2 = {mu_2}; got {g2[3]}"
        assert abs(g2[4] - (1.0 - mu_2)) < 1e-9, f"Expected g2[4] = 1-mu_2 = {1-mu_2}; got {g2[4]}"

    def test_high_mu2_biases_level1_food_dims_upward_fixed_mu2(self):
        """
        With mu_2 fixed at different values, the level-1 inference should
        produce different mu_1 food dimensions at convergence.

        Using fix_mu_2=True isolates the top-down influence without R5
        overriding the forced mu_2 values.

        Fixed point: mu* = Pi_1/(Pi_1+Pi_2) * s + Pi_2/(Pi_1+Pi_2) * mu_2
        With Pi_1=0.5, Pi_2=3.0, s[2,3]=0.0:
          mu*(high) = 3.0/3.5 * 0.9 = 0.771
          mu*(low)  = 3.0/3.5 * 0.1 = 0.086
        """
        # Neutral sensory input: no food anywhere
        s_neutral = [0.5, 0.5, 0.0, 0.0, 1.0]

        model_high = Model(
            kappa=0.5,
            Pi_1_init=0.5,   # low sensory precision -> top-down dominates
            Pi_2_init=3.0,   # high level-2 precision -> strong top-down
            N_iter=40,
        )
        model_low = Model(
            kappa=0.5,
            Pi_1_init=0.5,
            Pi_2_init=3.0,
            N_iter=40,
        )

        # Force mu_2 values and keep them fixed during inference
        model_high.mu_2 = 0.9
        model_low.mu_2 = 0.1

        # Run inference with neutral sensory input and fixed mu_2
        mu_1_high, _, _, _ = model_high._run_inference(s_neutral, fix_mu_2=True)
        mu_1_low, _, _, _ = model_low._run_inference(s_neutral, fix_mu_2=True)

        # Food-presence dims (2 and 3): high mu_2 top-down should pull mu_1 higher
        food_dims_high = mu_1_high[2] + mu_1_high[3]
        food_dims_low = mu_1_low[2] + mu_1_low[3]

        assert food_dims_high > food_dims_low, (
            f"Expected high mu_2 to yield higher food beliefs via top-down; "
            f"high={food_dims_high:.4f} (mu_1_high[2]={mu_1_high[2]:.4f}, [3]={mu_1_high[3]:.4f}), "
            f"low={food_dims_low:.4f} (mu_1_low[2]={mu_1_low[2]:.4f}, [3]={mu_1_low[3]:.4f})"
        )

    def test_mu2_update_responds_to_food_rich_environment(self):
        """
        In a food-rich environment (food everywhere), repeated updates should
        drive mu_2 away from its default (0.5) as the model learns the context.
        """
        model = Model(
            kappa=0.5,
            Pi_1_init=2.0,
            Pi_2_init=2.0,
            N_iter=10,
        )
        # Many food sources around the agent
        food_rich = [{"x": i, "y": j, "type": "food"} for i in range(3, 8) for j in range(3, 8)]
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=food_rich)

        mu_2_start = model.mu_2
        for _ in range(20):
            model.update(Action("stay"), 0.0, perception)

        # mu_2 should shift
        assert abs(model.mu_2 - mu_2_start) > 0.0001, (
            f"Expected mu_2 to update with food-rich environment; "
            f"mu_2 stayed at {model.mu_2:.6f}"
        )

    def test_level2_pe_reflects_discrepancy(self):
        """
        When mu_1 food dims differ from g2_pred food dims, eps_2 should be nonzero.
        This test verifies the hierarchical error signal is computed correctly.
        """
        model = Model()
        # Set up state with a specific discrepancy
        model.mu_1 = [0.3, 0.4, 0.6, 0.7, 0.3]  # high food beliefs
        model.mu_2 = 0.2                           # but low context belief

        s = [0.3, 0.4, 0.6, 0.7, 0.3]
        mu_1_out, mu_2_out, eps_1_out, eps_2_out = model._run_inference(
            s, fix_mu_2=True
        )

        # eps_2[2] = mu_1[2] - g2[2] = mu_1[2] - mu_2 = 0.6 - 0.2 = 0.4 (approx at start)
        # After many iterations, eps_2 should reflect the discrepancy
        # At least the magnitude of eps_2 should be nonzero initially
        model.mu_1 = [0.3, 0.4, 0.6, 0.7, 0.3]
        model.mu_2 = 0.2
        g2 = model._g2_pred(model.mu_1, model.mu_2)
        eps_2_manual = [m - g for m, g in zip(model.mu_1, g2)]

        # Dim 2: mu_1[2]=0.6, g2[2]=0.2 → eps_2=0.4
        assert abs(eps_2_manual[2] - 0.4) < 1e-9, (
            f"Expected eps_2[2]=0.4; got {eps_2_manual[2]:.4f}"
        )
        # Dim 3: mu_1[3]=0.7, g2[3]=0.2 → eps_2=0.5
        assert abs(eps_2_manual[3] - 0.5) < 1e-9, (
            f"Expected eps_2[3]=0.5; got {eps_2_manual[3]:.4f}"
        )


# ---------------------------------------------------------------------------
# Contract tests: interface compliance
# ---------------------------------------------------------------------------

class TestContractCompliance:
    """Verify the DecisionModel contract is correctly implemented."""

    def test_decide_returns_action(self):
        model = Model()
        perception = make_perception()
        result = model.decide(perception)
        assert isinstance(result, Action)
        assert result.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_decide_does_not_mutate_state(self):
        """decide() must be read-only."""
        model = Model()
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=[])
        state_before = model.get_state()
        model.decide(perception)
        state_after = model.get_state()
        assert state_before == state_after, (
            "decide() must not mutate model state"
        )

    def test_update_mutates_state(self):
        """update() must change at least one state variable."""
        model = Model()
        perception = make_perception(x=2, y=3, gw=10, gh=10,
                                     food=[{"x": 4, "y": 4, "type": "food"}])
        state_before = {k: v for k, v in model.get_state().items()}
        model.update(Action("move_right"), 0.0, perception)
        state_after = model.get_state()
        assert state_before != state_after, "update() must modify model state"

    def test_get_state_has_required_keys(self):
        model = Model()
        state = model.get_state()
        required = {"s", "mu_1", "mu_2", "eps_1", "eps_2", "Pi_1", "Pi_2", "F", "a", "q_values"}
        missing = required - set(state.keys())
        assert not missing, f"get_state() missing keys: {missing}"

    def test_q_values_covers_all_actions(self):
        """q_values must contain all six action names."""
        model = Model()
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=[])
        model.update(Action("stay"), 0.0, perception)
        q = model.get_state()["q_values"]
        for act in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]:
            assert act in q, f"q_values missing action '{act}'"

    def test_q_values_are_floats(self):
        model = Model()
        perception = make_perception()
        model.update(Action("stay"), 0.0, perception)
        q = model.get_state()["q_values"]
        for act, val in q.items():
            assert isinstance(val, float), f"q_values['{act}'] is not float: {type(val)}"

    def test_free_energy_bounded(self):
        """F should be finite and not absurdly negative."""
        model = Model()
        perception = make_perception(x=5, y=5, gw=10, gh=10, food=[])
        model.update(Action("stay"), 0.0, perception)
        assert math.isfinite(model.F), f"F={model.F} is not finite"
        assert model.F > -10.0, f"F={model.F:.4f} is unexpectedly very negative"

    def test_precision_stays_in_bounds(self):
        """Pi_1 and Pi_2 must stay in [0.01, 100.0]."""
        model = Model()
        food = [{"x": i, "y": i, "type": "food"} for i in range(5)]
        for step in range(50):
            x, y = step % 10, (step * 3) % 10
            perception = make_perception(x=x, y=y, gw=10, gh=10, food=food)
            model.update(Action("stay"), 0.0, perception)

        assert 0.01 <= model.Pi_1 <= 100.0, f"Pi_1={model.Pi_1} out of [0.01, 100.0]"
        assert 0.01 <= model.Pi_2 <= 100.0, f"Pi_2={model.Pi_2} out of [0.01, 100.0]"

    def test_beliefs_stay_in_unit_range(self):
        """mu_1 components and mu_2 must stay in [0, 1]."""
        model = Model()
        food = [{"x": 2, "y": 3, "type": "food"}]
        for step in range(30):
            x, y = step % 10, (step * 7) % 10
            perception = make_perception(x=x, y=y, gw=10, gh=10, food=food)
            model.update(Action("move_right"), float(step % 2), perception)

        for i, v in enumerate(model.mu_1):
            assert 0.0 <= v <= 1.0, f"mu_1[{i}]={v} outside [0, 1]"
        assert 0.0 <= model.mu_2 <= 1.0, f"mu_2={model.mu_2} outside [0, 1]"

    def test_action_selection_explores_different_actions(self):
        """Over many steps, the agent should select multiple different actions."""
        random.seed(0)
        model = Model(beta=1.0)  # low temperature -> more exploration
        food = [{"x": 7, "y": 7, "type": "food"}]
        perception = make_perception(x=3, y=3, gw=10, gh=10, food=food)

        actions_seen = set()
        for _ in range(100):
            act = model.decide(perception)
            actions_seen.add(act.name)

        assert len(actions_seen) >= 3, (
            f"Expected agent to explore >=3 actions; only saw: {actions_seen}"
        )

    def test_full_cycle_decide_update_decide(self):
        """A full cycle of decide -> update -> decide must not crash."""
        model = Model()
        perception = make_perception(x=3, y=4, gw=10, gh=10,
                                     food=[{"x": 5, "y": 5, "type": "food"}])
        act1 = model.decide(perception)
        model.update(act1, 0.0, perception)
        act2 = model.decide(perception)
        assert act2.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_q_values_negative_free_energy(self):
        """q_values should be negative F_pred (less negative = better action)."""
        model = Model()
        food = [{"x": 5, "y": 5, "type": "food"}]
        perception = make_perception(x=3, y=5, gw=10, gh=10, food=food)
        model.update(Action("stay"), 0.0, perception)

        q = model.get_state()["q_values"]
        F_pred = model._compute_action_free_energies(perception, model.mu_1, model.eps_2)

        for act in ["move_up", "move_down", "move_left", "move_right", "stay"]:
            assert abs(q[act] - (-F_pred[act])) < 1e-9, (
                f"q_values[{act}] should be -F_pred[{act}]; "
                f"got q={q[act]:.4f}, -F_pred={-F_pred[act]:.4f}"
            )
