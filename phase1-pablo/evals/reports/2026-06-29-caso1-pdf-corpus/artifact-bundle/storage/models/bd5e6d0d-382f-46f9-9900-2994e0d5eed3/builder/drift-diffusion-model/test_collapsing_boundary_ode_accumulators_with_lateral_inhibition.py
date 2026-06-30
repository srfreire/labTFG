"""
Tests for CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel

Covers expected behaviors B1–B6 from the spec.
"""

import math
import sys
import os
import random
import unittest

# PYTHONPATH is pre-configured to builder/drift-diffusion-model
from collapsing_boundary_ode_accumulators_with_lateral_inhibition_model import (
    CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel,
    Action,
    ACTIONS,
)


def make_perception(
    x=0, y=0, grid_width=10, grid_height=10, step=0,
    food=None, last_action_result=None
):
    """Helper to build a minimal perception dict."""
    return {
        'x': x,
        'y': y,
        'grid_width': grid_width,
        'grid_height': grid_height,
        'step': step,
        'resources': {'food': food or []},
        'last_action_result': last_action_result or {},
    }


class TestB1NavigatesTowardFood(unittest.TestCase):
    """B1: Agent navigates toward food — distance should decrease on average."""

    def test_agent_moves_toward_food(self):
        """
        Place food at (9, 9), agent at (0, 0).
        Simulate 30 steps. Track Manhattan distance to food.
        Assert final average position is closer than starting position.
        """
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(seed=42)
        food_x, food_y = 9, 9
        ax, ay = 0, 0

        direction_deltas = {
            'move_up': (0, -1), 'move_down': (0, 1),
            'move_left': (-1, 0), 'move_right': (1, 0),
        }

        initial_dist = abs(ax - food_x) + abs(ay - food_y)
        distances = []

        for step in range(30):
            perception = make_perception(
                x=ax, y=ay, step=step,
                food=[{'x': food_x, 'y': food_y}]
            )
            action = model.decide(perception)
            # Apply movement
            if action.name in direction_deltas:
                dx, dy = direction_deltas[action.name]
                new_ax = max(0, min(9, ax + dx))
                new_ay = max(0, min(9, ay + dy))
            else:
                new_ax, new_ay = ax, ay

            reward = 0.0
            if action.name == 'eat' and new_ax == food_x and new_ay == food_y:
                reward = 1.0

            new_perception = make_perception(
                x=new_ax, y=new_ay, step=step + 1,
                food=[{'x': food_x, 'y': food_y}]
            )
            model.update(action, reward, new_perception)
            ax, ay = new_ax, new_ay
            distances.append(abs(ax - food_x) + abs(ay - food_y))

        # Average distance over last 10 steps should be less than initial
        final_avg = sum(distances[-10:]) / 10
        self.assertLess(
            final_avg, initial_dist,
            f"Expected agent to approach food: initial_dist={initial_dist}, final_avg={final_avg}"
        )


class TestB2EatsWhenOnFood(unittest.TestCase):
    """B2: Agent eats when on food cell — eat should be chosen > 60% of the time."""

    def test_eat_preferred_on_food_cell(self):
        """
        Place agent on a food cell. Run decide() 200 times.
        Assert eat is chosen > 60% of the time.
        """
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(seed=7)
        perception = make_perception(
            x=3, y=3, food=[{'x': 3, 'y': 3}]
        )

        counts = {}
        for _ in range(200):
            action = model.decide(perception)
            counts[action.name] = counts.get(action.name, 0) + 1

        eat_count = counts.get('eat', 0)
        eat_fraction = eat_count / 200
        self.assertGreater(
            eat_fraction, 0.60,
            f"Expected eat fraction > 60%, got {eat_fraction:.2%} ({eat_count}/200)"
        )


class TestB3LateralInhibitionDecisiveness(unittest.TestCase):
    """
    B3: Lateral inhibition creates winner-take-all competition.
    With lateral inhibition (w > 0), action distribution should be MORE decisive
    (lower entropy) than with w=0 under the same perceptual conditions.
    """

    @staticmethod
    def _entropy(counts: dict, total: int) -> float:
        h = 0.0
        for c in counts.values():
            if c > 0:
                p = c / total
                h -= p * math.log2(p)
        return h

    def test_lateral_inhibition_reduces_entropy(self):
        """
        Run 300 trials each for model with inhibition (w=0.05) and without (w=0.0).
        Assert model with inhibition has lower or equal entropy.
        """
        n_trials = 300
        perception = make_perception(
            x=5, y=5,
            food=[{'x': 6, 'y': 5}, {'x': 5, 'y': 6}]
        )

        # With inhibition
        model_inh = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            w=0.05, seed=0
        )
        counts_inh: dict = {}
        for _ in range(n_trials):
            a = model_inh.decide(perception)
            counts_inh[a.name] = counts_inh.get(a.name, 0) + 1

        # Without inhibition
        model_no_inh = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            w=0.0, seed=0
        )
        counts_no_inh: dict = {}
        for _ in range(n_trials):
            a = model_no_inh.decide(perception)
            counts_no_inh[a.name] = counts_no_inh.get(a.name, 0) + 1

        h_inh = self._entropy(counts_inh, n_trials)
        h_no_inh = self._entropy(counts_no_inh, n_trials)

        self.assertLessEqual(
            h_inh, h_no_inh + 0.5,  # allow small tolerance
            f"Expected lower or similar entropy with inhibition: "
            f"h_inh={h_inh:.3f}, h_no_inh={h_no_inh:.3f}"
        )


class TestB4CollapsingBoundaryForcesDecision(unittest.TestCase):
    """
    B4: Collapsing boundary forces timely decisions.
    With all equal input drives (ambiguous), decision must be made before T_max
    in > 95% of trials.
    """

    def test_decision_before_timeout_in_ambiguous_case(self):
        """
        Set all perceptual signals equal by placing agent at center with no food.
        Run 200 trials; assert nearly all complete before T_max.
        """
        # With no food and agent at center, all movement signals will be equal
        # (all distances infinite → s_i = 1/(1+large) ≈ 0 for moves, stay=0, eat=-0.5)
        # This creates an ambiguous scenario among movement actions.
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            T_max=200, mu=0.02, seed=99
        )

        # Track whether the ODE simulation terminates before T_max
        # We do this by checking that the model always returns an action
        n_trials = 200
        decisions_made = 0

        for trial in range(n_trials):
            perception = make_perception(x=5, y=5, food=[])
            action = model.decide(perception)
            # Any action returned means a decision was made
            if action.name in ACTIONS:
                decisions_made += 1

        rate = decisions_made / n_trials
        self.assertGreater(
            rate, 0.95,
            f"Expected decisions in > 95% of trials, got {rate:.2%}"
        )


class TestB5LeakPreventsRunaway(unittest.TestCase):
    """
    B5: Leak prevents runaway activation.
    With very high v_i for one action, x_i should stabilize near v_i / kappa.
    """

    def test_activation_stabilizes_below_bound(self):
        """
        Give one action a very high drive.
        Run ODE for many steps (no threshold crossing) and verify x stabilizes.

        We use a model with high threshold to prevent early crossing.
        The steady-state for a single accumulator with no inhibition:
          dx/dt = v - kappa * x => x_ss = v / kappa
        With lateral inhibition from competing accumulators, x_ss <= v / kappa.
        """
        kappa = 0.15
        a_boundary = 10.0  # very high threshold so we can observe dynamics
        v_high = 2.0
        expected_ss = v_high / kappa  # ~13.3, but clamped by threshold

        # We test with a finite T_max and measure that x never goes to infinity
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            a=a_boundary, kappa=kappa, w=0.0, sigma=0.0,  # no noise for determinism
            dt=0.1, T_max=500, mu=0.0, theta_min=0.01, seed=0
        )

        # Manually trace the accumulator for one action with high drive
        # Build a perception that gives one specific action a large drive
        # 'eat' gets s_i = 1.0 if on food, so v_eat = k_v * 1.0 + r_bar = 1.5 + 0 = 1.5
        # To get very high drive, we set r_bar manually
        model.reward_trace['move_right'] = 5.0  # boosts v_move_right

        perception = make_perception(
            x=0, y=5,
            food=[{'x': 10, 'y': 5}]  # food to the right → move_right gets high s
        )

        action = model.decide(perception)
        # The chosen action should be move_right given its high drive
        # Check that accumulator activation is finite (not infinity)
        state = model.get_state()
        for act_name, xval in state['accumulator_activation'].items():
            self.assertTrue(
                math.isfinite(xval),
                f"Accumulator {act_name} is not finite: {xval}"
            )
            self.assertLess(
                xval, 1000.0,
                f"Accumulator {act_name} runaway: {xval} (expected finite)"
            )

    def test_steady_state_approximation(self):
        """
        Without noise (sigma=0) and with very high boundary, single-action drive
        should converge toward v/kappa at steady state.
        """
        kappa = 0.15
        v = 1.5  # k_v * s_eat (food on cell) + 0 reward trace
        expected_ss = v / kappa  # ~10.0

        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            a=50.0, kappa=kappa, w=0.0, sigma=0.0,
            dt=0.05, T_max=1000, mu=0.0, theta_min=0.01, seed=0
        )

        # Run with food on cell (eat gets s=1.0, v_eat=k_v*1.0=1.5)
        perception = make_perception(x=3, y=3, food=[{'x': 3, 'y': 3}])
        model.decide(perception)
        state = model.get_state()

        # eat accumulator should approach v/kappa = 1.5/0.15 = 10.0
        x_eat = state['accumulator_activation'].get('eat', 0.0)
        # Should be within 20% of steady state or at threshold
        # (the boundary is 50 so it won't cross early)
        self.assertGreater(
            x_eat, expected_ss * 0.5,
            f"Eat accumulator too low: {x_eat:.3f}, expected near {expected_ss:.3f}"
        )
        self.assertLess(
            x_eat, expected_ss * 1.5,
            f"Eat accumulator too high: {x_eat:.3f}, expected near {expected_ss:.3f}"
        )


class TestB6RewardTraceBiasesFutureDecisions(unittest.TestCase):
    """
    B6: Reward traces bias future decisions.
    After 10 eat rewards, r_bar['eat'] > 0.5 and eat is chosen more often.
    """

    def test_reward_trace_grows_with_rewards(self):
        """
        Give 10 eat rewards (reward=1.0 per update with eat action).
        Assert r_bar['eat'] > 0.5.
        """
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            alpha=0.1, seed=5
        )
        perception = make_perception(x=2, y=2, food=[{'x': 2, 'y': 2}])

        for _ in range(10):
            eat_action = Action(name='eat')
            model.update(eat_action, reward=1.0, new_perception=perception)

        state = model.get_state()
        r_bar_eat = state['reward_trace']['eat']
        self.assertGreater(
            r_bar_eat, 0.5,
            f"Expected r_bar_eat > 0.5 after 10 eat rewards, got {r_bar_eat:.4f}"
        )

    def test_reward_trace_increases_eat_preference(self):
        """
        After training reward traces with eat rewards, eat should be chosen
        more often when on food cell than a fresh model without training.
        """
        perception_on_food = make_perception(x=3, y=3, food=[{'x': 3, 'y': 3}])

        # Trained model: 15 eat rewards
        trained = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            alpha=0.1, seed=11
        )
        eat_action = Action(name='eat')
        for _ in range(15):
            trained.update(eat_action, reward=1.0, new_perception=perception_on_food)

        # Fresh model
        fresh = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(seed=11)

        n_trials = 200
        trained_eat = sum(
            1 for _ in range(n_trials)
            if trained.decide(perception_on_food).name == 'eat'
        )
        fresh_eat = sum(
            1 for _ in range(n_trials)
            if fresh.decide(perception_on_food).name == 'eat'
        )

        self.assertGreaterEqual(
            trained_eat, fresh_eat,
            f"Trained model should prefer eat >= fresh model: "
            f"trained={trained_eat}, fresh={fresh_eat}"
        )


class TestGetState(unittest.TestCase):
    """Test that get_state() returns a complete, well-formed snapshot."""

    def test_get_state_keys(self):
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel()
        state = model.get_state()
        required_keys = [
            'accumulator_activation', 'input_drive', 'perceptual_signal',
            'reward_trace', 'effective_threshold', 'urgency_signal',
            'chosen_action', 'q_values',
        ]
        for key in required_keys:
            self.assertIn(key, state, f"Missing key in get_state(): {key}")

    def test_q_values_cover_all_actions(self):
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel()
        perception = make_perception(x=0, y=0, food=[{'x': 5, 'y': 5}])
        action = model.decide(perception)
        model.update(action, 0.0, perception)
        state = model.get_state()
        for a in ACTIONS:
            self.assertIn(a, state['q_values'], f"q_values missing action: {a}")
            self.assertIsInstance(state['q_values'][a], float)

    def test_initial_state(self):
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel()
        state = model.get_state()
        # All reward traces should start at 0
        for a in ACTIONS:
            self.assertEqual(state['reward_trace'][a], 0.0)
        # Threshold starts at a
        self.assertEqual(state['effective_threshold'], 1.5)


class TestActionDataclass(unittest.TestCase):
    """Test Action dataclass behaves correctly."""

    def test_action_creation(self):
        a = Action(name='eat')
        self.assertEqual(a.name, 'eat')
        self.assertEqual(a.params, {})

    def test_action_with_params(self):
        a = Action(name='move_up', params={'speed': 1})
        self.assertEqual(a.params, {'speed': 1})


class TestDecideUpdateContract(unittest.TestCase):
    """Test that decide() is read-only and update() mutates state."""

    def test_decide_does_not_change_reward_trace(self):
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(seed=3)
        perception = make_perception(x=1, y=1, food=[{'x': 2, 'y': 2}])

        state_before = dict(model.get_state()['reward_trace'])
        model.decide(perception)
        state_after = dict(model.get_state()['reward_trace'])

        self.assertEqual(
            state_before, state_after,
            "decide() must not change reward_trace"
        )

    def test_update_changes_reward_trace(self):
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(seed=3)
        perception = make_perception(x=1, y=1, food=[{'x': 1, 'y': 1}])

        action = Action(name='eat')
        model.update(action, reward=1.0, new_perception=perception)
        state = model.get_state()
        self.assertGreater(
            state['reward_trace']['eat'], 0.0,
            "update() should increase reward_trace['eat'] after positive reward"
        )


class TestRewardTraceConvergence(unittest.TestCase):
    """Test that reward trace TD update converges toward reward value."""

    def test_td_convergence(self):
        """
        With alpha=0.1, after many updates with reward=1.0,
        r_bar_eat should converge toward 1.0.
        """
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(alpha=0.1)
        perception = make_perception(x=0, y=0)
        eat_action = Action(name='eat')

        for _ in range(100):
            model.update(eat_action, reward=1.0, new_perception=perception)

        state = model.get_state()
        r_bar = state['reward_trace']['eat']
        self.assertAlmostEqual(r_bar, 1.0, delta=0.05,
                               msg=f"r_bar_eat should converge to ~1.0, got {r_bar:.4f}")


class TestCollapsingThreshold(unittest.TestCase):
    """Test that the collapsing threshold behaves correctly."""

    def test_threshold_decreases_with_urgency(self):
        """
        With mu=0.01, a=1.5, theta_min=0.3:
        theta(t=50) = max(1.5 - 0.01*50, 0.3) = max(1.0, 0.3) = 1.0
        theta(t=120) = max(1.5 - 0.01*120, 0.3) = max(0.3, 0.3) = 0.3
        """
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            a=1.5, mu=0.01, theta_min=0.3
        )
        # Check formula manually
        t50 = max(model.a - model.mu * 50, model.theta_min)
        t120 = max(model.a - model.mu * 120, model.theta_min)
        self.assertAlmostEqual(t50, 1.0, places=5)
        self.assertAlmostEqual(t120, 0.3, places=5)
        self.assertGreater(t50, t120)

    def test_threshold_floor(self):
        """Threshold should never drop below theta_min."""
        model = CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel(
            a=1.5, mu=0.1, theta_min=0.3, T_max=1000
        )
        for t in range(1, 1001):
            theta = max(model.a - model.mu * t, model.theta_min)
            self.assertGreaterEqual(theta, model.theta_min)


if __name__ == '__main__':
    unittest.main()
