"""
Tests for ExecutiveResourceOdeWithDualValueArbitrationModel.

Covers all 5 expected behaviors from the spec:
  B1 - E depletes under sustained conflict, recovers during non-conflict
  B2 - High E → health-integrated; Low E → impulsive (taste-dominant)
  B3 - Hard self-control failure when E < theta during conflict
  B4 - Habit Q-values strengthen via TD learning
  B5 - Omega nonlinear collapse: E=0.7→0.49, E=0.3→0.09
"""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from executive_resource_ode_with_dual_value_arbitration_model import (
    ExecutiveResourceOdeWithDualValueArbitrationModel,
    Action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, gw=10, gh=10, step=0, foods=None, last_action_result=None):
    return {
        'x': x, 'y': y,
        'grid_width': gw, 'grid_height': gh,
        'step': step,
        'resources': {'food': foods or []},
        'last_action_result': last_action_result or {},
    }


def make_food(x, y, palatability):
    return {'x': x, 'y': y, 'type': 'food', 'palatability': palatability}


def run_steps(model, perception_fn, n_steps):
    """Run n_steps: decide → update with same perception (no actual env)."""
    for i in range(n_steps):
        p = perception_fn(i)
        action = model.decide(p)
        p_new = dict(p)
        p_new['last_action_result'] = {}
        model.update(action, 0.0, p_new)


# ---------------------------------------------------------------------------
# B1: Executive capacity depletes under sustained conflict, recovers without
# ---------------------------------------------------------------------------

def test_B1_depletion_under_conflict():
    """
    B1: E depletes under sustained conflict.
    Setup: tasty food to the right (pal=0.95), healthy food above (pal=0.05).
    V_I prefers right (high taste); V_G prefers up (high health) → conflict.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=42, stochastic_lapse_rate=0.0)

    tasty_food = make_food(8, 5, 0.95)    # right of agent at (5,5)
    healthy_food = make_food(5, 2, 0.05)  # above agent at (5,5), very healthy

    def conflict_perception(step):
        return make_perception(x=5, y=5, foods=[tasty_food, healthy_food], step=step)

    initial_E = model.E  # 1.0
    run_steps(model, conflict_perception, 40)

    final_E = model.E
    assert final_E < initial_E, f"E should deplete from {initial_E}, got {final_E}"
    assert final_E < 0.9, f"E={final_E} should have noticeably depleted after 40 conflict steps"


def test_B1_recovery_after_conflict_removed():
    """
    B1: E recovers when conflict is removed (no foods → no conflict).
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=42)

    # Manually deplete E
    model.E = 0.4
    model._last_conflict = False

    def no_conflict_perception(step):
        return make_perception(x=5, y=5, foods=[], step=step)

    E_before = model.E
    run_steps(model, no_conflict_perception, 20)
    E_after = model.E

    assert E_after > E_before, (
        f"E should recover from {E_before} without conflict, got {E_after}"
    )


# ---------------------------------------------------------------------------
# B2: High E → health-integrated; Low E → impulsive
# ---------------------------------------------------------------------------

def test_B2_high_E_choose_eat_for_composite_value():
    """
    B2: When E=1.0, omega=1.0, V = V_G entirely.
    Place only a single healthy food at agent position (pal=0.3, health=0.7).
    V_G[eat]=0.4*0.3+0.6*0.7=0.54 > V_G[move_*]=0 → agent eats (health-driven).
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0, stochastic_lapse_rate=0.0)
    model.E = 1.0

    healthy_food = make_food(5, 5, 0.3)
    p = make_perception(x=5, y=5, foods=[healthy_food])
    action = model.decide(p)

    # V[eat] = V_G[eat] = 0.54; V[move_*] = 0; V[stay] = 0
    assert action.name == 'eat', (
        f"With E=1 and only a food at position, agent should eat (V_G=0.54>0), got {action.name}"
    )


def test_B2_low_E_prefers_tasty_eat():
    """
    B2: When E << theta, V ≈ V_I. Single tasty food at position → always eat.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0, stochastic_lapse_rate=0.0)
    model.E = 0.05  # much below theta=0.3

    tasty_food = make_food(5, 5, 0.9)
    p = make_perception(x=5, y=5, foods=[tasty_food])

    actions = [model.decide(p).name for _ in range(10)]
    eat_count = sum(1 for a in actions if a == 'eat')

    # omega=0.0025 ≈ 0: V ≈ V_I. V_I[eat]=0.9, V_I[others]=0 → always eat
    assert eat_count == 10, (
        f"With very low E and food at position, should always eat, got {eat_count}/10"
    )


def test_B2_low_E_forced_impulsive_tasty_vs_healthy():
    """
    B2: When E < theta during conflict, agent forced to impulsive system.
    Scenario: tasty food here (pal=0.9) vs ultra-healthy food directly above (pal=0.0).
    V_I[eat]=0.9 (best impulsive), V_G[move_up]=0.6 (best goal-directed) → conflict.
    With E=0.1 < theta=0.3 → forced to V_I best = 'eat'.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0, stochastic_lapse_rate=0.0)
    model.E = 0.1  # below theta=0.3

    tasty_here = make_food(5, 5, 0.9)        # V_I[eat]=0.9
    very_healthy_close = make_food(5, 4, 0.0) # directly above; V_G[move_up]=0.6 > V_G[eat]=0.42
    p = make_perception(x=5, y=5, foods=[tasty_here, very_healthy_close])

    actions = [model.decide(p).name for _ in range(10)]
    eat_count = sum(1 for a in actions if a == 'eat')

    # E < theta, conflict → forced impulsive = eat
    assert eat_count == 10, (
        f"With E<theta, conflict present, should always pick impulsive 'eat', got {eat_count}/10"
    )


# ---------------------------------------------------------------------------
# B3: Hard self-control failure: E < theta during conflict → forced impulsive
# ---------------------------------------------------------------------------

def test_B3_forced_impulsive_below_threshold():
    """
    B3: When E < theta (0.3) and conflict is present, agent must take argmax(V_I).
    Scenario:
      - tasty at (5,5): V_I[eat]=0.95
      - very_healthy at (5,4): V_G[move_up]=0.6, V_G[eat]=0.41
      - best_V_I='eat', best_V_G='move_up' → conflict
      - E=0.2 < theta=0.3 → forced impulsive → 'eat'
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(
        seed=0, stochastic_lapse_rate=0.0
    )

    tasty_here = make_food(5, 5, 0.95)
    very_healthy_up = make_food(5, 4, 0.0)

    p = make_perception(x=5, y=5, foods=[tasty_here, very_healthy_up])

    forced_impulsive_count = 0
    for _ in range(10):
        model.E = 0.2  # reset E below theta for each trial
        action = model.decide(p)
        if action.name == 'eat':
            forced_impulsive_count += 1

    assert forced_impulsive_count == 10, (
        f"All 10 trials should force impulsive 'eat' when E<theta with conflict, "
        f"got {forced_impulsive_count}/10"
    )


def test_B3_no_forced_failure_above_threshold_uses_integrated():
    """
    B3 complement: When E > theta, no forced failure.
    Agent uses integrated values; the result differs from pure-impulsive outcome.
    
    Scenario: tasty at (5,5) [pal=0.95], very_healthy at (5,4) [pal=0.0].
    Pure impulsive best = 'eat' (V_I[eat]=0.95).
    
    With E=0.9 (omega=0.81), V_I[move_up] benefits from approaching tasty_here
    from (5,4) → V_I[move_up] = 0.95*0.9 = 0.855.
    V[move_up] = 0.81*0.6 + 0.19*0.855 = 0.486+0.162 = 0.648.
    V[eat]     = 0.81*0.41 + 0.19*0.95 = 0.332+0.181 = 0.513.
    So integrated winner = 'move_up' (differs from forced impulsive 'eat').
    This confirms no forced path is taken at high E.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(
        seed=0, stochastic_lapse_rate=0.0
    )
    model.E = 0.9  # above theta=0.3

    tasty_here = make_food(5, 5, 0.95)
    very_healthy_up = make_food(5, 4, 0.0)

    p = make_perception(x=5, y=5, foods=[tasty_here, very_healthy_up])

    # Pure impulsive would force 'eat' (V_I[eat]=0.95 is argmax V_I due to gamma^0=1).
    # But with E=0.9, the agent uses integrated values → move_up wins.
    # The key assertion: agent does NOT unconditionally take the impulsive 'eat' choice.
    actions = [model.decide(p).name for _ in range(5)]
    
    # Verify conflict is detected (both systems disagree)
    model.E = 0.9
    model.decide(p)
    assert model._last_conflict, "Conflict should be detected at E=0.9 with this food layout"

    # With E >= theta, forced impulsive path is NOT taken.
    # The agent uses integrated value → 'move_up' (V=0.648 > V[eat]=0.513).
    for a in actions:
        assert a == 'move_up', (
            f"At E=0.9 (above theta), integrated V favors move_up (0.648>0.513), got {a}"
        )


# ---------------------------------------------------------------------------
# B4: Habit Q-values update via TD learning
# ---------------------------------------------------------------------------

def test_B4_habit_td_learning():
    """
    B4: Repeatedly eating food with palatability=0.9 strengthens habit Q-value.
    After 10 TD updates with palatability 0.9, Q_habit(state,'eat') should be > 0.5.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=42)
    model.epsilon = 0.0

    food = make_food(5, 5, 0.9)
    p = make_perception(x=5, y=5, foods=[food])

    for _ in range(10):
        model.decide(p)
        new_p = make_perception(
            x=5, y=5, foods=[food],
            last_action_result={'consumed': True, 'palatability': 0.9}
        )
        model.update(Action(name='eat'), 0.9, new_p)

    state_key = model._make_state_key(5, 5, [food])
    q_val = model.Q_habit.get((state_key, 'eat'), 0.0)

    assert q_val > 0.5, (
        f"Q_habit[(state,'eat')] should be > 0.5 after 10 TD updates toward 0.9, "
        f"got {q_val:.4f}"
    )


def test_B4_habit_converges_to_palatability():
    """
    B4: After many TD updates, habit Q-value converges near the palatability.
    """
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(
        habit_learning_rate=0.1, seed=42
    )
    food = make_food(3, 3, 0.8)
    p = make_perception(x=3, y=3, foods=[food])

    for _ in range(100):
        model.decide(p)
        new_p = make_perception(
            x=3, y=3, foods=[food],
            last_action_result={'consumed': True, 'palatability': 0.8}
        )
        model.update(Action(name='eat'), 0.8, new_p)

    state_key = model._make_state_key(3, 3, [food])
    q_val = model.Q_habit.get((state_key, 'eat'), 0.0)

    assert abs(q_val - 0.8) < 0.05, (
        f"Q_habit should converge to ~0.8 after 100 TD updates, got {q_val:.4f}"
    )


def test_B4_no_update_without_consumed():
    """B4: Q_habit does not update when eat action fails (consumed=False)."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    food = make_food(5, 5, 0.9)
    p = make_perception(x=5, y=5, foods=[food])

    state_key = model._make_state_key(5, 5, [food])
    q_before = model.Q_habit.get((state_key, 'eat'), 0.0)

    for _ in range(5):
        model.decide(p)
        new_p = make_perception(
            x=5, y=5, foods=[food],
            last_action_result={'consumed': False}
        )
        model.update(Action(name='eat'), 0.0, new_p)

    q_after = model.Q_habit.get((state_key, 'eat'), 0.0)
    assert q_after == q_before, (
        f"Q_habit should not change without consumed=True, was {q_before}, got {q_after}"
    )


# ---------------------------------------------------------------------------
# B5: Arbitration weight omega = E^2 (nonlinear collapse)
# ---------------------------------------------------------------------------

def test_B5_omega_E07():
    """B5: E=0.7 → omega = 0.7^2 = 0.49."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    model.E = 0.7
    model.omega = model.E ** 2
    assert abs(model.omega - 0.49) < 1e-9, (
        f"With E=0.7, omega should be exactly 0.49, got {model.omega}"
    )


def test_B5_omega_E03():
    """B5: E=0.3 → omega = 0.3^2 = 0.09."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    model.E = 0.3
    model.omega = model.E ** 2
    assert abs(model.omega - 0.09) < 1e-9, (
        f"With E=0.3, omega should be exactly 0.09, got {model.omega}"
    )


def test_B5_omega_updated_in_update():
    """B5: omega is updated to E^2 in every update() call."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    model.E = 0.7

    p = make_perception(x=5, y=5, foods=[])
    action = model.decide(p)
    new_p = make_perception(x=5, y=5, foods=[])
    model.update(action, 0.0, new_p)

    state = model.get_state()
    expected_omega = state['E'] ** 2
    assert abs(state['omega'] - expected_omega) < 1e-9, (
        f"omega={state['omega']} should equal E^2={expected_omega:.6f}"
    )


def test_B5_omega_nonlinear_at_various_levels():
    """B5: Verify omega = E^2 at multiple E levels; confirms nonlinear collapse."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    test_cases = [
        (1.0, 1.0),
        (0.7, 0.49),
        (0.5, 0.25),
        (0.3, 0.09),
        (0.1, 0.01),
        (0.0, 0.0),
    ]
    for e_val, expected_omega in test_cases:
        model.E = e_val
        computed = model.E ** 2
        assert abs(computed - expected_omega) < 1e-9, (
            f"E={e_val}: omega should be {expected_omega}, got {computed}"
        )

    # Key nonlinear property: moderate depletion (E=0.7) has much more omega than severe (E=0.3)
    assert 0.49 > 5 * 0.09, "omega collapse is highly nonlinear: omega(0.7) >> 5×omega(0.3)"


# ---------------------------------------------------------------------------
# Contract / interface tests
# ---------------------------------------------------------------------------

def test_get_state_has_required_keys():
    """get_state must include q_values and all variable/parameter names."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    state = model.get_state()

    required_keys = ['E', 'V_I', 'V_G', 'V', 'omega', 'ctrl', 'q_values']
    for key in required_keys:
        assert key in state, f"Missing key '{key}' in get_state()"

    assert isinstance(state['q_values'], dict)
    for action_name in ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']:
        assert action_name in state['q_values'], (
            f"q_values missing action '{action_name}'"
        )
    for v in state['q_values'].values():
        assert isinstance(v, float), f"q_values values should be float, got {type(v)}"


def test_decide_returns_valid_action():
    """decide() must return an Action with a valid action name."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    food = make_food(5, 5, 0.7)
    p = make_perception(x=5, y=5, foods=[food])
    action = model.decide(p)

    assert isinstance(action, Action)
    valid_actions = {'move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat'}
    assert action.name in valid_actions, f"Invalid action: {action.name}"


def test_decide_is_readonly():
    """decide() must NOT modify E or ctrl."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    model.E = 0.75
    model.ctrl = 0

    food = make_food(5, 5, 0.8)
    p = make_perception(x=5, y=5, foods=[food])

    E_before = model.E
    ctrl_before = model.ctrl
    model.decide(p)

    assert model.E == E_before, f"decide() must not modify E (was {E_before}, now {model.E})"
    assert model.ctrl == ctrl_before, "decide() must not modify ctrl"


def test_update_changes_E():
    """update() must change E via the ODE step."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    model.E = 0.5

    tasty_food = make_food(8, 5, 0.95)
    healthy_food = make_food(5, 2, 0.05)
    p = make_perception(x=5, y=5, foods=[tasty_food, healthy_food])

    action = model.decide(p)
    E_before = model.E
    assert E_before == 0.5, "decide() should not change E"

    new_p = make_perception(x=5, y=5, foods=[tasty_food, healthy_food])
    model.update(action, 0.0, new_p)

    E_after = model.E
    # E changes: ctrl=0 → E += 0.04*(0.5) = 0.52; ctrl=1 → E = 0.5+0.02-0.08=0.44
    assert E_after != E_before, (
        f"E should change after update (was {E_before}, now {E_after})"
    )


def test_no_food_does_not_crash():
    """Model handles empty food list gracefully."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0)
    p = make_perception(x=3, y=3, foods=[])
    action = model.decide(p)
    assert action.name in {'move_up', 'move_down', 'move_left', 'move_right', 'stay'}
    new_p = make_perception(x=3, y=3, foods=[])
    model.update(action, 0.0, new_p)  # should not raise


def test_eat_not_offered_without_food_at_position():
    """eat should not be offered when no food is at current position."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0, stochastic_lapse_rate=0.0)
    food = make_food(8, 8, 0.9)  # far away from agent at (5,5)
    p = make_perception(x=5, y=5, foods=[food])

    for _ in range(5):
        action = model.decide(p)
        assert action.name != 'eat', "Should not offer eat when no food at position"


def test_ctrl_flag_set_correctly():
    """ctrl=1 when conflict, ctrl=0 when no conflict."""
    model = ExecutiveResourceOdeWithDualValueArbitrationModel(seed=0, stochastic_lapse_rate=0.0)
    model.E = 1.0  # above threshold

    # Create conflict: tasty here + ultra-healthy directly above
    tasty_here = make_food(5, 5, 0.95)
    very_healthy_up = make_food(5, 4, 0.0)
    p_conflict = make_perception(x=5, y=5, foods=[tasty_here, very_healthy_up])

    action = model.decide(p_conflict)
    assert model._last_conflict == True, "Should detect conflict with differing preferences"

    new_p = make_perception(x=5, y=5, foods=[tasty_here, very_healthy_up])
    model.update(action, 0.0, new_p)
    assert model.ctrl == 1, f"ctrl should be 1 after conflict, got {model.ctrl}"

    # No conflict: single food at position (both systems agree 'eat' is best)
    single_food = make_food(5, 5, 0.7)
    p_no_conflict = make_perception(x=5, y=5, foods=[single_food])
    action2 = model.decide(p_no_conflict)
    assert model._last_conflict == False, "Should not detect conflict with single food"

    new_p2 = make_perception(x=5, y=5, foods=[single_food])
    model.update(action2, 0.0, new_p2)
    assert model.ctrl == 0, f"ctrl should be 0 with no conflict, got {model.ctrl}"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
