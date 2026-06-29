"""
Tests for ContinuousFreeEnergyGradientDescentWithPrecisionWeightedPredictionErrors model.
Covers all 5 expected_behaviors from the spec.
"""

import importlib.util
import math
import os
import random
import sys


# ---------------------------------------------------------------------------
# Dynamic import to handle hyphenated filename
# ---------------------------------------------------------------------------

_MODEL_FILE = os.path.join(
    os.path.dirname(__file__),
    "continuous-free-energy-gradient-descent-with-precision-weighted-prediction-errors_model.py",
)
_spec = importlib.util.spec_from_file_location("_cfeg_model", _MODEL_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Model = _mod.ContinuousFreeEnergyGradientDescentWithPrecisionWeightedPredictionErrorsModel
Action = _mod.Action


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, food=None, step=0, last_action_result=None):
    """Build a minimal perception dict."""
    return {
        "x": x,
        "y": y,
        "grid_width": 10,
        "grid_height": 10,
        "step": step,
        "resources": {"food": food if food is not None else []},
        "last_action_result": last_action_result if last_action_result is not None else {},
    }


def run_step(model, perception, action_name=None):
    """
    Run one full simulation step.
    decide() receives perception WITHOUT last_action_result.
    update() receives perception WITH last_action_result.
    """
    p_no_result = dict(perception)
    p_no_result["last_action_result"] = {}

    if action_name is None:
        action = model.decide(p_no_result)
    else:
        action = Action(name=action_name)

    # Simulate a trivial env response
    last_action_result = {}
    if action.name == "eat":
        food_list = perception.get("resources", {}).get("food", [])
        food_here = [f for f in food_list if f["x"] == perception["x"] and f["y"] == perception["y"]]
        if food_here:
            last_action_result = {"consumed": True, "palatability": food_here[0].get("palatability", 1.0)}
        else:
            last_action_result = {"consumed": False}

    p_with_result = dict(perception)
    p_with_result["last_action_result"] = last_action_result

    model.update(action, 0.0, p_with_result)
    return action


# ---------------------------------------------------------------------------
# B1: Belief state converges toward precision-weighted posterior
# ---------------------------------------------------------------------------

class TestB1BeliefConvergence:
    """
    B1: Belief state mu converges toward the precision-weighted combination of
    interoceptive observation s_t and interoceptive prior mu_p.

    The belief update R6 is:
        mu_new = mu + kappa * (pi_s * eps_s - pi_p * eps_p)
               = mu + kappa * (pi_s*(s_t - mu) - pi_p*(mu - mu_p))

    With no noise (sigma_s=0), s_t = energy.

    Fixed point:
        pi_s * (energy - mu*) = pi_p * (mu* - mu_p)
        mu* = (pi_s * energy + pi_p * mu_p) / (pi_s + pi_p)

    IMPORTANT: energy also evolves (depletes by c_stay each step).
    So we test convergence direction rather than exact value, or fix energy.
    """

    def test_belief_converges_to_posterior_mean_fixed_energy(self):
        """
        With sigma_s=0 and energy held fixed (we manually reset it after each step),
        mu should converge to the precision-weighted posterior mean.
        """
        pi_s, pi_p = 1.0, 2.0
        energy_val = 0.3
        mu_p_val = 1.0
        # Analytical fixed point (precision-weighted Bayesian posterior mean)
        expected_mu_star = (pi_s * energy_val + pi_p * mu_p_val) / (pi_s + pi_p)
        # = (0.3 + 2.0) / 3 = 0.7667

        model = Model(rng_seed=42, sigma_s=0.0, pi_s=pi_s, pi_p=pi_p,
                      kappa=0.5, mu_p_value=mu_p_val)
        model.energy = energy_val
        model.mu = 0.5  # Start somewhere different from the fixed point

        perception = make_perception(food=[])
        for _ in range(50):
            run_step(model, perception, action_name="stay")
            # Re-fix energy to prevent metabolic depletion from shifting the target
            model.energy = energy_val

        final_mu = model.get_state()["mu"]
        assert abs(final_mu - expected_mu_star) < 0.05, (
            f"Belief did not converge to precision-weighted posterior: "
            f"expected mu*={expected_mu_star:.4f}, got {final_mu:.4f}"
        )

    def test_belief_reduces_free_energy_over_time(self):
        """
        Across many steps, free energy should decrease (mu approaches fixed point).
        Test: F after 30 steps < F at step 1.
        """
        model = Model(rng_seed=7, sigma_s=0.0, kappa=0.5)
        model.energy = 0.5
        model.mu = 0.0  # Far from both energy and mu_p=1.0; fixed point ≈ 0.833

        perception = make_perception(food=[])
        # First step to get initial F
        run_step(model, perception, action_name="stay")
        F_initial = model.get_state()["F"]

        for _ in range(29):
            run_step(model, perception, action_name="stay")
        F_final = model.get_state()["F"]

        assert F_final < F_initial, (
            f"Free energy did not decrease over time: F_initial={F_initial:.6f}, F_final={F_final:.6f}"
        )

    def test_belief_converges_from_above(self):
        """
        Starting with mu above the fixed point, mu should decrease toward it.
        Fixed point with fixed energy=0.3: mu* ≈ 0.767.
        mu starts at 0.95 (above). Should decrease.
        """
        pi_s, pi_p = 1.0, 2.0
        energy_val = 0.3
        mu_p_val = 1.0
        mu_star = (pi_s * energy_val + pi_p * mu_p_val) / (pi_s + pi_p)  # ≈ 0.767

        model = Model(rng_seed=0, sigma_s=0.0, pi_s=pi_s, pi_p=pi_p,
                      kappa=0.5, mu_p_value=mu_p_val)
        model.energy = energy_val
        model.mu = 0.95  # start above fixed point

        dist_initial = abs(model.mu - mu_star)
        perception = make_perception(food=[])
        for _ in range(20):
            run_step(model, perception, action_name="stay")
            model.energy = energy_val  # hold energy fixed

        dist_final = abs(model.get_state()["mu"] - mu_star)
        assert dist_final < dist_initial, (
            f"mu did not approach fixed point: dist_initial={dist_initial:.4f}, dist_final={dist_final:.4f}"
        )

    def test_belief_converges_from_below(self):
        """
        Starting with mu below the fixed point, mu should increase toward it.
        Fixed point with fixed energy=0.3: mu* ≈ 0.767.
        mu starts at 0.2 (below). Should increase.
        """
        pi_s, pi_p = 1.0, 2.0
        energy_val = 0.3
        mu_p_val = 1.0
        mu_star = (pi_s * energy_val + pi_p * mu_p_val) / (pi_s + pi_p)  # ≈ 0.767

        model = Model(rng_seed=0, sigma_s=0.0, pi_s=pi_s, pi_p=pi_p,
                      kappa=0.5, mu_p_value=mu_p_val)
        model.energy = energy_val
        model.mu = 0.2  # start below fixed point

        dist_initial = abs(model.mu - mu_star)
        perception = make_perception(food=[])
        for _ in range(20):
            run_step(model, perception, action_name="stay")
            model.energy = energy_val  # hold energy fixed

        dist_final = abs(model.get_state()["mu"] - mu_star)
        assert dist_final < dist_initial, (
            f"mu did not approach fixed point: dist_initial={dist_initial:.4f}, dist_final={dist_final:.4f}"
        )


# ---------------------------------------------------------------------------
# B2: Agent preferentially eats when on food tile with low energy
# ---------------------------------------------------------------------------

class TestB2MovesTowardFood:
    """
    B2: When food is present at the agent's position and energy is low,
    eating minimizes predicted free energy (because eat has the highest
    predicted s_pred → lowest F_pred). The agent should strongly prefer eat.

    NOTE: The one-step lookahead predicts immediate sensory outcomes.
    When food IS at the current tile, eating predicts a large sensory gain
    (s_pred[eat] = s_t + energy_gain_eat), which greatly reduces eps_s².
    """

    def test_eats_when_on_food_tile_with_low_energy(self):
        """Agent on a food tile with low energy should strongly prefer eat."""
        random.seed(99)
        model = Model(rng_seed=99, beta=20.0, sigma_s=0.0)
        model.energy = 0.1
        model.mu = 0.1

        food = [{"x": 3, "y": 3, "palatability": 1.0}]
        eat_count = 0

        for _ in range(10):
            perception = make_perception(x=3, y=3, food=food)
            p_no_result = dict(perception)
            p_no_result["last_action_result"] = {}
            action = model.decide(p_no_result)
            if action.name == "eat":
                eat_count += 1
            model.update(action, 0.0, {**perception, "last_action_result": {"consumed": True, "palatability": 1.0}})

        assert eat_count > 0, "Agent never chose eat despite being hungry on food tile"

    def test_eat_has_lowest_predicted_free_energy_on_food_tile(self):
        """
        When food is at current position and mu is low (hungry), eat should
        have the lowest predicted free energy (= is the greedy-optimal action).
        """
        model = Model(sigma_s=0.0)
        model.energy = 0.15
        model.mu = 0.15  # hungry: far from mu_p=1.0

        # Initialize s_t by running one step
        perception = make_perception(x=2, y=2, food=[{"x": 2, "y": 2, "palatability": 1.0}])
        run_step(model, perception, action_name="stay")

        # After stay, check q_values: eat should have highest q (= lowest F_pred)
        q = model.get_state()["q_values"]
        # q_values[a] = -F_pred[a], so highest q = best action
        assert q["eat"] > q["stay"], (
            f"Eat q-value not higher than stay when hungry on food: eat={q['eat']:.4f}, stay={q['stay']:.4f}"
        )
        assert q["eat"] > q["move_up"], (
            f"Eat q-value not higher than move_up when hungry on food: eat={q['eat']:.4f}, move_up={q['move_up']:.4f}"
        )

    def test_move_toward_food_preferred_over_random_move(self):
        """
        When food is off-position, direction toward food should have lower
        F_pred (less energy loss predicted) than other move directions.
        """
        model = Model(sigma_s=0.0)
        model.energy = 0.3
        model.mu = 0.3

        # Food is to the right and below (move_right or move_down closer)
        food = [{"x": 7, "y": 7, "palatability": 1.0}]
        perception = make_perception(x=5, y=5, food=food)
        run_step(model, perception, action_name="stay")

        q = model.get_state()["q_values"]
        # The toward-food direction (move_right or move_down, equal dx=dy)
        # Both should beat move_left and move_up (away from food)
        toward_q = max(q["move_right"], q["move_down"])
        away_q = max(q["move_left"], q["move_up"])
        assert toward_q >= away_q, (
            f"Food-directed move not preferred: toward_q={toward_q:.6f}, away_q={away_q:.6f}"
        )


# ---------------------------------------------------------------------------
# B3: Agent does not urgently seek food when energy is high
# ---------------------------------------------------------------------------

class TestB3NoUrgencyWhenSated:
    """B3: Agent stays/wanders when energy is near setpoint (high)."""

    def test_few_move_toward_food_when_sated(self):
        """
        With energy=0.95 near setpoint=1.0, the agent should not take
        exclusively food-directed steps (move toward distant food every step).
        """
        random.seed(7)
        model = Model(rng_seed=7, beta=5.0, sigma_s=0.05)
        model.energy = 0.95
        model.mu = 0.95

        food = [{"x": 9, "y": 9, "palatability": 1.0}]
        agent_x, agent_y = 0, 0
        move_toward_count = 0

        for step in range(10):
            perception = make_perception(x=agent_x, y=agent_y, food=food, step=step)
            action = run_step(model, perception)

            # Check if this step moved toward (9,9) from current pos
            if action.name == "move_right":
                agent_x += 1
                move_toward_count += 1
            elif action.name == "move_down":
                agent_y += 1
                move_toward_count += 1
            elif action.name == "move_left":
                agent_x = max(0, agent_x - 1)
            elif action.name == "move_up":
                agent_y = max(0, agent_y - 1)

        # Sated agent should NOT be taking exclusively food-directed steps
        assert move_toward_count < 10, (
            f"Sated agent moved toward food all 10 steps — too urgent"
        )

    def test_free_energy_is_low_when_sated(self):
        """When energy ≈ mu_p, free energy should be small."""
        model = Model(sigma_s=0.0)
        model.energy = 0.95
        model.mu = 0.95

        perception = make_perception(food=[])
        run_step(model, perception, action_name="stay")

        state = model.get_state()
        # eps_p = mu - mu_p ≈ 0.95 - 1.0 = -0.05 → F should be small
        assert state["F"] < 0.5, f"Free energy too large when sated: F={state['F']:.4f}"

    def test_sated_agent_has_uniform_action_distribution(self):
        """
        When sated (energy ≈ mu_p), all actions have very similar (small) F_pred,
        so q_values should be close to each other — the agent is indifferent.
        The gap between best and worst action q-value should be small when sated.
        """
        model = Model(sigma_s=0.0, pi_p=2.0)
        model.energy = 0.98
        model.mu = 0.98  # Very close to mu_p=1.0

        food = [{"x": 9, "y": 9, "palatability": 1.0}]
        perception = make_perception(x=0, y=0, food=food)
        run_step(model, perception, action_name="stay")

        q = model.get_state()["q_values"]
        q_vals = list(q.values())
        q_range = max(q_vals) - min(q_vals)

        # Compare to a hungry agent
        model_hungry = Model(sigma_s=0.0, pi_p=2.0)
        model_hungry.energy = 0.1
        model_hungry.mu = 0.1
        run_step(model_hungry, perception, action_name="stay")
        q_hungry = model_hungry.get_state()["q_values"]
        q_hungry_vals = list(q_hungry.values())
        q_hungry_range = max(q_hungry_vals) - min(q_hungry_vals)

        # Sated agent should have smaller q_range (more indifferent) than hungry
        assert q_range <= q_hungry_range, (
            f"Sated agent should have smaller q-value spread than hungry: "
            f"sated_range={q_range:.6f}, hungry_range={q_hungry_range:.6f}"
        )


# ---------------------------------------------------------------------------
# B4: Higher pi_p increases urgency when energy is low
# ---------------------------------------------------------------------------

class TestB4HigherPrecisionMoreUrgent:
    """B4: Higher prior precision pi_p makes agent seek food faster when hungry."""

    def test_higher_pi_p_reaches_food_faster(self):
        """
        Two agents: pi_p=1.0 vs pi_p=4.0 both at energy=0.3, food at (5,0).
        High-pi_p agent should reach food in fewer steps on average.
        """
        food = [{"x": 5, "y": 0, "palatability": 1.0}]
        N_TRIALS = 15

        def steps_to_food(pi_p_val, seed):
            random.seed(seed)
            model = Model(rng_seed=seed, pi_p=pi_p_val, beta=8.0, sigma_s=0.05)
            model.energy = 0.3
            model.mu = 0.3
            ax, ay = 0, 0
            for s in range(50):
                perception = make_perception(x=ax, y=ay, food=food, step=s)
                action = run_step(model, perception)
                if action.name == "move_right":
                    ax += 1
                elif action.name == "move_left":
                    ax = max(0, ax - 1)
                elif action.name == "move_down":
                    ay += 1
                elif action.name == "move_up":
                    ay = max(0, ay - 1)
                if ax == 5 and ay == 0:
                    return s + 1
            return 50  # did not reach

        low_times = [steps_to_food(1.0, seed=s) for s in range(N_TRIALS)]
        high_times = [steps_to_food(4.0, seed=s) for s in range(N_TRIALS)]

        avg_low = sum(low_times) / N_TRIALS
        avg_high = sum(high_times) / N_TRIALS

        assert avg_high <= avg_low, (
            f"High pi_p agent was NOT faster: avg_low={avg_low:.2f}, avg_high={avg_high:.2f}"
        )

    def test_higher_pi_p_gives_higher_free_energy_gradient(self):
        """
        With higher pi_p, the prior prediction error term in F is stronger,
        resulting in a larger F when energy is low.
        """
        model_low = Model(sigma_s=0.0, pi_p=1.0)
        model_high = Model(sigma_s=0.0, pi_p=4.0)
        for m in (model_low, model_high):
            m.energy = 0.3
            m.mu = 0.3

        perception = make_perception(food=[])
        run_step(model_low, perception, action_name="stay")
        run_step(model_high, perception, action_name="stay")

        F_low = model_low.get_state()["F"]
        F_high = model_high.get_state()["F"]

        # Higher precision weights prior error more heavily → higher F when hungry
        assert F_high > F_low, (
            f"Higher pi_p should yield higher F when hungry: F_low={F_low:.4f}, F_high={F_high:.4f}"
        )


# ---------------------------------------------------------------------------
# B5: Free energy decreases after eating
# ---------------------------------------------------------------------------

class TestB5FreeEnergyDecreasesAfterEating:
    """B5: Successful eat reduces variational free energy."""

    def test_free_energy_drops_after_eat(self):
        """
        Record F before and after a successful eat action.
        F_after < F_before.
        """
        model = Model(sigma_s=0.0, rng_seed=0)
        model.energy = 0.3
        model.mu = 0.3

        food = [{"x": 2, "y": 2, "palatability": 1.0}]
        perception = make_perception(x=2, y=2, food=food)

        # Do one stay step to initialize s_t and F properly
        run_step(model, perception, action_name="stay")
        F_before = model.get_state()["F"]

        # Now eat
        eat_action = Action(name="eat")
        p_result = {**perception, "last_action_result": {"consumed": True, "palatability": 1.0}}
        model.update(eat_action, 1.0, p_result)
        F_after = model.get_state()["F"]

        assert F_after < F_before, (
            f"Free energy did NOT decrease after eating: "
            f"F_before={F_before:.6f}, F_after={F_after:.6f}"
        )

    def test_energy_increases_after_eat(self):
        """Energy level should increase after a consumed eat action."""
        model = Model(sigma_s=0.0, rng_seed=0)
        model.energy = 0.4

        food = [{"x": 1, "y": 1, "palatability": 1.0}]
        perception = make_perception(x=1, y=1, food=food)
        energy_before = model.energy

        eat_action = Action(name="eat")
        p_result = {**perception, "last_action_result": {"consumed": True, "palatability": 1.0}}
        model.update(eat_action, 1.0, p_result)

        assert model.energy > energy_before, (
            f"Energy did not increase after eating: before={energy_before}, after={model.energy}"
        )

    def test_eps_p_decreases_after_eating_when_hungry(self):
        """
        When agent is hungry (energy << mu_p), eating increases energy toward mu_p,
        which reduces |eps_p| after the belief update.
        """
        model = Model(sigma_s=0.0, rng_seed=0)
        model.energy = 0.2
        model.mu = 0.2

        perception = make_perception(x=3, y=3, food=[{"x": 3, "y": 3, "palatability": 1.0}])
        run_step(model, perception, action_name="stay")  # warm up
        eps_p_before = abs(model.get_state()["eps_p"])

        eat_action = Action(name="eat")
        p_result = {**perception, "last_action_result": {"consumed": True, "palatability": 1.0}}
        model.update(eat_action, 1.0, p_result)
        eps_p_after = abs(model.get_state()["eps_p"])

        assert eps_p_after <= eps_p_before, (
            f"|eps_p| should not increase after eating: before={eps_p_before:.4f}, after={eps_p_after:.4f}"
        )


# ---------------------------------------------------------------------------
# Structural / contract tests
# ---------------------------------------------------------------------------

class TestContractCompliance:
    """Verify the DecisionModel contract is correctly implemented."""

    def test_decide_returns_action(self):
        model = Model(rng_seed=0)
        perception = make_perception()
        action = model.decide(perception)
        assert isinstance(action, Action)
        assert action.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def test_get_state_keys(self):
        model = Model(rng_seed=0)
        state = model.get_state()
        for key in ("s_t", "mu", "mu_p", "eps_s", "eps_p", "F", "energy", "q_values"):
            assert key in state, f"Missing key in get_state: {key}"

    def test_q_values_all_actions(self):
        model = Model(rng_seed=0)
        perception = make_perception()
        model.update(Action(name="stay"), 0.0, perception)
        q = model.get_state()["q_values"]
        for a in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]:
            assert a in q, f"Missing action in q_values: {a}"

    def test_decide_does_not_mutate_state(self):
        """decide() must be read-only."""
        model = Model(rng_seed=42, sigma_s=0.0)
        model.energy = 0.5
        model.mu = 0.7
        perception = make_perception(food=[{"x": 5, "y": 5, "palatability": 1.0}])
        state_before = model.get_state()
        model.decide(perception)
        state_after = model.get_state()
        for key in ("mu", "energy", "F", "eps_s", "eps_p"):
            assert state_before[key] == state_after[key], (
                f"decide() mutated state[{key}]: {state_before[key]} → {state_after[key]}"
            )

    def test_update_modifies_state(self):
        """update() should change mu after perception update."""
        model = Model(rng_seed=1, sigma_s=0.0, kappa=0.5)
        model.energy = 0.3
        model.mu = 0.8
        perception = make_perception(food=[])
        mu_before = model.mu
        model.update(Action(name="stay"), 0.0, perception)
        assert model.mu != mu_before, "update() did not change mu"

    def test_no_external_imports(self):
        """Model file should only use stdlib."""
        with open(_MODEL_FILE) as f:
            source = f.read()
        forbidden = ["numpy", "scipy", "pandas", "torch", "tensorflow"]
        for pkg in forbidden:
            assert pkg not in source, f"Forbidden import found: {pkg}"

    def test_q_values_are_floats(self):
        """All q_values must be floats."""
        model = Model(rng_seed=0)
        perception = make_perception(food=[{"x": 5, "y": 5, "palatability": 1.0}])
        model.update(Action(name="stay"), 0.0, perception)
        q = model.get_state()["q_values"]
        for a, v in q.items():
            assert isinstance(v, float), f"q_values[{a}] is not float: {type(v)}"

    def test_energy_clamped_to_unit_interval(self):
        """Energy should never exceed [0, 1]."""
        model = Model(sigma_s=0.0)
        model.energy = 0.95

        # Eat many times to try to overflow
        food = [{"x": 0, "y": 0, "palatability": 1.0}]
        perception = make_perception(x=0, y=0, food=food)
        for _ in range(10):
            model.update(Action(name="eat"), 1.0,
                         {**perception, "last_action_result": {"consumed": True, "palatability": 1.0}})

        assert 0.0 <= model.energy <= 1.0, f"Energy out of range: {model.energy}"


# ---------------------------------------------------------------------------
# Run if executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
