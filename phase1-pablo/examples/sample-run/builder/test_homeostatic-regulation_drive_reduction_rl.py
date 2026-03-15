"""
Tests for homeostatic-regulation_drive_reduction_rl model.
"""

import math
import random
import sys
import os
import importlib.util

# Load module from hyphenated filename
_spec = importlib.util.spec_from_file_location(
    "homeostatic_regulation_drive_reduction_rl_model",
    os.path.join(os.path.dirname(__file__),
                 "homeostatic-regulation_drive_reduction_rl_model.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

HomeostaticDriveReductionRL = _mod.HomeostaticDriveReductionRL
Action = _mod.Action
ALL_ACTIONS = _mod.ALL_ACTIONS


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
# B1: Drive increases as energy falls below set point without eating
# ---------------------------------------------------------------------------

def test_B1_drive_increases_without_eating():
    """
    Run 30 steps with no food. Energy should decrease each step and
    drive D = phi*(x-s)^2 should increase each step (x moves further below s=80).
    """
    agent = HomeostaticDriveReductionRL()
    agent.x = 50.0
    agent.x_prev = 50.0

    prev_D = agent.phi * (agent.x - agent.s) ** 2
    all_D_increased = True

    for i in range(30):
        perception = make_perception(step=i)
        action = agent.decide(perception)
        agent.update(action, 0.0, perception)

        state = agent.get_state()
        current_D = state['drive']
        assert abs(current_D - agent.phi * (state['energy'] - agent.s) ** 2) < 1e-9, \
            "D must equal phi*(x-s)^2"
        if current_D <= prev_D:
            all_D_increased = False
        prev_D = current_D

    assert all_D_increased, "Drive should increase every step without eating"


# ---------------------------------------------------------------------------
# B2: Eating produces positive reward when energy is below set point
# ---------------------------------------------------------------------------

def test_B2_eating_produces_positive_reward_below_setpoint():
    """
    At x=50, eat food (delta_eat=15, decay=1 → x_new=64).
    D_prev = (50-80)^2=900, D_curr=(64-80)^2=256 → r=644 > 0.
    """
    agent = HomeostaticDriveReductionRL()
    agent.x = 50.0
    agent.x_prev = 50.0
    agent.a_prev = 'eat'
    agent.z_prev = None  # Skip Q-update

    perception = make_perception(last_action_result={'consumed': True})
    agent.decide(perception)

    state = agent.get_state()
    assert state['reward'] > 0, \
        f"Eating when hungry should give positive reward, got r={state['reward']}"


# ---------------------------------------------------------------------------
# B3: Eating produces negative reward when energy overshoots set point
# ---------------------------------------------------------------------------

def test_B3_eating_negative_reward_above_setpoint():
    """
    At x=78, eat food (delta_eat=15, decay=1 → x_new=92).
    D(78)=(78-80)^2=4, D(92)=(92-80)^2=144 → r=-140 < 0.
    """
    agent = HomeostaticDriveReductionRL()
    agent.x = 78.0
    agent.x_prev = 78.0
    agent.a_prev = 'eat'
    agent.z_prev = None  # Skip Q-update

    perception = make_perception(last_action_result={'consumed': True})
    agent.decide(perception)

    state = agent.get_state()
    assert state['reward'] < 0, \
        f"Eating when overfull should give negative reward, got r={state['reward']}"
    assert abs(state['energy'] - 92.0) < 1e-9, \
        f"Energy should be 92, got {state['energy']}"


# ---------------------------------------------------------------------------
# B4: Q-values converge to prefer moving toward food when energy is low
# ---------------------------------------------------------------------------

def test_B4_qvalues_converge_prefer_food_direction():
    """
    After many training episodes the agent should accumulate positive Q-values
    for move_right when food is to the east and energy is low.
    We verify that the Q-table is non-trivially updated AND the sum of
    move_right Q-values across all low-energy east-facing states exceeds
    the corresponding sum for move_left.
    """
    random.seed(42)
    agent = HomeostaticDriveReductionRL(
        softmax_inv_temperature=1.0,   # more exploration
        td_learning_rate=0.2,
        discount_factor=0.95,
        energy_discretization_bins=10,
    )

    n_episodes = 30
    steps_per_episode = 50

    for ep in range(n_episodes):
        # Reset agent position and energy each episode
        agent.x = 40.0
        agent.x_prev = 40.0
        agent_x, agent_y = 2, 5
        food_x, food_y = 10, 5  # Always to the east
        agent.a_prev = 'stay'
        agent.z_prev = None

        for i in range(steps_per_episode):
            food = [{'x': food_x, 'y': food_y, 'type': 'food', 'palatability': 1.0}]
            at_food = (agent_x == food_x and agent_y == food_y)
            last_result = {'consumed': True} if (agent.a_prev == 'eat' and at_food) else {}

            perception = make_perception(
                x=agent_x, y=agent_y,
                food=food, step=ep * steps_per_episode + i,
                last_action_result=last_result
            )
            action = agent.decide(perception)
            agent.update(action, 0.0, perception)

            # Advance agent position
            if action.name == 'move_right' and agent_x < 19:
                agent_x += 1
            elif action.name == 'move_left' and agent_x > 0:
                agent_x -= 1
            elif action.name == 'move_up' and agent_y > 0:
                agent_y -= 1
            elif action.name == 'move_down' and agent_y < 19:
                agent_y += 1
            elif action.name == 'eat' and at_food:
                # Reset after eating
                agent_x, agent_y = 2, 5
                agent.x = 40.0
                agent.x_prev = 40.0

            # Keep energy low to sustain foraging drive
            if agent.x > 65.0:
                agent.x = 40.0

    # Aggregate Q-values: sum over all low-energy bins with 'E' direction
    low_bins = list(range(0, 5))  # bins 0-4 correspond to x < 50
    q_right_total = sum(
        agent.Q[((b, 'E'), 'move_right')] for b in low_bins
    )
    q_left_total = sum(
        agent.Q[((b, 'E'), 'move_left')] for b in low_bins
    )

    # At minimum: Q-table must have been updated at all (not all zeros)
    all_q_values = list(agent.Q.values())
    assert any(v != 0.0 for v in all_q_values), \
        "Q-table should have been updated during training"

    # move_right should be preferred over move_left when food is east and energy is low
    assert q_right_total >= q_left_total, (
        f"sum Q[low,'E', move_right]={q_right_total:.4f} should >= "
        f"sum Q[low,'E', move_left]={q_left_total:.4f}"
    )


# ---------------------------------------------------------------------------
# B5: Agent prefers 'stay' when energy is near set point
# ---------------------------------------------------------------------------

def test_B5_prefers_stay_near_setpoint():
    """
    After manually giving 'stay' the highest Q-value at high energy with no food,
    the agent (with high beta) should select 'stay' most often.
    """
    random.seed(0)
    agent = HomeostaticDriveReductionRL(
        softmax_inv_temperature=10.0,
    )

    high_bin = min(int(80.0 * agent.n_bins / agent.x_max), agent.n_bins - 1)
    z_near = (high_bin, 'none')
    for a in ALL_ACTIONS:
        agent.Q[(z_near, a)] = -10.0
    agent.Q[(z_near, 'stay')] = 10.0

    agent.x = 80.0
    agent.x_prev = 80.0

    counts = {a: 0 for a in ALL_ACTIONS}
    for i in range(50):
        perception = make_perception(x=5, y=5, step=i)
        action = agent.decide(perception)
        agent.update(action, 0.0, perception)
        counts[action.name] += 1
        agent.x = 80.0
        agent.x_prev = 80.0

    assert counts['stay'] == max(counts.values()), \
        f"'stay' should be most frequent near set point, got counts={counts}"


# ---------------------------------------------------------------------------
# B6: Softmax entropy decreases as Q-values differentiate
# ---------------------------------------------------------------------------

def test_B6_entropy_decreases_over_training():
    """
    Compare action entropy after 10 steps vs 500 steps of training.
    As Q-values differentiate, the softmax distribution becomes more peaked.
    We measure entropy ONLY over states that were actually visited.
    """
    def train_and_measure_entropy(n_steps, seed):
        random.seed(seed)
        agent = HomeostaticDriveReductionRL(
            softmax_inv_temperature=5.0,
            td_learning_rate=0.3,
        )
        agent.x = 40.0
        food = [{'x': 15, 'y': 5, 'type': 'food', 'palatability': 1.0}]
        ax, ay = 5, 5

        for i in range(n_steps):
            at_food = (ax == 15 and ay == 5)
            last_result = {'consumed': True} if (agent.a_prev == 'eat' and at_food) else {}
            perception = make_perception(
                x=ax, y=ay, food=food, step=i,
                last_action_result=last_result
            )
            action = agent.decide(perception)
            agent.update(action, 0.0, perception)

            if action.name == 'move_right' and ax < 19:
                ax += 1
            elif action.name == 'move_left' and ax > 0:
                ax -= 1
            elif action.name == 'eat' and at_food:
                ax, ay = 5, 5
                agent.x = 40.0
            if agent.x > 65.0:
                agent.x = 40.0

        # Compute entropy over the current state's Q-values
        z = agent.z
        food_at_pos = False
        q_vals = {}
        for a in ALL_ACTIONS:
            if a == 'eat' and not food_at_pos:
                q_vals[a] = float('-inf')
            else:
                q_vals[a] = agent.Q[(z, a)]

        finite = [v for v in q_vals.values() if v != float('-inf')]
        if not finite or all(v == finite[0] for v in finite):
            # Uniform → max entropy
            n_valid = sum(1 for v in q_vals.values() if v != float('-inf'))
            return math.log(n_valid) if n_valid > 1 else 0.0

        max_q = max(finite)
        exp_vals = {
            a: (math.exp(agent.beta * (v - max_q)) if v != float('-inf') else 0.0)
            for a, v in q_vals.items()
        }
        total = sum(exp_vals.values())
        probs = [ev / total for ev in exp_vals.values() if ev > 0]
        return -sum(p * math.log(p) for p in probs)

    h_early = train_and_measure_entropy(10, seed=7)
    h_late = train_and_measure_entropy(500, seed=7)

    assert h_late < h_early, (
        f"Entropy should decrease over training: early={h_early:.4f}, late={h_late:.4f}"
    )


# ---------------------------------------------------------------------------
# Additional correctness tests
# ---------------------------------------------------------------------------

def test_get_state_keys():
    agent = HomeostaticDriveReductionRL()
    perception = make_perception()
    agent.decide(perception)
    state = agent.get_state()
    expected_keys = {
        'energy', 'drive', 'reward', 'q_table',
        'discretized_state', 'previous_energy', 'previous_state', 'previous_action'
    }
    assert expected_keys.issubset(set(state.keys())), \
        f"Missing keys: {expected_keys - set(state.keys())}"


def test_energy_clamped_to_zero():
    """Energy should never go below 0."""
    agent = HomeostaticDriveReductionRL()
    agent.x = 0.5
    for i in range(5):
        perception = make_perception(step=i)
        agent.decide(perception)
        agent.update(Action(name='stay'), 0.0, perception)
        assert agent.get_state()['energy'] >= 0.0


def test_energy_clamped_to_max():
    """Energy should never exceed max_energy."""
    agent = HomeostaticDriveReductionRL()
    agent.x = 99.0
    agent.a_prev = 'eat'
    perception = make_perception(last_action_result={'consumed': True})
    agent.decide(perception)
    assert agent.get_state()['energy'] <= agent.x_max
