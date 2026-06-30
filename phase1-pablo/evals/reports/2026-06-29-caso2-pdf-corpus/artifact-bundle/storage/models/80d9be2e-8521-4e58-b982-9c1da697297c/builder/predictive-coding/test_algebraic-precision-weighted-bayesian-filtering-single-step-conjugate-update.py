"""
Tests for Algebraic Precision-Weighted Bayesian Filtering (Single-Step Conjugate Update)

Tests correspond to expected_behaviors B1–B6 from the spec.
"""

import math
import random
import sys
import os

# Ensure the module is importable
sys.path.insert(0, os.path.dirname(__file__))

from algebraic_precision_weighted_bayesian_filtering_single_step_conjugate_update_model import (
    AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel,
    Action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=5, y=5, grid_width=10, grid_height=10, step=0,
    food=None, last_action_result=None
):
    return {
        'x': x,
        'y': y,
        'grid_width': grid_width,
        'grid_height': grid_height,
        'step': step,
        'resources': {'food': food or []},
        'last_action_result': last_action_result or {},
    }


def run_update_cycle(model, perception):
    """Run one decide→update cycle with a neutral action."""
    action = Action(name='stay')
    model.update(action, 0.0, perception)


def vec_norm(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ---------------------------------------------------------------------------
# B1: Posterior tracks sensory observation when pi_s >> pi_0
# ---------------------------------------------------------------------------
def test_B1_posterior_tracks_observation_when_high_sensory_precision():
    """
    When pi_s >> pi_0, the posterior mu_hat should be close to the sensory observation s.
    """
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=10.0, pi_0_init=1.0,
        alpha_pi=0.0,   # disable precision adaptation so pi_s stays at 10
    )

    # Override alpha_pi to keep precision fixed at 10
    model.alpha_pi = 0.0
    model.pi_s = 10.0
    model.pi_0 = 1.0

    # Create a perception with food that produces a non-trivial s vector
    food = [{'x': 5, 'y': 5, 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)

    run_update_cycle(model, perception)

    # Freeze pi_s to exactly 10 (alpha_pi=0 prevents it changing naturally)
    model.pi_s = 10.0

    # After the update with alpha_pi=0: pi_s stays near 10
    # mu_hat = (10*s + 1*mu_0) / 11 ≈ s (because 10/11 ≈ 0.909)
    s = model.s
    mu_hat = model.mu_hat

    # Recompute expected posterior analytically for validation
    mu_0 = model.mu_0
    expected = [(10.0 * s_i + 1.0 * m0_i) / 11.0 for s_i, m0_i in zip(s, mu_0)]

    assert vec_norm(mu_hat, expected) < 1e-9, \
        f"mu_hat should match conjugate formula exactly, got {mu_hat}, expected {expected}"

    # The posterior should be close to s (within weight 10/11)
    dist_to_s = vec_norm(mu_hat, s)
    assert dist_to_s < 0.2, \
        f"Posterior should be close to s when pi_s=10 >> pi_0=1, dist={dist_to_s:.4f}"


# ---------------------------------------------------------------------------
# B2: Posterior tracks prior prediction when pi_0 >> pi_s
# ---------------------------------------------------------------------------
def test_B2_posterior_tracks_prior_when_high_prior_precision():
    """
    When pi_0 >> pi_s, the posterior mu_hat should be close to the prior prediction mu_0.
    """
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=1.0, pi_0_init=10.0,
        alpha_pi=0.0,
    )
    model.alpha_pi = 0.0
    model.pi_s = 1.0
    model.pi_0 = 10.0

    # Set a non-trivial prior
    model.mu_hat = [0.8, 0.3, -0.2, 0.5, 0.4]

    # Perception with food at agent's location
    food = [{'x': 5, 'y': 5, 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)

    run_update_cycle(model, perception)

    # Freeze to intended precisions
    model.pi_s = 1.0
    model.pi_0 = 10.0

    s = model.s
    mu_0 = model.mu_0
    mu_hat = model.mu_hat

    # Recompute expected analytically
    expected = [(1.0 * s_i + 10.0 * m0_i) / 11.0 for s_i, m0_i in zip(s, mu_0)]

    assert vec_norm(mu_hat, expected) < 1e-9, \
        f"mu_hat should match formula exactly, got {mu_hat}, expected {expected}"

    # Posterior should be close to prior mu_0
    dist_to_prior = vec_norm(mu_hat, mu_0)
    assert dist_to_prior < 0.2, \
        f"Posterior should be close to prior when pi_0=10 >> pi_s=1, dist={dist_to_prior:.4f}"


# ---------------------------------------------------------------------------
# B3: Agent eats when food is present at current position
# ---------------------------------------------------------------------------
def test_B3_agent_eats_when_food_present():
    """
    When food is at the agent's position, 'eat' should be selected with high probability.
    We check that across many trials, eat is chosen more than 80% of the time.
    """
    random.seed(42)
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=4.0, pi_0_init=1.0, beta=5.0,
    )

    # Warm up: run a few steps so mu_hat reflects food presence
    food = [{'x': 5, 'y': 5, 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)
    for _ in range(5):
        run_update_cycle(model, perception)

    # Now sample many decisions
    eat_count = 0
    n_trials = 200
    for _ in range(n_trials):
        action = model.decide(perception)
        if action.name == 'eat':
            eat_count += 1

    eat_rate = eat_count / n_trials
    assert eat_rate > 0.8, \
        f"Expected eat rate > 0.80 when food is at position, got {eat_rate:.3f}"


# ---------------------------------------------------------------------------
# B4: Agent moves toward nearest food when not on food
# ---------------------------------------------------------------------------
def test_B4_agent_moves_toward_nearest_food():
    """
    With food at (7,5) and agent at (3,5), 'move_right' should be the most probable action.
    """
    random.seed(123)
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=4.0, pi_0_init=1.0, beta=5.0,
    )

    # Food to the right of agent
    food = [{'x': 7, 'y': 5, 'palatability': 1.0}]
    perception = make_perception(x=3, y=5, food=food, grid_width=10, grid_height=10)

    # Warm up model so beliefs reflect food to the right
    for _ in range(5):
        run_update_cycle(model, perception)

    # Sample many decisions and check move_right dominates
    action_counts = {'move_up': 0, 'move_down': 0, 'move_left': 0, 'move_right': 0,
                     'stay': 0, 'eat': 0}
    n_trials = 500
    for _ in range(n_trials):
        action = model.decide(perception)
        action_counts[action.name] += 1

    move_right_rate = action_counts['move_right'] / n_trials
    # move_right should be the most common action
    most_common = max(action_counts, key=action_counts.get)
    assert most_common == 'move_right', \
        f"Expected 'move_right' to be most common but got '{most_common}': {action_counts}"
    assert move_right_rate > 0.3, \
        f"Expected move_right rate > 0.3, got {move_right_rate:.3f}: {action_counts}"


# ---------------------------------------------------------------------------
# B5: Sensory precision increases in stable environment
# ---------------------------------------------------------------------------
def test_B5_precision_increases_in_stable_environment():
    """
    In an unchanging food layout, prediction errors should be small and pi_s should
    increase over many steps.
    """
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=1.0, pi_0_init=1.0, alpha_pi=0.15,
    )

    # Static food layout
    food = [{'x': 4, 'y': 4, 'palatability': 0.8}]
    perception = make_perception(x=5, y=5, food=food)

    initial_pi_s = model.pi_s

    # Run 50 steps in unchanging environment
    for _ in range(50):
        run_update_cycle(model, perception)

    final_pi_s = model.pi_s
    assert final_pi_s > initial_pi_s, \
        f"Sensory precision should increase in stable environment: " \
        f"initial={initial_pi_s:.4f}, final={final_pi_s:.4f}"


# ---------------------------------------------------------------------------
# B6: High uncertainty discourages movement via uncertainty_weight penalty
# ---------------------------------------------------------------------------
def test_B6_high_uncertainty_lowers_movement_values():
    """
    When pi_s is low relative to pi_0 (high uncertainty), movement values should be
    lower than when pi_s is high (low uncertainty).
    """
    # Scenario 1: Low pi_s / high pi_0 → high uncertainty
    model_uncertain = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=0.5, pi_0_init=5.0, alpha_pi=0.0,
    )
    model_uncertain.pi_s = 0.5
    model_uncertain.pi_0 = 5.0

    # Scenario 2: High pi_s / low pi_0 → low uncertainty
    model_certain = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=5.0, pi_0_init=1.0, alpha_pi=0.0,
    )
    model_certain.pi_s = 5.0
    model_certain.pi_0 = 1.0

    # Same perception: food to the right
    food = [{'x': 7, 'y': 5, 'palatability': 0.8}]
    perception = make_perception(x=5, y=5, food=food)

    # Warm up both models identically (alpha_pi=0 keeps precisions frozen)
    for _ in range(3):
        run_update_cycle(model_uncertain, perception)
        run_update_cycle(model_certain, perception)

    # Reset precisions to intended values after warm-up
    model_uncertain.pi_s = 0.5
    model_uncertain.pi_0 = 5.0
    model_certain.pi_s = 5.0
    model_certain.pi_0 = 1.0

    # Rebuild q_values with fixed precisions by running update once more
    action = Action(name='stay')
    model_uncertain.update(action, 0.0, perception)
    model_uncertain.pi_s = 0.5
    model_uncertain.pi_0 = 5.0

    model_certain.update(action, 0.0, perception)
    model_certain.pi_s = 5.0
    model_certain.pi_0 = 1.0

    state_uncertain = model_uncertain.get_state()
    state_certain = model_certain.get_state()

    # Uncertainty weight = 1 - pi_s/(pi_s+pi_0)
    uw_uncertain = 1.0 - 0.5 / (0.5 + 5.0)   # ≈ 0.909
    uw_certain = 1.0 - 5.0 / (5.0 + 1.0)       # ≈ 0.167

    assert uw_uncertain > uw_certain, \
        f"Setup check failed: uncertain model should have higher uw ({uw_uncertain:.3f} vs {uw_certain:.3f})"

    # Movement values should be lower when uncertainty is high
    move_actions = ['move_up', 'move_down', 'move_left', 'move_right']
    avg_move_uncertain = sum(state_uncertain['q_values'][a] for a in move_actions) / 4
    avg_move_certain = sum(state_certain['q_values'][a] for a in move_actions) / 4

    assert avg_move_uncertain < avg_move_certain, \
        f"Movement values should be lower under high uncertainty: " \
        f"uncertain_avg={avg_move_uncertain:.4f}, certain_avg={avg_move_certain:.4f}"


# ---------------------------------------------------------------------------
# Additional: get_state returns required keys including q_values
# ---------------------------------------------------------------------------
def test_get_state_contains_q_values():
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel()
    state = model.get_state()

    assert 'q_values' in state, "get_state() must include 'q_values'"
    q = state['q_values']
    assert isinstance(q, dict), "q_values must be a dict"

    expected_actions = {'eat', 'stay', 'move_up', 'move_down', 'move_left', 'move_right'}
    assert set(q.keys()) == expected_actions, \
        f"q_values must contain all action keys, got {set(q.keys())}"
    for k, v in q.items():
        assert isinstance(v, float), f"q_values['{k}'] must be float, got {type(v)}"


# ---------------------------------------------------------------------------
# Additional: decide is truly read-only (state doesn't change between two calls)
# ---------------------------------------------------------------------------
def test_decide_is_read_only():
    """Calling decide() multiple times should not change model state."""
    random.seed(999)
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel()

    food = [{'x': 3, 'y': 3, 'palatability': 0.7}]
    perception = make_perception(x=5, y=5, food=food)

    # Warm up
    run_update_cycle(model, perception)

    state_before = model.get_state()

    # Multiple decide calls
    for _ in range(10):
        model.decide(perception)

    state_after = model.get_state()

    assert state_before == state_after, \
        "decide() must not modify model state"


# ---------------------------------------------------------------------------
# Additional: conjugate update math is exact
# ---------------------------------------------------------------------------
def test_conjugate_update_math():
    """
    Verify the conjugate Gaussian posterior formula analytically:
    mu_hat = (pi_s * s + pi_0 * mu_0) / (pi_s + pi_0)
    """
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=3.0, pi_0_init=2.0, alpha_pi=0.0, gamma=0.9,
    )
    model.pi_s = 3.0
    model.pi_0 = 2.0
    model.alpha_pi = 0.0

    # Set prior mu_hat so we can predict mu_0
    model.mu_hat = [0.4, 0.2, -0.1, 0.3, 0.5]

    # Perception: agent at (5,5), food at (5,5)
    food = [{'x': 5, 'y': 5, 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food, grid_width=10, grid_height=10)

    # Run update
    run_update_cycle(model, perception)

    # Recompute analytically
    s = model.s
    mu_0 = model.mu_0
    expected_mu_hat = [(3.0 * s_i + 2.0 * m0_i) / 5.0 for s_i, m0_i in zip(s, mu_0)]

    assert vec_norm(model.mu_hat, expected_mu_hat) < 1e-9, \
        f"Conjugate update formula mismatch: {model.mu_hat} vs {expected_mu_hat}"


# ---------------------------------------------------------------------------
# Additional: prediction_error and surprise scalar
# ---------------------------------------------------------------------------
def test_prediction_error_and_surprise():
    """
    Verify eps = s - mu_0 and w = pi_s * dot(eps,eps) / (pi_s + pi_0).
    """
    model = AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel(
        pi_s_init=4.0, pi_0_init=1.0, alpha_pi=0.0, gamma=0.9,
    )
    model.pi_s = 4.0
    model.pi_0 = 1.0
    model.alpha_pi = 0.0
    model.mu_hat = [0.0, 0.1, -0.1, 0.2, 0.3]

    food = [{'x': 5, 'y': 5, 'palatability': 0.8}]
    perception = make_perception(x=5, y=5, food=food)

    run_update_cycle(model, perception)

    s = model.s
    mu_0 = model.mu_0
    expected_eps = [s_i - m0_i for s_i, m0_i in zip(s, mu_0)]
    expected_eps_sq = sum(e * e for e in expected_eps)
    expected_w = 4.0 * expected_eps_sq / (4.0 + 1.0)

    assert vec_norm(model.eps, expected_eps) < 1e-9, \
        f"Prediction error mismatch: {model.eps} vs {expected_eps}"
    assert abs(model.w - expected_w) < 1e-9, \
        f"Surprise scalar mismatch: {model.w} vs {expected_w}"


if __name__ == '__main__':
    test_B1_posterior_tracks_observation_when_high_sensory_precision()
    print("B1 passed")
    test_B2_posterior_tracks_prior_when_high_prior_precision()
    print("B2 passed")
    test_B3_agent_eats_when_food_present()
    print("B3 passed")
    test_B4_agent_moves_toward_nearest_food()
    print("B4 passed")
    test_B5_precision_increases_in_stable_environment()
    print("B5 passed")
    test_B6_high_uncertainty_lowers_movement_values()
    print("B6 passed")
    test_get_state_contains_q_values()
    print("get_state q_values passed")
    test_decide_is_read_only()
    print("decide read-only passed")
    test_conjugate_update_math()
    print("conjugate math passed")
    test_prediction_error_and_surprise()
    print("prediction error passed")
    print("\nAll tests passed!")
