"""
Tests for AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel
Covers all expected_behaviors B1–B5.
"""

import math
import random
import sys
import time

import pytest

from algebraic_closed_form_ddm_with_softmax_action_selection_model import (
    Action,
    AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=0, y=0,
    grid_width=10, grid_height=10,
    step=0,
    food=None,
    last_action_result=None,
):
    """Build a minimal perception dict."""
    return {
        'x': x,
        'y': y,
        'grid_width': grid_width,
        'grid_height': grid_height,
        'step': step,
        'resources': {'food': food or []},
        'last_action_result': last_action_result or {},
    }


def manhattan(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


# ---------------------------------------------------------------------------
# B1: Agent moves toward food
# ---------------------------------------------------------------------------

class TestB1AgentMovesTowardFood:
    """
    B1: place food at (5,5), agent at (0,0).
    Over 50 steps, agent's distance to food should decrease on average.
    We use high beta (deterministic-ish) to make the test reliable.
    """

    def test_distance_decreases(self):
        random.seed(42)
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            softmax_inverse_temperature=20.0,  # nearly deterministic
            time_cost_penalty=0.0,             # no time penalty for cleaner signal
        )

        food_pos = (5, 5)
        x, y = 0, 0

        DIRECTION_MAP = {
            'move_up':    (0, -1),
            'move_down':  (0,  1),
            'move_left':  (-1, 0),
            'move_right': (1,  0),
        }

        initial_dist = manhattan((x, y), food_pos)
        distances = [initial_dist]

        for step in range(50):
            perception = make_perception(
                x=x, y=y,
                food=[{'x': food_pos[0], 'y': food_pos[1]}],
                step=step,
            )
            action = model.decide(perception)

            if action.name in DIRECTION_MAP:
                dx, dy = DIRECTION_MAP[action.name]
                new_x = max(0, min(9, x + dx))
                new_y = max(0, min(9, y + dy))
            else:
                new_x, new_y = x, y

            reward = 0.0
            new_perception = make_perception(
                x=new_x, y=new_y,
                food=[{'x': food_pos[0], 'y': food_pos[1]}],
                step=step,
            )
            model.update(action, reward, new_perception)

            x, y = new_x, new_y
            distances.append(manhattan((x, y), food_pos))

        # Distance should decrease: final distance < initial distance
        final_dist = distances[-1]
        assert final_dist < initial_dist, (
            f"Expected agent to approach food: initial_dist={initial_dist}, "
            f"final_dist={final_dist}"
        )

    def test_movement_actions_toward_food_have_higher_v(self):
        """Actions pointing toward food should have higher drift rates."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        # Agent at (0,0), food at (3,0) → move_right should have highest s_i
        perception = make_perception(
            x=0, y=0,
            food=[{'x': 3, 'y': 0}],
        )
        dummy_action = Action(name='stay')
        model.update(dummy_action, 0.0, perception)

        state = model.get_state()
        v = state['drift_rate']
        assert v['move_right'] > v['move_left'], (
            f"move_right drift ({v['move_right']:.4f}) should > move_left ({v['move_left']:.4f})"
        )
        assert v['move_right'] > v['move_up'], (
            f"move_right drift ({v['move_right']:.4f}) should > move_up ({v['move_up']:.4f})"
        )


# ---------------------------------------------------------------------------
# B2: Agent eats when on food cell
# ---------------------------------------------------------------------------

class TestB2AgentEatsOnFood:
    """
    B2: Place agent on food cell → run decide() 200 times → eat chosen > 70%.

    Design rationale:
      When the agent is on a food cell, s_eat = 1.0.
      Movement actions have s_move = 1/(1+d_neighbor_to_food).
      Since food is AT current pos (3,3), d from neighbor(4,3) to (3,3) = 1
        → s_move = 0.5.
      With sigma=1.0: P_eat ≈ 0.953, P_move ≈ 0.818, P_stay = 0.5.
      V_eat = 0.953, V_move ≈ 0.818, V_stay = 0.5.
      With beta=50 (near-deterministic):
        softmax gap between eat (0.953) and moves (0.818) = 0.135 * 50 = 6.75
        → eat dominates with probability ≈ exp(0)/(exp(0)+4*exp(-6.75)+exp(-22.7)) >> 99%
    """

    def test_eat_dominates_on_food_cell(self):
        random.seed(0)
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            softmax_inverse_temperature=50.0,  # strong exploitation → eat dominates
            diffusion_coefficient=1.0,          # meaningful P_i differences
            time_cost_penalty=0.0,              # no time penalty
        )
        food_pos = (3, 3)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )

        counts = {}
        N = 200
        for _ in range(N):
            action = model.decide(perception)
            counts[action.name] = counts.get(action.name, 0) + 1

        eat_fraction = counts.get('eat', 0) / N
        assert eat_fraction > 0.70, (
            f"Expected eat > 70% when on food (beta=50, sigma=1.0, lambda_t=0), "
            f"got {eat_fraction:.2%}. Full counts: {counts}"
        )

    def test_eat_signal_is_high_on_food(self):
        """Verify s_eat=1.0 and P_eat > 0.5 when agent is on food."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        food_pos = (2, 2)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )
        model.update(Action(name='stay'), 0.0, perception)
        state = model.get_state()

        assert state['perceptual_signal']['eat'] == pytest.approx(1.0)
        assert state['choice_probability']['eat'] > 0.5

    def test_eat_signal_low_off_food(self):
        """Verify s_eat=-0.5 when not on food."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(
            x=0, y=0,
            food=[{'x': 5, 'y': 5}],
        )
        model.update(Action(name='stay'), 0.0, perception)
        state = model.get_state()

        assert state['perceptual_signal']['eat'] == pytest.approx(-0.5)
        assert state['choice_probability']['eat'] < 0.5

    def test_eat_has_highest_signal_on_food_cell(self):
        """When on food cell, eat's signal (1.0) exceeds movement signals (0.5)."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        food_pos = (4, 4)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )
        model.update(Action(name='stay'), 0.0, perception)
        state = model.get_state()

        s_eat = state['perceptual_signal']['eat']
        for move_action in ['move_up', 'move_down', 'move_left', 'move_right']:
            s_move = state['perceptual_signal'][move_action]
            assert s_eat > s_move, (
                f"s_eat ({s_eat}) should > s_{move_action} ({s_move}) when on food cell"
            )

    def test_eat_has_highest_composite_value_on_food_sigma_1(self):
        """
        With sigma=1.0 (non-saturating regime), eat should have highest V_i when on food.
        """
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            diffusion_coefficient=1.0,
            time_cost_penalty=0.0,
        )
        food_pos = (5, 5)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()

        v_eat = state['composite_action_value']['eat']
        for action in ['move_up', 'move_down', 'move_left', 'move_right', 'stay']:
            v_other = state['composite_action_value'][action]
            assert v_eat >= v_other, (
                f"V_eat ({v_eat:.4f}) should >= V_{action} ({v_other:.4f})"
            )

    def test_eat_pi_highest_analytically(self):
        """
        With beta=50, sigma=1.0, lambda_t=0 on food cell:
        verify that pi_eat is analytically the largest probability.
        """
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            softmax_inverse_temperature=50.0,
            diffusion_coefficient=1.0,
            time_cost_penalty=0.0,
        )
        food_pos = (3, 3)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()

        pi = state['action_selection_probability']
        assert pi['eat'] > 0.70, (
            f"Analytic pi_eat should > 0.70 with beta=50, got {pi['eat']:.4f}. "
            f"Full pi: {pi}"
        )


# ---------------------------------------------------------------------------
# B3: Speed-accuracy trade-off via lambda_t
# ---------------------------------------------------------------------------

class TestB3SpeedAccuracyTradeoff:
    """
    B3: Higher lambda_t should favor actions with lower T_bar_i.
    """

    def test_higher_lambda_reduces_time_cost_tolerance(self):
        """
        With higher lambda_t, V_i is penalized more for high T_bar_i.
        """
        food_pos = (5, 5)
        perception = make_perception(x=2, y=2, food=[{'x': food_pos[0], 'y': food_pos[1]}])
        dummy = Action('stay')

        model_lo = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            time_cost_penalty=0.01,
        )
        model_lo.update(dummy, 0.0, perception)
        state_lo = model_lo.get_state()

        model_hi = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            time_cost_penalty=1.0,
        )
        model_hi.update(dummy, 0.0, perception)
        state_hi = model_hi.get_state()

        for action in ['move_up', 'move_down', 'move_left', 'move_right']:
            t_bar = state_lo['expected_decision_time'][action]
            if t_bar > 0.01:
                v_lo = state_lo['composite_action_value'][action]
                v_hi = state_hi['composite_action_value'][action]
                assert v_hi <= v_lo, (
                    f"Action {action}: V under high lambda_t ({v_hi:.4f}) "
                    f"should be <= V under low lambda_t ({v_lo:.4f}), T_bar={t_bar:.4f}"
                )

    def test_lambda_t_affects_composite_values(self):
        """Direct check: increasing lambda_t should reduce V_i for costly actions."""
        perception = make_perception(
            x=0, y=0,
            food=[{'x': 9, 'y': 9}],
        )

        model1 = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            time_cost_penalty=0.001,
        )
        model2 = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            time_cost_penalty=10.0,
        )
        dummy = Action('stay')
        model1.update(dummy, 0.0, perception)
        model2.update(dummy, 0.0, perception)

        state1 = model1.get_state()
        state2 = model2.get_state()

        sum_v1 = sum(state1['composite_action_value'].values())
        sum_v2 = sum(state2['composite_action_value'].values())
        assert sum_v2 < sum_v1, (
            f"Higher lambda_t should produce lower total V: "
            f"sum_v1={sum_v1:.4f}, sum_v2={sum_v2:.4f}"
        )


# ---------------------------------------------------------------------------
# B4: Q-learning adapts over time
# ---------------------------------------------------------------------------

class TestB4QLearningAdapts:
    """
    B4: After 50 eat-reward cycles, Q['eat'] should be > 0.5.
    """

    def test_q_eat_increases_with_rewards(self):
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            learning_rate=0.1,
        )
        food_pos = (1, 1)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )

        eat_action = Action(name='eat')
        reward = 1.0

        for _ in range(50):
            model.update(eat_action, reward, perception)

        state = model.get_state()
        q_eat = state['learned_action_utility']['eat']
        assert q_eat > 0.5, (
            f"Expected Q['eat'] > 0.5 after 50 reward cycles, got {q_eat:.4f}"
        )

    def test_q_values_start_at_zero(self):
        """Initial Q values should all be 0."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        state = model.get_state()
        for action, q in state['learned_action_utility'].items():
            assert q == pytest.approx(0.0), (
                f"Initial Q[{action}] should be 0, got {q}"
            )

    def test_only_chosen_q_updates(self):
        """Only the chosen action's Q-value should change."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(x=0, y=0, food=[{'x': 5, 'y': 5}])

        eat_action = Action(name='eat')
        model.update(eat_action, 1.0, perception)

        state = model.get_state()
        q = state['learned_action_utility']
        assert q['eat'] != pytest.approx(0.0), "Q['eat'] should have updated"
        for action in ['move_up', 'move_down', 'move_left', 'move_right', 'stay']:
            assert q[action] == pytest.approx(0.0), (
                f"Q[{action}] should remain 0, got {q[action]}"
            )

    def test_td_update_formula(self):
        """Verify TD update: Q_new = Q_old + alpha*(reward - Q_old)."""
        alpha = 0.3
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(learning_rate=alpha)
        perception = make_perception(x=0, y=0)

        # First update: Q_eat = 0 + 0.3*(1.0 - 0) = 0.3
        model.update(Action('eat'), 1.0, perception)
        state = model.get_state()
        assert state['learned_action_utility']['eat'] == pytest.approx(0.3, rel=1e-6)

        # Second update: Q_eat = 0.3 + 0.3*(1.0 - 0.3) = 0.3 + 0.21 = 0.51
        model.update(Action('eat'), 1.0, perception)
        state = model.get_state()
        assert state['learned_action_utility']['eat'] == pytest.approx(0.51, rel=1e-6)


# ---------------------------------------------------------------------------
# B5: No internal simulation loop — fast algebraic computation
# ---------------------------------------------------------------------------

class TestB5AlgebraicSpeed:
    """
    B5: decide() should be < 1ms per call (algebraic, no simulation loops).
    """

    def test_decide_under_1ms(self):
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(
            x=5, y=5,
            food=[{'x': 3, 'y': 3}, {'x': 7, 'y': 7}],
        )

        N = 1000
        random.seed(99)
        start = time.perf_counter()
        for _ in range(N):
            model.decide(perception)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / N) * 1000
        assert avg_ms < 1.0, (
            f"decide() averaged {avg_ms:.4f}ms per call, expected < 1ms"
        )

    def test_no_random_walk_loop_in_decide(self):
        """decide() should return in O(n_actions) time, not O(simulation_steps)."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(x=0, y=0, food=[{'x': 9, 'y': 9}])

        random.seed(0)
        start = time.perf_counter()
        for _ in range(10000):
            model.decide(perception)
        elapsed_10k = time.perf_counter() - start

        assert elapsed_10k < 1.0, (
            f"10000 decide() calls took {elapsed_10k:.3f}s, expected < 1.0s"
        )


# ---------------------------------------------------------------------------
# Additional unit tests: correctness of DDM formulas
# ---------------------------------------------------------------------------

class TestDDMFormulas:
    """Verify the closed-form DDM equations directly."""

    def test_choice_probability_positive_drift(self):
        """For v > 0, P_i > 0.5 (accumulates toward upper boundary)."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            boundary_separation=1.5,
            diffusion_coefficient=0.1,
        )
        perception = make_perception(
            x=0, y=0,
            food=[{'x': 1, 'y': 0}],
        )
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        assert state['choice_probability']['move_right'] > 0.5

    def test_choice_probability_at_zero_drift(self):
        """For v = 0, P_i should be exactly 0.5 (symmetric)."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            boundary_separation=1.5,
            diffusion_coefficient=0.1,
        )
        perception = make_perception(x=0, y=0, food=[])
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        assert state['choice_probability']['stay'] == pytest.approx(0.5, abs=1e-9)

    def test_decision_time_zero_drift_guard(self):
        """With |v| < epsilon, T_bar = a^2 / (2*sigma^2)."""
        a = 1.5
        sigma = 0.1
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            boundary_separation=a,
            diffusion_coefficient=sigma,
            zero_drift_guard=1.0,
        )
        perception = make_perception(x=0, y=0, food=[{'x': 5, 'y': 5}])
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        expected_T = a ** 2 / (2.0 * sigma ** 2)
        for action in ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']:
            T = state['expected_decision_time'][action]
            assert T == pytest.approx(expected_T, rel=1e-6), (
                f"T_bar[{action}]={T:.4f} should equal {expected_T:.4f}"
            )

    def test_softmax_probabilities_sum_to_one(self):
        """pi_i values must sum to 1.0."""
        random.seed(42)
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(
            x=3, y=3,
            food=[{'x': 7, 'y': 7}],
        )
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        total_pi = sum(state['action_selection_probability'].values())
        assert total_pi == pytest.approx(1.0, abs=1e-9)

    def test_softmax_probabilities_sum_to_one_after_q_updates(self):
        """pi_i values should still sum to 1 after Q-learning updates."""
        random.seed(5)
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        food_pos = (2, 2)
        perception = make_perception(
            x=food_pos[0], y=food_pos[1],
            food=[{'x': food_pos[0], 'y': food_pos[1]}],
        )
        for _ in range(20):
            model.update(Action('eat'), 1.0, perception)

        state = model.get_state()
        total_pi = sum(state['action_selection_probability'].values())
        assert total_pi == pytest.approx(1.0, abs=1e-9)

    def test_q_values_in_get_state(self):
        """get_state() must include q_values as a flat dict[str, float]."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        state = model.get_state()
        assert 'q_values' in state, "get_state() must include 'q_values'"
        q_values = state['q_values']
        assert isinstance(q_values, dict)
        for action in ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']:
            assert action in q_values, f"q_values must contain '{action}'"
            assert isinstance(q_values[action], float), (
                f"q_values['{action}'] must be float"
            )

    def test_decide_is_read_only(self):
        """
        Calling decide() multiple times should not mutate Q-values.
        """
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(
            x=1, y=1,
            food=[{'x': 5, 'y': 5}],
        )
        state_before = model.get_state()
        q_before = dict(state_before['learned_action_utility'])

        random.seed(3)
        for _ in range(10):
            model.decide(perception)

        state_after = model.get_state()
        q_after = dict(state_after['learned_action_utility'])

        for action in q_before:
            assert q_before[action] == q_after[action], (
                f"decide() mutated Q[{action}]: {q_before[action]} → {q_after[action]}"
            )

    def test_all_actions_present_in_state(self):
        """All 6 actions must appear in every per-action state dict."""
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel()
        perception = make_perception(x=0, y=0, food=[{'x': 3, 'y': 3}])
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()

        EXPECTED_ACTIONS = {'move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat'}
        for key in ['perceptual_signal', 'drift_rate', 'choice_probability',
                    'expected_decision_time', 'composite_action_value',
                    'action_selection_probability', 'learned_action_utility', 'q_values']:
            assert set(state[key].keys()) == EXPECTED_ACTIONS, (
                f"state['{key}'] missing actions: "
                f"{EXPECTED_ACTIONS - set(state[key].keys())}"
            )

    def test_p_i_formula_manual(self):
        """
        Manual verification of the R2 formula:
        P_i = 1/(1 + exp(-2*v*a/sigma^2))
        """
        a = 1.0
        sigma = 1.0
        v = 1.0
        expected = 1.0 / (1.0 + math.exp(-2.0 * v * a / sigma**2))
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            boundary_separation=a,
            diffusion_coefficient=sigma,
            drift_rate_scaling=1.0,
        )
        perception = make_perception(x=0, y=0, food=[{'x': 1, 'y': 0}])
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        P_move_right = state['choice_probability']['move_right']
        assert P_move_right == pytest.approx(expected, rel=1e-6), (
            f"P_move_right={P_move_right:.6f} should equal {expected:.6f}"
        )

    def test_t_bar_formula_manual(self):
        """
        Manual verification of R3 formula:
        T_bar = (a/(2v)) * tanh(v*a/sigma^2)
        """
        a = 1.0
        sigma = 1.0
        v = 1.0
        expected = (a / (2.0 * v)) * math.tanh(v * a / sigma**2)
        model = AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel(
            boundary_separation=a,
            diffusion_coefficient=sigma,
            drift_rate_scaling=1.0,
        )
        perception = make_perception(x=0, y=0, food=[{'x': 1, 'y': 0}])
        model.update(Action('stay'), 0.0, perception)
        state = model.get_state()
        T_move_right = state['expected_decision_time']['move_right']
        assert T_move_right == pytest.approx(expected, rel=1e-6), (
            f"T_move_right={T_move_right:.6f} should equal {expected:.6f}"
        )
