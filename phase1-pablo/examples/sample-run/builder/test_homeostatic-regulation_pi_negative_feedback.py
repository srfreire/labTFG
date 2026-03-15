"""
Tests for homeostatic-regulation_pi_negative_feedback model.
"""

import sys
import os
import random
import importlib.util

# Load module from hyphenated filename
_spec = importlib.util.spec_from_file_location(
    "homeostatic_regulation_pi_negative_feedback_model",
    os.path.join(os.path.dirname(__file__),
                 "homeostatic-regulation_pi_negative_feedback_model.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

HomeostaticPINegativeFeedback = _mod.HomeostaticPINegativeFeedback
Action = _mod.Action


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_perception(x=5, y=5, grid_width=20, grid_height=20, step=0,
                    food=None, last_action_result=None):
    return {
        'x': x,
        'y': y,
        'grid_width': grid_width,
        'grid_height': grid_height,
        'step': step,
        'resources': {'food': food if food is not None else []},
        'last_action_result': last_action_result if last_action_result is not None else {},
    }


# ---------------------------------------------------------------------------
# B1: Energy decays without eating, error grows, control signal grows
# ---------------------------------------------------------------------------

def test_B1_energy_decays_error_grows():
    """
    Run 20 steps without food. A decreases each step, e increases, c increases.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 60.0

    prev_A = agent.A
    prev_e = agent.s - agent.A
    prev_c = agent.k_P * prev_e + agent.c_I

    for i in range(20):
        perception = make_perception(step=i)
        action = agent.decide(perception)
        agent.update(action, 0.0, perception)

        state = agent.get_state()
        A = state['energy']
        e = state['error_signal']
        c = state['total_control_signal']

        assert A < prev_A, f"Step {i}: energy should decrease, got {A} >= {prev_A}"
        assert e > prev_e, f"Step {i}: error should increase, got {e} <= {prev_e}"
        assert c > prev_c, f"Step {i}: control should increase, got {c} <= {prev_c}"

        prev_A = A
        prev_e = e
        prev_c = c


# ---------------------------------------------------------------------------
# B2: Agent eats when food is at its position and energy is below set point
# ---------------------------------------------------------------------------

def test_B2_eats_when_food_at_position_and_hungry():
    """
    Place food at agent position with A < s → action should be 'eat'.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 50.0  # Below set point 80

    food = [{'x': 5, 'y': 5, 'type': 'food', 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)
    action = agent.decide(perception)

    assert action.name == 'eat', \
        f"Agent should eat when food is at position and hungry, got '{action.name}'"


# ---------------------------------------------------------------------------
# B3: Agent stays put when energy is at or above set point
# ---------------------------------------------------------------------------

def test_B3_stays_when_energy_at_setpoint():
    """
    Set A so that after decay it remains >= s → action should be 'stay'.
    decay=1.0, so set A=86 → after decay A=85 > s=80.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 86.0  # After decay: 85 > 80

    perception = make_perception(x=5, y=5)
    action = agent.decide(perception)

    assert action.name == 'stay', \
        f"Agent should stay when energy >= set point, got '{action.name}'"


def test_B3_stays_when_energy_above_setpoint_no_decay():
    """
    Set A very high so even after decay it is above set point.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 95.0  # After decay: 94 > 80

    perception = make_perception(x=5, y=5)
    action = agent.decide(perception)

    assert action.name == 'stay', \
        f"Agent should stay when energy is high, got '{action.name}'"


# ---------------------------------------------------------------------------
# B4: Integral term accumulates during prolonged deficit
# ---------------------------------------------------------------------------

def test_B4_integral_accumulates_during_deficit():
    """
    Run 50 steps with A < s. c_I should be > 0 and non-decreasing.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 50.0  # Well below set point
    agent.c_I = 0.0

    prev_c_I = 0.0
    for i in range(50):
        perception = make_perception(step=i)
        action = agent.decide(perception)
        agent.update(action, 0.0, perception)

        state = agent.get_state()
        c_I = state['integral_control']
        assert c_I > 0, f"Step {i}: c_I should be > 0 during deficit, got {c_I}"
        assert c_I >= prev_c_I, \
            f"Step {i}: c_I should be non-decreasing, got {c_I} < {prev_c_I}"
        prev_c_I = c_I


# ---------------------------------------------------------------------------
# B5: Agent moves toward nearest food when hungry and food is visible
# ---------------------------------------------------------------------------

def test_B5_moves_toward_food_to_the_right():
    """
    Place food 3 cells to the right, A < s → agent should select 'move_right'.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 50.0  # Below set point

    # Food at (8, 5), agent at (5, 5) → food is 3 cells to the right
    food = [{'x': 8, 'y': 5, 'type': 'food', 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)
    action = agent.decide(perception)

    assert action.name == 'move_right', \
        f"Agent should move right toward food, got '{action.name}'"


def test_B5_moves_toward_food_directly_above():
    """
    Food is 3 cells above the agent (lower y) → agent should move_up.
    """
    agent = HomeostaticPINegativeFeedback()
    agent.A = 50.0

    # Food at (5, 2), agent at (5, 5) → dy=-3
    food = [{'x': 5, 'y': 2, 'type': 'food', 'palatability': 1.0}]
    perception = make_perception(x=5, y=5, food=food)
    action = agent.decide(perception)

    assert action.name == 'move_up', \
        f"Agent should move up toward food, got '{action.name}'"


# ---------------------------------------------------------------------------
# B6: Agent explores randomly when hungry but no food is visible
# ---------------------------------------------------------------------------

def test_B6_explores_randomly_no_food():
    """
    A < s with no food → action is one of move_up/down/left/right.
    """
    random.seed(0)
    agent = HomeostaticPINegativeFeedback()
    agent.A = 40.0

    valid_moves = {'move_up', 'move_down', 'move_left', 'move_right'}
    for _ in range(20):
        perception = make_perception(x=5, y=5, food=[])
        action = agent.decide(perception)
        agent.update(action, 0.0, perception)
        assert action.name in valid_moves, \
            f"Agent should explore randomly with no food, got '{action.name}'"


# ---------------------------------------------------------------------------
# Additional correctness tests
# ---------------------------------------------------------------------------

def test_error_formula():
    """e = s - A is computed correctly after decide()."""
    agent = HomeostaticPINegativeFeedback()
    agent.A = 70.0
    perception = make_perception()
    agent.decide(perception)
    state = agent.get_state()
    # After decide: A = 70 - 1 = 69, e = 80 - 69 = 11
    assert abs(state['error_signal'] - (agent.s - state['energy'])) < 1e-9


def test_proportional_control_formula():
    """c_P = k_P * e is computed correctly."""
    agent = HomeostaticPINegativeFeedback()
    agent.A = 70.0
    perception = make_perception()
    agent.decide(perception)
    state = agent.get_state()
    assert abs(state['proportional_control'] - agent.k_P * state['error_signal']) < 1e-9


def test_energy_increases_when_eating():
    """Energy increases by delta_eat - d when eating successfully."""
    agent = HomeostaticPINegativeFeedback()
    agent.A = 50.0
    agent._last_action_name = 'eat'

    perception = make_perception(
        x=5, y=5,
        food=[{'x': 5, 'y': 5, 'type': 'food', 'palatability': 1.0}],
        last_action_result={'consumed': True}
    )
    agent.decide(perception)
    state = agent.get_state()
    expected = min(50.0 - agent.d + agent.delta_eat, agent.A_max)
    assert abs(state['energy'] - expected) < 1e-9, \
        f"Energy after eating should be {expected}, got {state['energy']}"


def test_integral_windup_cap():
    """Integral term should not exceed c_I_max."""
    agent = HomeostaticPINegativeFeedback()
    agent.A = 0.0  # Maximum error
    for i in range(1000):
        perception = make_perception(step=i)
        agent.decide(perception)
        agent.update(Action(name='stay'), 0.0, perception)
        state = agent.get_state()
        assert state['integral_control'] <= agent.c_I_max, \
            f"c_I exceeded windup cap: {state['integral_control']}"


def test_get_state_keys():
    """get_state should return all required variable keys."""
    agent = HomeostaticPINegativeFeedback()
    perception = make_perception()
    agent.decide(perception)
    state = agent.get_state()
    expected_keys = {
        'energy', 'error_signal', 'proportional_control',
        'integral_control', 'total_control_signal'
    }
    assert expected_keys.issubset(set(state.keys())), \
        f"Missing keys: {expected_keys - set(state.keys())}"


def test_energy_never_negative():
    """Energy should never go below 0."""
    agent = HomeostaticPINegativeFeedback()
    agent.A = 0.5
    for i in range(10):
        perception = make_perception(step=i)
        agent.decide(perception)
        agent.update(Action(name='stay'), 0.0, perception)
        assert agent.get_state()['energy'] >= 0.0


def test_eating_increases_energy_more_than_no_eating():
    """After successful eat action, energy should be higher than without eating."""
    agent_eat = HomeostaticPINegativeFeedback()
    agent_eat.A = 50.0
    agent_no_eat = HomeostaticPINegativeFeedback()
    agent_no_eat.A = 50.0

    agent_eat._last_action_name = 'eat'
    p_eat = make_perception(last_action_result={'consumed': True})
    agent_eat.decide(p_eat)

    p_no = make_perception(last_action_result={})
    agent_no_eat.decide(p_no)

    assert agent_eat.get_state()['energy'] > agent_no_eat.get_state()['energy']
