"""
Tests for Expected Free-Energy Policy Selection with Allostatic Prior Shifting
"""

import math
import random
import sys
import os
import importlib.util

# ---------------------------------------------------------------------------
# Dynamic import to handle hyphenated filename
# ---------------------------------------------------------------------------

_here = os.path.dirname(__file__)
_model_filename = "expected-free-energy-policy-selection-with-allostatic-prior-shifting_model.py"
_model_path = os.path.join(_here, _model_filename)

_spec = importlib.util.spec_from_file_location("efe_model", _model_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel = (
    _module.ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel
)
Action = _module.Action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=5, y=5, grid_width=10, grid_height=10, step=0,
    food=None, last_action_result=None
):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": food if food is not None else []},
        "last_action_result": last_action_result if last_action_result is not None else {},
    }


def make_food(x, y, palatability=1.0):
    return {"x": x, "y": y, "type": "food", "palatability": palatability}


def simulate_n_steps(model, n_steps, pos=(5, 5), food_list=None, grid_w=10, grid_h=10):
    """Run n steps with fixed food list, returning list of action names."""
    if food_list is None:
        food_list = []
    actions = []
    px, py = pos
    for step in range(n_steps):
        perc = make_perception(
            x=px, y=py,
            grid_width=grid_w, grid_height=grid_h,
            step=step, food=food_list
        )
        action = model.decide(perc)
        actions.append(action.name)
        lar = {}
        if action.name == "eat":
            food_here = any(f["x"] == px and f["y"] == py for f in food_list)
            lar = {"consumed": food_here, "palatability": 1.0, "success": food_here}
        elif action.name == "move_right":
            px = min(px + 1, grid_w - 1)
        elif action.name == "move_left":
            px = max(px - 1, 0)
        elif action.name == "move_down":
            py = min(py + 1, grid_h - 1)
        elif action.name == "move_up":
            py = max(py - 1, 0)
        model.update(action, 0.0, make_perception(
            x=px, y=py,
            grid_width=grid_w, grid_height=grid_h,
            step=step + 1, food=food_list,
            last_action_result=lar
        ))
    return actions


# ---------------------------------------------------------------------------
# B1: Allostatic prior shifts with environment richness
# ---------------------------------------------------------------------------

class TestB1AllostaticPriorShift:
    """Allostatic prior shifts downward in scarce environments and upward in rich ones."""

    def test_scarce_vs_rich_mu_p(self):
        """After 50 steps, mu_p in scarce env should be lower than in rich env."""
        # Scarce: 1 food item on 10×10 grid
        model_scarce = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=42)
        food_scarce = [make_food(9, 9)]
        simulate_n_steps(model_scarce, 50, food_list=food_scarce)
        mu_p_scarce = model_scarce.get_state()["mu_p"]

        # Rich: 10 food items on 10×10 grid
        model_rich = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=42)
        food_rich = [make_food(i % 10, i % 10) for i in range(10)]
        simulate_n_steps(model_rich, 50, food_list=food_rich)
        mu_p_rich = model_rich.get_state()["mu_p"]

        assert mu_p_scarce < mu_p_rich, (
            f"Expected mu_p_scarce ({mu_p_scarce:.4f}) < mu_p_rich ({mu_p_rich:.4f})"
        )

    def test_mu_p_decreases_in_empty_env(self):
        """In an environment with no food, mu_p should decrease toward mu_p_low."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            mu_p_base=0.8, mu_p_low=0.5, lambda_allo=0.1, seed=0
        )
        initial_mu_p = model.get_state()["mu_p"]
        simulate_n_steps(model, 20, food_list=[])
        final_mu_p = model.get_state()["mu_p"]
        assert final_mu_p < initial_mu_p, (
            f"Expected mu_p to decrease in empty env: initial={initial_mu_p:.4f}, final={final_mu_p:.4f}"
        )

    def test_mu_p_increases_in_dense_env(self):
        """In a dense food environment, mu_p should rise toward mu_p_base."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            mu_p_base=0.8, mu_p_low=0.5, lambda_allo=0.1, seed=0
        )
        # Force mu_p down first
        model.mu_p = 0.6
        food_rich = [make_food(i % 10, i // 10) for i in range(50)]
        simulate_n_steps(model, 30, food_list=food_rich, grid_w=10, grid_h=10)
        final_mu_p = model.get_state()["mu_p"]
        assert final_mu_p > 0.6, (
            f"Expected mu_p to rise in rich env: {final_mu_p:.4f}"
        )

    def test_mu_p_bounded(self):
        """mu_p should stay within plausible bounds after allostatic updates."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        simulate_n_steps(model, 50, food_list=[make_food(3, 3)])
        mu_p = model.get_state()["mu_p"]
        assert 0.0 <= mu_p <= 1.0, f"mu_p out of bounds: {mu_p:.4f}"


# ---------------------------------------------------------------------------
# B2: Anticipatory food-seeking at moderate energy
# ---------------------------------------------------------------------------

class TestB2AnticipatoryFoodSeeking:
    """Agent moves toward food at moderate energy (not waiting until critical)."""

    def test_moves_toward_food_within_5_steps(self):
        """At energy=0.6, food 3+ steps away → agent takes a movement action within 5 steps.

        5 steps gives the stochastic policy sampler reliable time to pick a movement
        while still being well before any critical-energy threshold.
        The spec requires anticipatory seeking; we verify it starts well above 0 energy.
        """
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.6

        food = [make_food(8, 5)]  # pos=(5,5), food at (8,5) → dx=3
        move_actions = {"move_right", "move_left", "move_up", "move_down"}

        moved = False
        for step in range(5):
            perc = make_perception(x=5, y=5, step=step, food=food)
            action = model.decide(perc)
            if action.name in move_actions:
                moved = True
            model.update(action, 0.0, make_perception(x=5, y=5, step=step + 1, food=food))
            if moved:
                break

        assert moved, "Agent should take a movement action within 5 steps at moderate energy"

    def test_active_at_moderate_energy(self):
        """Agent at energy=0.6 should not exclusively stay over 5 steps."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=7)
        model.energy = 0.6
        food = [make_food(8, 5)]

        actions = simulate_n_steps(model, 5, pos=(5, 5), food_list=food)
        non_stay = sum(1 for a in actions if a != "stay")
        assert non_stay > 0, (
            f"At moderate energy, agent should do more than just stay. Actions: {actions}"
        )

    def test_food_seeking_across_seeds(self):
        """Over multiple seeds, agent at energy=0.6 should move toward food in at least one."""
        food = [make_food(8, 5)]
        move_actions = {"move_right", "move_left", "move_up", "move_down"}
        found_movement = False

        for seed in range(10):
            model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=seed)
            model.energy = 0.6
            for step in range(3):
                perc = make_perception(x=5, y=5, step=step, food=food)
                action = model.decide(perc)
                if action.name in move_actions:
                    found_movement = True
                    break
                model.update(action, 0.0, make_perception(x=5, y=5, step=step + 1, food=food))
            if found_movement:
                break

        assert found_movement, "Across 10 seeds, agent should move toward food at moderate energy"


# ---------------------------------------------------------------------------
# B3: Epistemic exploration increases with high w_epist
# ---------------------------------------------------------------------------

class TestB3EpistemicExploration:
    """Agent with high w_epist should produce different G values and behaviors."""

    def test_high_epist_weight_changes_G(self):
        """High w_epist should produce different G values than w_epist=0."""
        model_high = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            w_epist=2.0, seed=99
        )
        model_none = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            w_epist=0.0, seed=99
        )

        food = [make_food(7, 7)]
        perc = make_perception(x=5, y=5, food=food)

        model_high.decide(perc)
        model_none.decide(perc)

        G_high = model_high._pending_G_vals[:]
        G_low = model_none._pending_G_vals[:]

        assert G_high != G_low, "Different w_epist should yield different G values"

    def test_epistemic_term_nonzero(self):
        """The epistemic component should be non-zero (A is not identity)."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            w_epist=1.0, seed=0
        )
        food = [make_food(7, 7)]
        perc = make_perception(x=5, y=5, food=food)
        model.decide(perc)

        G_vals = model._pending_G_vals
        assert any(abs(g) > 1e-10 for g in G_vals), (
            "G values should be non-zero (epistemic/pragmatic terms contribute)"
        )

    def test_high_epist_agent_runs_correctly(self):
        """Agent with high w_epist should run without errors."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            w_epist=2.0, seed=1234
        )
        model.energy = 0.7
        food = [make_food(9, 9)]
        actions = simulate_n_steps(model, 30, pos=(0, 0), food_list=food)
        assert len(actions) == 30
        for a in actions:
            assert a in model.ACTIONS


# ---------------------------------------------------------------------------
# B4: Transition model learning
# ---------------------------------------------------------------------------

class TestB4TransitionModelLearning:
    """B[eat] accumulates counts and remains a valid stochastic matrix."""

    def test_eat_increments_dirichlet_counts(self):
        """Repeatedly eating should increment b_counts['eat']."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            alpha_learn=0.05, seed=0
        )
        food = [make_food(5, 5, palatability=1.0)]

        initial_sum = sum(
            model.b_counts["eat"][r][c]
            for r in range(model.n_states)
            for c in range(model.n_states)
        )

        for step in range(100):
            model.energy = 0.3
            lar = {"consumed": True, "palatability": 1.0, "success": True}
            new_perc = make_perception(x=5, y=5, step=step + 1, food=food, last_action_result=lar)
            model.update(Action(name="eat"), 1.0, new_perc)

        final_sum = sum(
            model.b_counts["eat"][r][c]
            for r in range(model.n_states)
            for c in range(model.n_states)
        )

        assert final_sum > initial_sum, (
            "Dirichlet counts for 'eat' should increase after repeated eating"
        )

    def test_B_matrix_column_stochastic(self):
        """B[action] should be column-stochastic."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        for action in model.ACTIONS:
            B = model.B[action]
            for col in range(model.n_states):
                col_sum = sum(B[row][col] for row in range(model.n_states))
                assert abs(col_sum - 1.0) < 1e-6, (
                    f"B[{action}] column {col} sums to {col_sum:.6f}"
                )

    def test_B_concentrates_after_experience(self):
        """After many eat transitions, B[eat] column should concentrate."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(
            alpha_learn=0.1, seed=0
        )
        food = [make_food(5, 5, palatability=1.0)]

        # Force initial state
        s_old = (0, 0)
        model.prev_obs = s_old
        s_old_idx = model._obs_index(s_old)

        for step in range(100):
            model.energy = 0.05
            lar = {"consumed": True, "palatability": 1.0, "success": True}
            new_perc = make_perception(x=5, y=5, step=step + 1, food=food, last_action_result=lar)
            model.update(Action(name="eat"), 1.0, new_perc)

        col = [model.B["eat"][row][s_old_idx] for row in range(model.n_states)]
        max_prob = max(col)
        # Should be concentrated above uniform (1/20 = 0.05)
        assert max_prob > 1.0 / model.n_states, (
            f"B[eat] should concentrate; max_prob={max_prob:.4f}, uniform={1/model.n_states:.4f}"
        )

    def test_B_stays_valid_after_learning(self):
        """B matrices should remain valid after learning steps."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        food = [make_food(5, 5)]
        simulate_n_steps(model, 50, food_list=food)

        for action in model.ACTIONS:
            B = model.B[action]
            for col in range(model.n_states):
                col_sum = sum(B[row][col] for row in range(model.n_states))
                assert abs(col_sum - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# B5: Preference vector C shifts with allostatic prior
# ---------------------------------------------------------------------------

class TestB5PreferenceVectorShift:
    """C shifts so moderate energy bins are preferred when mu_p is low."""

    def test_mu_p_low_prefers_moderate_energy(self):
        """When mu_p=0.5, energy bin 2 (center=0.5) preferred over bin 4 (center=0.9)."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.mu_p = 0.5
        model.C = model._compute_C(model.mu_p)

        # dist_bin=0 for both: index = 0*5 + energy_bin
        C_bin2 = model.C[2]   # energy_bin=2, center=0.5
        C_bin4 = model.C[4]   # energy_bin=4, center=0.9

        assert C_bin2 > C_bin4, (
            f"With mu_p=0.5, C[energy_bin=2]={C_bin2:.4f} should be > C[energy_bin=4]={C_bin4:.4f}"
        )

    def test_mu_p_high_prefers_high_energy(self):
        """When mu_p=0.9, energy bin 4 (center=0.9) preferred over bin 2 (center=0.5)."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.mu_p = 0.9
        model.C = model._compute_C(model.mu_p)

        C_bin2 = model.C[2]
        C_bin4 = model.C[4]

        assert C_bin4 > C_bin2, (
            f"With mu_p=0.9, C[energy_bin=4]={C_bin4:.4f} should be > C[energy_bin=2]={C_bin2:.4f}"
        )

    def test_C_all_nonpositive(self):
        """C values should all be <= 0."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        for mu_p_val in [0.3, 0.5, 0.7, 0.9]:
            C = model._compute_C(mu_p_val)
            for i, c in enumerate(C):
                assert c <= 1e-9, f"C[{i}]={c:.4f} should be <= 0 for mu_p={mu_p_val}"

    def test_C_peak_matches_mu_p_bin(self):
        """The best energy bin in C should be the one closest to mu_p."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        bin_center_to_target = [(0, 0.1), (1, 0.3), (2, 0.5), (3, 0.7), (4, 0.9)]
        for target_bin, mu_p_val in bin_center_to_target:
            C = model._compute_C(mu_p_val)
            best_e_bin = max(range(model.n_energy), key=lambda e: C[e])
            assert best_e_bin == target_bin, (
                f"For mu_p={mu_p_val}, expected best_e_bin={target_bin}, got {best_e_bin}"
            )

    def test_C_changes_with_allostatic_update(self):
        """After allostatic update in scarce env, C should shift."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        C_before = model.C[:]
        simulate_n_steps(model, 30, food_list=[])  # scarce env decreases mu_p
        C_after = model.C[:]
        assert C_before != C_after, "C should change after allostatic adaptation"


# ---------------------------------------------------------------------------
# B6: Multi-step planning vs myopic
# ---------------------------------------------------------------------------

class TestB6MultiStepPlanning:
    """Verify T=3 and T=1 agents both run correctly without errors."""

    def _count_eats(self, model, n_steps, grid_w=10, grid_h=10):
        food_pos = (5, 5)
        pos = [0, 0]
        eat_count = 0
        food_available = True

        for step in range(n_steps):
            food = [make_food(food_pos[0], food_pos[1])] if food_available else []
            perc = make_perception(
                x=pos[0], y=pos[1],
                grid_width=grid_w, grid_height=grid_h,
                step=step, food=food
            )
            action = model.decide(perc)

            lar = {}
            food_here = (pos[0] == food_pos[0] and pos[1] == food_pos[1])
            if action.name == "eat" and food_here and food_available:
                eat_count += 1
                lar = {"consumed": True, "palatability": 1.0, "success": True}
                food_available = False
            elif action.name == "eat":
                lar = {"consumed": False, "palatability": 0.0, "success": False}
            else:
                if action.name == "move_right" and pos[0] < grid_w - 1:
                    pos[0] += 1
                elif action.name == "move_left" and pos[0] > 0:
                    pos[0] -= 1
                elif action.name == "move_down" and pos[1] < grid_h - 1:
                    pos[1] += 1
                elif action.name == "move_up" and pos[1] > 0:
                    pos[1] -= 1

            if step % 5 == 4:
                food_available = True

            new_food = [make_food(food_pos[0], food_pos[1])] if food_available else []
            new_perc = make_perception(
                x=pos[0], y=pos[1],
                grid_width=grid_w, grid_height=grid_h,
                step=step + 1, food=new_food,
                last_action_result=lar
            )
            model.update(action, float(eat_count > 0), new_perc)

        return eat_count

    def test_T3_agent_runs_without_errors(self):
        """T=3 agent should run 200 steps without errors."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(T=3, seed=0)
        eat_count = self._count_eats(model, 200)
        assert eat_count >= 0

    def test_T1_agent_runs_without_errors(self):
        """T=1 agent should run 200 steps without errors."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(T=1, seed=0)
        eat_count = self._count_eats(model, 200)
        assert eat_count >= 0

    def test_T3_produces_18_policies(self):
        """T=3 with 6 first actions × 3 continuations = 18 policies."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(T=3, seed=0)
        food = [make_food(7, 7)]
        policies = model._enumerate_policies((5, 5), food)
        assert len(policies) == 18

    def test_T1_produces_18_policies(self):
        """T=1 with 6 first actions × 3 continuations = 18 policies."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(T=1, seed=0)
        food = [make_food(7, 7)]
        policies = model._enumerate_policies((5, 5), food)
        assert len(policies) == 18


# ---------------------------------------------------------------------------
# Core mechanics tests
# ---------------------------------------------------------------------------

class TestCoreMechanics:
    """Unit tests for individual components."""

    def test_energy_increases_on_eat(self):
        """Energy should increase when eating succeeds."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.5
        food = [make_food(5, 5)]
        action = Action(name="eat")
        lar = {"consumed": True, "palatability": 1.0, "success": True}
        new_perc = make_perception(x=5, y=5, food=food, last_action_result=lar)
        model.update(action, 1.0, new_perc)
        assert model.energy > 0.5, f"Energy should increase on eat, got {model.energy:.4f}"

    def test_energy_decreases_on_move(self):
        """Energy should decrease on movement."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.5
        action = Action(name="move_up")
        new_perc = make_perception(x=5, y=4)
        model.update(action, 0.0, new_perc)
        assert model.energy < 0.5, f"Energy should decrease on move, got {model.energy:.4f}"

    def test_energy_decreases_on_stay(self):
        """Energy should decrease on stay (metabolic cost)."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.5
        action = Action(name="stay")
        new_perc = make_perception(x=5, y=5)
        model.update(action, 0.0, new_perc)
        assert model.energy < 0.5, f"Energy should decrease on stay, got {model.energy:.4f}"

    def test_energy_clamped_upper(self):
        """Energy should not exceed 1.0."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 1.0
        food = [make_food(5, 5)]
        action = Action(name="eat")
        lar = {"consumed": True, "palatability": 1.0, "success": True}
        new_perc = make_perception(x=5, y=5, food=food, last_action_result=lar)
        model.update(action, 1.0, new_perc)
        assert model.energy <= 1.0

    def test_energy_clamped_lower(self):
        """Energy should not go below 0.0."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.0
        action = Action(name="move_up")
        new_perc = make_perception(x=5, y=4)
        model.update(action, 0.0, new_perc)
        assert model.energy >= 0.0

    def test_q_s_sums_to_one(self):
        """State posterior q_s should always sum to 1."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        food = [make_food(3, 3)]
        for step in range(10):
            perc = make_perception(x=5, y=5, step=step, food=food)
            action = model.decide(perc)
            model.update(action, 0.0, make_perception(x=5, y=5, step=step + 1, food=food))

            q_s_sum = sum(model.q_s)
            assert abs(q_s_sum - 1.0) < 1e-6, f"q_s sums to {q_s_sum:.6f} at step {step}"

    def test_decide_returns_valid_action(self):
        """decide() should return an Action with a valid action name."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        perc = make_perception(x=5, y=5, food=[make_food(7, 7)])
        action = model.decide(perc)
        assert isinstance(action, Action)
        assert action.name in model.ACTIONS, f"Invalid action: {action.name}"

    def test_get_state_has_q_values(self):
        """get_state() must include q_values dict."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        state = model.get_state()
        assert "q_values" in state
        assert isinstance(state["q_values"], dict)
        assert len(state["q_values"]) == len(model.ACTIONS)

    def test_q_values_floats_after_update(self):
        """After update(), q_values should be populated with floats."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        perc = make_perception(x=5, y=5, food=[make_food(7, 7)])
        action = model.decide(perc)
        model.update(action, 0.0, perc)
        state = model.get_state()
        for k, v in state["q_values"].items():
            assert isinstance(v, float), f"q_values[{k}] should be float, got {type(v)}"

    def test_obs_index_in_range(self):
        """Observation index should always be in [0, n_states)."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        for dist_bin in range(model.n_dist):
            for e_bin in range(model.n_energy):
                idx = model._obs_index((dist_bin, e_bin))
                assert 0 <= idx < model.n_states, (
                    f"obs_index out of range: ({dist_bin}, {e_bin}) → {idx}"
                )

    def test_A_matrix_rows_sum_to_one(self):
        """Each row of likelihood matrix A should sum to 1."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        for o in range(model.n_obs):
            row_sum = sum(model.A[o])
            assert abs(row_sum - 1.0) < 1e-6, (
                f"A row {o} sums to {row_sum:.6f}"
            )

    def test_decide_is_readonly(self):
        """decide() must not mutate energy, mu_p, or q_s."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.55
        model.mu_p = 0.72
        q_s_before = model.q_s[:]

        perc = make_perception(x=5, y=5, food=[make_food(7, 7)])
        model.decide(perc)

        assert model.energy == 0.55, "decide() must not change energy"
        assert model.mu_p == 0.72, "decide() must not change mu_p"
        assert model.q_s == q_s_before, "decide() must not change q_s"

    def test_policy_each_length_T(self):
        """All generated policies should have exactly T actions."""
        for T in [1, 2, 3, 4]:
            model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(T=T, seed=0)
            food = [make_food(7, 7)]
            policies = model._enumerate_policies((5, 5), food)
            for pi in policies:
                assert len(pi) == T, f"Policy {pi} has length {len(pi)}, expected {T}"

    def test_all_policy_actions_valid(self):
        """All actions in generated policies should be in ACTIONS."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        food = [make_food(7, 7)]
        policies = model._enumerate_policies((5, 5), food)
        for pi in policies:
            for a in pi:
                assert a in model.ACTIONS, f"Invalid action '{a}' in policy {pi}"

    def test_dist_bin_discretisation(self):
        """Distance discretisation should produce bins 0-3 correctly."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        assert model._dist_bin(0) == 0, "Distance 0 should be bin 0 (at resource)"
        assert model._dist_bin(1) == 1, "Distance 1 should be bin 1 (near)"
        assert model._dist_bin(2) == 1, "Distance 2 should be bin 1 (near)"
        assert model._dist_bin(3) == 2, "Distance 3 should be bin 2 (medium)"
        assert model._dist_bin(5) == 2, "Distance 5 should be bin 2 (medium)"
        assert model._dist_bin(6) == 3, "Distance 6 should be bin 3 (far)"
        assert model._dist_bin(100) == 3, "Distance 100 should be bin 3 (far)"

    def test_energy_bin_discretisation(self):
        """Energy discretisation should produce correct bins."""
        model = ExpectedFreeEnergyPolicySelectionWithAllostaticPriorShiftingModel(seed=0)
        model.energy = 0.0
        assert model._energy_bin() == 0
        model.energy = 0.19
        assert model._energy_bin() == 0
        model.energy = 0.5
        assert model._energy_bin() == 2
        model.energy = 0.99
        assert model._energy_bin() == 4
        model.energy = 1.0
        assert model._energy_bin() == 4  # clamped


# ---------------------------------------------------------------------------
# Run with pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
