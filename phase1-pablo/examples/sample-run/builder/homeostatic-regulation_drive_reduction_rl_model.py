"""
Homeostatic Reinforcement Learning (Drive-Reduction MDP)
Formulation: homeostatic-regulation_drive_reduction_rl

Tabular Q-learning agent where reward is redefined as drive reduction —
the decrease in a quadratic discomfort function measuring deviation from
a homeostatic set point. Based on Keramati & Gutkin (2011).
"""

import math
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


ALL_ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']


def _compass_direction(dx: float, dy: float) -> str:
    """Convert dx,dy offset to one of N/NE/E/SE/S/SW/W/NW/here."""
    if dx == 0 and dy == 0:
        return 'here'
    angle = math.degrees(math.atan2(dy, dx))  # E=0°, N=-90°, S=90°
    # Map angle to 8 compass directions + here
    # We treat +y as south (grid coords), so angle from atan2(dy,dx):
    #   dx>0,dy=0 => E; dx=0,dy>0 => S; dx<0,dy=0 => W; dx=0,dy<0 => N
    if angle < -157.5 or angle >= 157.5:
        return 'W'
    elif angle < -112.5:
        return 'NW'
    elif angle < -67.5:
        return 'N'
    elif angle < -22.5:
        return 'NE'
    elif angle < 22.5:
        return 'E'
    elif angle < 67.5:
        return 'SE'
    elif angle < 112.5:
        return 'S'
    else:
        return 'SW'


class HomeostaticDriveReductionRL:
    """
    Homeostatic RL agent using tabular Q-learning with drive-reduction reward.
    """

    def __init__(
        self,
        energy_set_point: float = 80.0,
        drive_weight: float = 1.0,
        max_energy: float = 100.0,
        passive_energy_decay: float = 1.0,
        energy_from_eating: float = 15.0,
        td_learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        softmax_inv_temperature: float = 5.0,
        energy_discretization_bins: int = 10,
    ):
        # Parameters
        self.s = energy_set_point
        self.phi = drive_weight
        self.x_max = max_energy
        self.d = passive_energy_decay
        self.delta_eat = energy_from_eating
        self.alpha = td_learning_rate
        self.gamma = discount_factor
        self.beta = softmax_inv_temperature
        self.n_bins = energy_discretization_bins

        # Variables
        self.x: float = 50.0
        self.D: float = self.phi * (self.x - self.s) ** 2
        self.r: float = 0.0
        self.Q: dict = defaultdict(float)
        self.z: tuple = (5, 'none')
        self.x_prev: float = 50.0
        self.z_prev: tuple = None   # None until first update
        self.a_prev: str = 'stay'

        # Internal flag: whether decide has been called at least once
        self._first_step: bool = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clamp(self, value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def _discretize_state(self, x: float, food_list: list, pos: tuple) -> tuple:
        """Compute discretized state (energy_bin, direction)."""
        energy_bin = min(int(x * self.n_bins / self.x_max), self.n_bins - 1)
        if not food_list:
            direction = 'none'
        else:
            nearest = min(
                food_list,
                key=lambda f: abs(f['x'] - pos[0]) + abs(f['y'] - pos[1])
            )
            dx_f = nearest['x'] - pos[0]
            dy_f = nearest['y'] - pos[1]
            direction = _compass_direction(dx_f, dy_f)
        return (energy_bin, direction)

    def _softmax_action(self, z: tuple, food_at_position: bool) -> str:
        """Select an action via Boltzmann softmax over Q-values."""
        q_vals = {}
        for a in ALL_ACTIONS:
            if a == 'eat' and not food_at_position:
                q_vals[a] = float('-inf')
            else:
                q_vals[a] = self.Q[(z, a)]

        finite_vals = [v for v in q_vals.values() if v != float('-inf')]
        if not finite_vals:
            # All actions masked (shouldn't happen in practice)
            return random.choice(ALL_ACTIONS)

        max_q = max(finite_vals)
        exp_vals = {}
        for a, v in q_vals.items():
            if v == float('-inf'):
                exp_vals[a] = 0.0
            else:
                exp_vals[a] = math.exp(self.beta * (v - max_q))

        total = sum(exp_vals.values())
        probs = {a: ev / total for a, ev in exp_vals.items()}
        actions_list = list(probs.keys())
        weights = [probs[a] for a in actions_list]
        return random.choices(actions_list, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Main decision step:
          1. Update energy from last action result.
          2. Compute drive-reduction reward.
          3. Discretize current state.
          4. TD update on Q-table for previous (state, action).
          5. Select action via softmax.
        """
        last_result = perception.get('last_action_result', {})
        consumed = last_result.get('consumed', False)
        ate = 1 if (self.a_prev == 'eat' and consumed) else 0

        # R1: Energy dynamics
        self.x = self._clamp(self.x - self.d + self.delta_eat * ate, 0.0, self.x_max)

        # R2 & R3: Drive and reward
        D_prev = self.phi * (self.x_prev - self.s) ** 2
        D_curr = self.phi * (self.x - self.s) ** 2
        self.D = D_curr
        self.r = D_prev - D_curr

        # R4: State discretization
        food_list = perception['resources'].get('food', [])
        pos = (perception['x'], perception['y'])
        food_at_position = any(
            f['x'] == pos[0] and f['y'] == pos[1] for f in food_list
        )
        self.z = self._discretize_state(self.x, food_list, pos)

        # R5 & R6: TD update (skip very first step before any action stored)
        if self.z_prev is not None:
            best_future = max(self.Q[(self.z, a)] for a in ALL_ACTIONS)
            delta = self.r + self.gamma * best_future - self.Q[(self.z_prev, self.a_prev)]
            self.Q[(self.z_prev, self.a_prev)] += self.alpha * delta

        # R7: Softmax action selection
        selected = self._softmax_action(self.z, food_at_position)

        # Store state for next TD update
        self.x_prev = self.x
        self.z_prev = self.z
        # a_prev will be set in update()

        self._first_step = False
        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Store the action taken for use in the next TD update."""
        self.a_prev = action.name

    def get_state(self) -> dict:
        return {
            'energy': self.x,
            'drive': self.D,
            'reward': self.r,
            'q_table': dict(self.Q),
            'discretized_state': self.z,
            'previous_energy': self.x_prev,
            'previous_state': self.z_prev,
            'previous_action': self.a_prev,
        }
