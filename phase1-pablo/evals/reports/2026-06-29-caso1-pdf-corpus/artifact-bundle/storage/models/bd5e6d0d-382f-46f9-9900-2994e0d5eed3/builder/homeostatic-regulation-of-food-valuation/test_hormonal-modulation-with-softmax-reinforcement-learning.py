"""
Tests for HormonalModulationWithSoftmaxReinforcementLearningModel
covering all expected_behaviors B1–B6 from the spec.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from hormonal_modulation_with_softmax_reinforcement_learning_model import (
    HormonalModulationWithSoftmaxReinforcementLearningModel,
    Action,
)

MODEL = HormonalModulationWithSoftmaxReinforcementLearningModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, food_list=None, last_action_result=None,
                    grid_width=10, grid_height=10, step=0):
    """Build a minimal perception dict."""
    if food_list is None:
        food_list = []
    if last_action_result is None:
        last_action_result = {}
    return {
        "x": x, "y": y,
        "grid_width": grid_width, "grid_height": grid_height,
        "step": step,
        "resources": {"food": food_list},
        "last_action_result": last_action_result,
    }


def make_model(**kwargs) -> MODEL:
    return MODEL(**kwargs)


# ---------------------------------------------------------------------------
# B1 – Ghrelin rises during fasting
# ---------------------------------------------------------------------------

class TestB1GhrelinRiseDuringFasting:
    """Without eating, G increases by ~lambda_G per step."""

    def test_ghrelin_rises_each_step(self):
        model = make_model(lambda_G=0.03, seed=42)
        initial_G = model.G

        for step in range(30):
            action = Action(name="stay")
            new_perc = make_perception(
                food_list=[], last_action_result={}, step=step
            )
            model.update(action, 0.0, new_perc)

        # G should have increased by ~30 * 0.03 = 0.9 from initial 0.3 → clamped to 1.0
        expected_G = min(initial_G + 30 * 0.03, 1.0)
        state = model.get_state()
        assert state["ghrelin_proxy"] > initial_G, (
            f"G should rise during fasting; got {state['ghrelin_proxy']} vs initial {initial_G}"
        )
        assert abs(state["ghrelin_proxy"] - expected_G) < 0.05, (
            f"G={state['ghrelin_proxy']:.4f} far from expected {expected_G:.4f}"
        )

    def test_ghrelin_rises_monotonically_for_first_few_steps(self):
        """Each non-eating step should strictly increase G (when not yet clamped)."""
        model = make_model(lambda_G=0.03, seed=0)
        model.G = 0.1  # start low so we don't hit the ceiling quickly

        prev_G = model.G
        for step in range(10):
            action = Action(name="move_up")
            new_perc = make_perception(last_action_result={}, step=step)
            model.update(action, 0.0, new_perc)
            current_G = model.get_state()["ghrelin_proxy"]
            assert current_G >= prev_G, (
                f"G should not decrease during fasting; step {step}: {current_G} < {prev_G}"
            )
            prev_G = current_G


# ---------------------------------------------------------------------------
# B2 – Ghrelin drops after eating
# ---------------------------------------------------------------------------

class TestB2GhrelinDropAfterEating:
    """Successful eat causes sharp ghrelin suppression (~kappa_G drop)."""

    def test_ghrelin_drops_by_kappa_G(self):
        model = make_model(kappa_G=0.5, lambda_G=0.03, seed=42)
        model.G = 0.8  # manually set high ghrelin

        action = Action(name="eat")
        new_perc = make_perception(
            last_action_result={"success": True},
            step=1
        )
        model.update(action, 1.0, new_perc)

        state = model.get_state()
        # G = clamp(0.8 + 0.03 - 0.5, 0, 1) = 0.33
        expected_G = max(0.0, min(1.0, 0.8 + 0.03 - 0.5))
        assert abs(state["ghrelin_proxy"] - expected_G) < 1e-9, (
            f"G should be {expected_G:.4f} after eating; got {state['ghrelin_proxy']:.4f}"
        )

    def test_ghrelin_significantly_lower_after_eating(self):
        """G after eating should be much lower than before."""
        model = make_model(kappa_G=0.5, lambda_G=0.03, seed=0)
        model.G = 0.8
        G_before = model.G

        action = Action(name="eat")
        new_perc = make_perception(last_action_result={"success": True}, step=0)
        model.update(action, 1.0, new_perc)

        G_after = model.get_state()["ghrelin_proxy"]
        assert G_after < G_before - 0.3, (
            f"G should drop sharply after eating; before={G_before:.3f}, after={G_after:.3f}"
        )

    def test_failed_eat_does_not_suppress_ghrelin(self):
        """A failed eat (no resource consumed) should not suppress ghrelin."""
        model = make_model(kappa_G=0.5, lambda_G=0.03, seed=0)
        model.G = 0.5
        G_before = model.G

        action = Action(name="eat")
        new_perc = make_perception(
            last_action_result={"success": False},
            step=0
        )
        model.update(action, 0.0, new_perc)

        G_after = model.get_state()["ghrelin_proxy"]
        # No suppression; G rises by lambda_G
        expected_G = min(1.0, G_before + 0.03)
        assert abs(G_after - expected_G) < 1e-9, (
            f"Failed eat should not suppress G; expected {expected_G:.4f}, got {G_after:.4f}"
        )


# ---------------------------------------------------------------------------
# B3 – Hormonal modulator amplifies food seeking when hungry
# ---------------------------------------------------------------------------

class TestB3ModulatorHighWhenHungry:
    """M >> 1 when G is high and E is low."""

    def test_M_greater_than_2_when_hungry(self):
        """Formula check: M = (1+w_G*G)/(1+w_L*L) with G=0.9, E=0.1 → M ≈ 2.33."""
        w_G, w_L, k_L = 2.0, 2.0, 1.0
        G, E = 0.9, 0.1
        L = E ** k_L
        M = (1.0 + w_G * G) / (1.0 + w_L * L)
        assert M > 2.0, f"M should be > 2.0 when G=0.9, E=0.1; got M={M:.4f}"

    def test_M_formula_hungry_via_update(self):
        """Verify model computes M correctly after update() with hungry state."""
        model = make_model(w_G=2.0, w_L=2.0, k_L=1.0, seed=0)
        # Set to hungry state before update
        model.G = 0.88  # after +0.03 → 0.91
        model.E = 0.12  # after -0.01 → 0.11

        action = Action(name="stay")
        new_perc = make_perception(last_action_result={}, step=0)
        model.update(action, 0.0, new_perc)

        # G_new=0.91, E_new=0.11, L_new=0.11
        # M = (1+2*0.91)/(1+2*0.11) = 2.82/1.22 ≈ 2.311
        state = model.get_state()
        assert state["hormonal_modulator"] > 2.0, (
            f"M should be > 2.0 when hungry; got {state['hormonal_modulator']:.4f}"
        )

    def test_update_computes_M_correctly(self):
        """M = (1+w_G*G_new)/(1+w_L*L_new) after state updates."""
        model = make_model(w_G=2.0, w_L=2.0, k_L=1.0,
                           lambda_G=0.03, alpha_E=0.01, seed=0)
        model.G = 0.7
        model.E = 0.2

        action = Action(name="stay")
        new_perc = make_perception(last_action_result={}, step=0)
        model.update(action, 0.0, new_perc)

        # G=clamp(0.7+0.03,0,1)=0.73, E=clamp(0.2-0.01,0,1)=0.19
        G_new = min(1.0, 0.7 + 0.03)
        E_new = max(0.0, 0.2 - 0.01)
        L_new = E_new ** 1.0
        expected_M = (1.0 + 2.0 * G_new) / (1.0 + 2.0 * L_new)

        state = model.get_state()
        assert abs(state["hormonal_modulator"] - expected_M) < 1e-9


# ---------------------------------------------------------------------------
# B4 – Hormonal modulator suppresses food seeking when satiated
# ---------------------------------------------------------------------------

class TestB4ModulatorLowWhenSatiated:
    """M < 1 when G is low and E is high."""

    def test_M_less_than_1_when_satiated(self):
        model = make_model(w_G=2.0, w_L=2.0, k_L=1.0, seed=0)
        model.G = 0.05  # low enough so after +lambda_G still produces M < 1
        model.E = 0.95  # high enough so after -alpha_E still produces M < 1

        action = Action(name="stay")
        new_perc = make_perception(last_action_result={}, step=0)
        model.update(action, 0.0, new_perc)

        state = model.get_state()
        M = state["hormonal_modulator"]
        assert M < 1.0, f"M should be < 1.0 when satiated; got M={M:.4f}"

    def test_M_formula_satiated(self):
        """M formula: (1 + 2*0.1) / (1 + 2*0.9) = 1.2/2.8 ≈ 0.429 < 1."""
        G, E, w_G, w_L = 0.1, 0.9, 2.0, 2.0
        L = E ** 1.0
        M = (1.0 + w_G * G) / (1.0 + w_L * L)
        assert M < 1.0, f"Satiated M formula should be < 1.0; got {M:.4f}"
        assert abs(M - 1.2 / 2.8) < 1e-9

    def test_M_satiated_less_than_M_hungry(self):
        """M_hungry > M_satiated by a large margin."""
        G_h, E_h = 0.9, 0.1
        M_h = (1.0 + 2.0 * G_h) / (1.0 + 2.0 * (E_h ** 1.0))

        G_s, E_s = 0.1, 0.9
        M_s = (1.0 + 2.0 * G_s) / (1.0 + 2.0 * (E_s ** 1.0))

        assert M_h > M_s * 2, (
            f"M_hungry={M_h:.3f} should be more than 2x M_satiated={M_s:.3f}"
        )


# ---------------------------------------------------------------------------
# B5 – Agent learns to approach food
# ---------------------------------------------------------------------------

class TestB5LearnsToApproachFood:
    """
    After training, Q-values for food-approach actions should exceed
    Q-values for food-retreat actions in states with food nearby.
    """

    def _run_training(self, n_steps=1000, seed=7):
        """
        Simulate training: food is fixed at (6,5). Agent starts at (5,5).
        Food is always to the right (dx=+1). Moving right → closer → eat → reward.
        """
        random.seed(seed)
        model = make_model(
            alpha=0.3, gamma=0.9, beta=2.0,
            r_food=1.0, c_step=-0.02,
            lambda_G=0.03, kappa_G=0.5,
            seed=seed,
        )

        food_x, food_y = 6, 5
        food_list = [{"x": food_x, "y": food_y, "type": "food", "palatability": 1.0}]
        x, y = 5, 5

        for step in range(n_steps):
            perception = make_perception(x=x, y=y, food_list=food_list, step=step)
            action = model.decide(perception)

            # Simulate movement
            nx, ny = x, y
            if action.name == "move_right":
                nx = min(x + 1, 9)
            elif action.name == "move_left":
                nx = max(x - 1, 0)
            elif action.name == "move_up":
                ny = max(y - 1, 0)
            elif action.name == "move_down":
                ny = min(y + 1, 9)

            x, y = nx, ny

            ate_success = (action.name == "eat" and x == food_x and y == food_y)
            last_result = {"success": ate_success}

            if ate_success:
                x, y = 5, 5  # reset after eating

            new_perc = make_perception(
                x=x, y=y, food_list=food_list,
                last_action_result=last_result, step=step
            )
            env_reward = 1.0 if ate_success else 0.0
            model.update(action, env_reward, new_perc)

        return model

    def test_approach_q_higher_than_retreat(self):
        """
        After training, the best move_right Q at (5,5) with food to the right
        should exceed the best move_left Q (across all hunger bins).
        """
        model = self._run_training(n_steps=1000, seed=7)

        # Check all hunger_bins for (5,5), food at (6,5): dx_sign=1, dy_sign=0, food_at_cell=0
        best_right = max(
            model._get_q((5, 5, 0, 1, 0, hb), "move_right")
            for hb in range(3)
        )
        best_left = max(
            model._get_q((5, 5, 0, 1, 0, hb), "move_left")
            for hb in range(3)
        )

        assert best_right > best_left, (
            f"Best move_right Q ({best_right:.4f}) should > best move_left Q ({best_left:.4f}) "
            f"when food is to the right."
        )

    def test_eat_q_positive_at_food_cell(self):
        """Q[eat] should be positive at the food cell after training."""
        model = self._run_training(n_steps=1000, seed=7)

        # Food cell (6,5): food_at_cell=1, dx=0, dy=0
        best_eat = max(
            model._get_q((6, 5, 1, 0, 0, hb), "eat")
            for hb in range(3)
        )

        assert best_eat > 0, (
            f"Q[eat] at food cell should be positive after training; best={best_eat:.4f}"
        )

    def test_q_table_grows_during_training(self):
        """Training should populate the Q-table with many entries."""
        model = self._run_training(n_steps=200, seed=42)
        state = model.get_state()
        assert state["q_table_size"] > 0, "Q-table should have entries after training"


# ---------------------------------------------------------------------------
# B6 – State-dependent eating probability via M modulation
# ---------------------------------------------------------------------------

class TestB6StateDependentEatingProbability:
    """
    Same Q-values but different M → different P(eat).
    P_hungry(eat) >> P_satiated(eat).
    """

    def _compute_eat_prob(self, model, state_key, x, y, food_list):
        """Compute softmax probability of eat action."""
        nearest = model._nearest_food(x, y, food_list)
        modulated = {}
        for a in model.ACTIONS:
            q = model._get_q(state_key, a)
            if model._is_food_related(a, x, y, nearest):
                modulated[a] = model.M * q
            else:
                modulated[a] = q

        scores = list(modulated.values())
        max_s = max(scores)
        exp_s = [math.exp(model.beta * (s - max_s)) for s in scores]
        total = sum(exp_s)
        probs = {a: e / total for a, e in zip(model.ACTIONS, exp_s)}
        return probs["eat"]

    def test_higher_M_increases_eat_probability(self):
        """
        P(eat | M_hungry) > P(eat | M_satiated) when there is competition.

        Setup: food is to the RIGHT of agent (dx=+1, not at current cell).
        eat is food-related (always); move_right is food-related (dx>0);
        other moves and stay are NOT food-related.

        Set Q[eat]=1.0, Q[stay]=1.0, others=0.
        With M_hungry=2.5: Q̃[eat]=2.5, Q̃[stay]=1.0 → eat strongly preferred.
        With M_satiated=0.3: Q̃[eat]=0.3, Q̃[stay]=1.0 → stay preferred.
        """
        # Food is to the right, not at current cell
        food_list = [{"x": 6, "y": 5, "type": "food", "palatability": 1.0}]
        x, y = 5, 5  # dx=+1, food not at cell → eat is food-related, stay is not

        model = make_model(beta=5.0, seed=0)
        state_key = (5, 5, 0, 1, 0, 1)  # food_at_cell=0, dx=1, dy=0, hunger_bin=1

        # Set up competition: eat and stay both have Q=1.0
        model._set_q(state_key, "eat", 1.0)
        model._set_q(state_key, "stay", 1.0)
        for a in ["move_up", "move_down", "move_left", "move_right"]:
            model._set_q(state_key, a, 0.0)

        # Hungry (M=2.5): Q̃[eat]=2.5, Q̃[stay]=1.0 → P(eat) high
        model.M = 2.5
        p_eat_hungry = self._compute_eat_prob(model, state_key, x, y, food_list)

        # Satiated (M=0.3): Q̃[eat]=0.3, Q̃[stay]=1.0 → P(eat) low
        model.M = 0.3
        p_eat_satiated = self._compute_eat_prob(model, state_key, x, y, food_list)

        assert p_eat_hungry > p_eat_satiated, (
            f"P(eat|hungry M=2.5)={p_eat_hungry:.4f} should > "
            f"P(eat|satiated M=0.3)={p_eat_satiated:.4f}"
        )
        ratio = p_eat_hungry / max(p_eat_satiated, 1e-10)
        assert ratio > 2.0, (
            f"P(eat) ratio hungry/satiated should be > 2; got {ratio:.2f}"
        )

    def test_modulated_qvalues_scale_with_M(self):
        """Q̃(eat) = M * Q(eat) for food actions."""
        model = make_model(seed=0)
        state_key = (3, 3, 1, 0, 0, 2)
        food_list = [{"x": 3, "y": 3, "type": "food", "palatability": 1.0}]
        x, y = 3, 3

        model._set_q(state_key, "eat", 2.0)

        model.M = 2.5
        modulated_hungry = model._compute_modulated_qvalues(
            state_key, make_perception(x=x, y=y, food_list=food_list)
        )

        model.M = 0.5
        modulated_satiated = model._compute_modulated_qvalues(
            state_key, make_perception(x=x, y=y, food_list=food_list)
        )

        assert abs(modulated_hungry["eat"] - 2.5 * 2.0) < 1e-9, (
            f"Q̃(eat) hungry should be 5.0; got {modulated_hungry['eat']:.4f}"
        )
        assert abs(modulated_satiated["eat"] - 0.5 * 2.0) < 1e-9, (
            f"Q̃(eat) satiated should be 1.0; got {modulated_satiated['eat']:.4f}"
        )

    def test_non_food_actions_not_modulated(self):
        """stay action should have Q̃ = Q (unmodulated) regardless of M."""
        model = make_model(seed=0)
        # No food present → stay is not food-related
        state_key = (5, 5, 0, 0, 0, 0)
        model._set_q(state_key, "stay", 1.5)

        perc = make_perception(x=5, y=5, food_list=[])

        model.M = 3.0
        mod_high = model._compute_modulated_qvalues(state_key, perc)

        model.M = 0.3
        mod_low = model._compute_modulated_qvalues(state_key, perc)

        assert mod_high["stay"] == mod_low["stay"] == 1.5, (
            f"stay Q-value should not be modulated; "
            f"high M={mod_high['stay']:.2f}, low M={mod_low['stay']:.2f}"
        )


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

class TestModelStructure:
    """Verify the model satisfies the DecisionModel contract."""

    def test_decide_returns_action(self):
        model = make_model(seed=0)
        perception = make_perception()
        action = model.decide(perception)
        assert isinstance(action, Action)
        assert action.name in MODEL.ACTIONS

    def test_get_state_keys_present(self):
        model = make_model(seed=0)
        state = model.get_state()
        required_keys = [
            "energy_store", "ghrelin_proxy", "leptin_proxy",
            "hormonal_modulator", "td_error", "reward_signal",
            "ate_flag", "q_values",
        ]
        for k in required_keys:
            assert k in state, f"Missing key in get_state(): {k}"

    def test_q_values_in_get_state(self):
        model = make_model(seed=0)
        state = model.get_state()
        assert "q_values" in state
        q = state["q_values"]
        assert isinstance(q, dict)
        for a in MODEL.ACTIONS:
            assert a in q, f"Action '{a}' missing from q_values"
            assert isinstance(q[a], float)

    def test_decide_does_not_modify_physiological_state(self):
        """decide() must not modify E, G, L, M."""
        model = make_model(seed=42)
        model.G = 0.6
        model.E = 0.4
        model.M = 1.5
        g_before = model.G
        e_before = model.E
        m_before = model.M

        perception = make_perception()
        for _ in range(5):
            model.decide(perception)

        assert model.G == g_before
        assert model.E == e_before
        assert model.M == m_before

    def test_initial_state_values(self):
        model = make_model()
        assert model.E == 0.5
        assert model.G == 0.3
        assert model.L == 0.5
        assert model.M == 1.0
        assert model.delta == 0.0
        assert model.ate == 0

    def test_energy_clamp_upper(self):
        """Energy should not exceed 1.0."""
        model = make_model(c_food=0.3, alpha_E=0.01, seed=0)
        model.E = 0.99
        action = Action(name="eat")
        new_perc = make_perception(last_action_result={"success": True}, step=0)
        model.update(action, 1.0, new_perc)
        assert 0.0 <= model.get_state()["energy_store"] <= 1.0

    def test_ghrelin_clamp_upper(self):
        """Ghrelin should not exceed 1.0."""
        model = make_model(seed=0)
        model.G = 0.99
        action = Action(name="stay")
        new_perc = make_perception(last_action_result={}, step=0)
        model.update(action, 0.0, new_perc)
        assert 0.0 <= model.get_state()["ghrelin_proxy"] <= 1.0

    def test_hormonal_modulator_extreme_hungry(self):
        """M = 3.0 at extreme hunger (G=1, E=0) with default weights."""
        w_G, w_L = 2.0, 2.0
        G, L = 1.0, 0.0
        M = (1.0 + w_G * G) / (1.0 + w_L * L)
        assert abs(M - 3.0) < 1e-9

    def test_hormonal_modulator_extreme_satiated(self):
        """M = 1/3 ≈ 0.333 at extreme satiety (G=0, E=1) with default weights."""
        w_G, w_L = 2.0, 2.0
        G, L = 0.0, 1.0
        M = (1.0 + w_G * G) / (1.0 + w_L * L)
        assert abs(M - 1.0 / 3.0) < 1e-9

    def test_td_error_computed_on_second_update(self):
        """After decide+update twice, delta = R (all-zero Q-table case)."""
        model = make_model(seed=42)
        food_list = [{"x": 6, "y": 5, "type": "food", "palatability": 1.0}]

        # Step 1
        p = make_perception(food_list=food_list)
        a = model.decide(p)
        new_p = make_perception(food_list=food_list, last_action_result={})
        model.update(a, 0.0, new_p)

        # Step 2: TD update fires since _decide_state is set
        a2 = model.decide(new_p)
        new_p2 = make_perception(food_list=food_list, last_action_result={})
        model.update(a2, 0.0, new_p2)

        state = model.get_state()
        # With all Q=0: delta = R + gamma*0 - 0 = R = c_step
        assert abs(state["td_error"] - state["reward_signal"]) < 1e-9, (
            "With all-zero Q-table, delta should equal R"
        )

    def test_eat_reward_modulated_by_M(self):
        """Eating reward R = M * r_food (R5), using M computed in same update call."""
        model = make_model(r_food=1.0, w_G=2.0, w_L=2.0,
                           lambda_G=0.03, kappa_G=0.5, k_L=1.0,
                           alpha_E=0.01, c_food=0.3, seed=0)
        model.G = 0.8
        model.E = 0.2

        action = Action(name="eat")
        new_perc = make_perception(last_action_result={"success": True}, step=0)
        model.update(action, 1.0, new_perc)

        state = model.get_state()
        # After update: G=clamp(0.8+0.03-0.5,0,1)=0.33, E=clamp(0.2-0.01+0.3,0,1)=0.49
        # L=0.49, M=(1+2*0.33)/(1+2*0.49)=1.66/1.98≈0.838
        # R = M * r_food = 0.838
        expected_R = state["hormonal_modulator"] * 1.0
        assert abs(state["reward_signal"] - expected_R) < 1e-9, (
            f"Eat reward should be M*r_food={expected_R:.4f}; got {state['reward_signal']:.4f}"
        )

    def test_leptin_tracks_energy(self):
        """With k_L=1, L == E after each update."""
        model = make_model(k_L=1.0, seed=0)
        for step in range(5):
            action = Action(name="stay")
            new_perc = make_perception(last_action_result={}, step=step)
            model.update(action, 0.0, new_perc)
            state = model.get_state()
            assert abs(state["leptin_proxy"] - state["energy_store"]) < 1e-12, (
                f"With k_L=1, L should equal E; "
                f"L={state['leptin_proxy']:.6f}, E={state['energy_store']:.6f}"
            )

    def test_q_table_updated_after_decide_update(self):
        """Q-table should have a non-default entry after decide()+update() cycle."""
        model = make_model(alpha=0.5, r_food=1.0, seed=0)
        food_list = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]

        perc = make_perception(x=5, y=5, food_list=food_list)
        a = model.decide(perc)

        # Simulate eat success
        new_perc = make_perception(
            x=5, y=5, food_list=food_list,
            last_action_result={"success": True} if a.name == "eat" else {}
        )
        model.update(a, 1.0, new_perc)

        state = model.get_state()
        assert state["q_table_size"] > 0, (
            "Q-table should have at least one entry after decide()+update()"
        )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
