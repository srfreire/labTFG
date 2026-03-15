"""
Proportional-Integral (PI) Negative-Feedback Controller
Formulation: homeostatic-regulation_pi_negative_feedback

A continuous-time ODE-inspired control agent that maintains an internal
energy variable via proportional and integral error correction.
Based on Gross et al. (2024), Drengstig et al. (2012), and npj Digital Medicine (2020).
"""

import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class HomeostaticPINegativeFeedback:
    """
    PI negative-feedback controller for homeostatic regulation.
    """

    def __init__(
        self,
        energy_set_point: float = 80.0,
        proportional_gain: float = 0.5,
        integral_gain: float = 0.05,
        passive_energy_decay: float = 1.0,
        energy_from_eating: float = 15.0,
        max_energy: float = 100.0,
        integral_windup_cap: float = 50.0,
    ):
        # Parameters
        self.s = energy_set_point
        self.k_P = proportional_gain
        self.k_I = integral_gain
        self.d = passive_energy_decay
        self.delta_eat = energy_from_eating
        self.A_max = max_energy
        self.c_I_max = integral_windup_cap

        # Variables (initial values from spec)
        self.A: float = 50.0
        self.e: float = self.s - self.A           # 30.0
        self.c_P: float = self.k_P * self.e       # 15.0
        self.c_I: float = 0.0
        self.c: float = self.c_P + self.c_I       # 15.0

        # Track last action for energy update in decide()
        self._last_action_name: str = 'stay'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clamp(self, value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        PI-controller driven action selection:
          1. Update energy (R5).
          2. Compute error, proportional, integral, total control (R1-R4).
          3. Select action based on control signal and food availability.
        """
        last_result = perception.get('last_action_result', {})
        consumed = last_result.get('consumed', False)
        ate = 1 if (self._last_action_name == 'eat' and consumed) else 0

        # R5: Energy dynamics
        self.A = self._clamp(
            self.A - self.d + self.delta_eat * ate,
            0.0,
            self.A_max
        )

        # R1: Error signal
        self.e = self.s - self.A

        # R2: Proportional control
        self.c_P = self.k_P * self.e

        # R3: Integral control with anti-windup
        self.c_I = self._clamp(
            self.c_I + self.k_I * self.e,
            -self.c_I_max,
            self.c_I_max
        )

        # R4: Total control signal
        self.c = self.c_P + self.c_I

        # Gather food positions from perception
        food_list = perception['resources'].get('food', [])
        food_positions = [(f['x'], f['y']) for f in food_list]
        pos = (perception['x'], perception['y'])
        food_at_position = pos in food_positions

        grid_width = perception.get('grid_width', 100)
        grid_height = perception.get('grid_height', 100)

        # Decision logic
        # If energy at or above set point: stay
        if self.e <= 0:
            return Action(name='stay')

        # If food at position and control signal positive: eat (R6)
        if food_at_position:
            U_eat = self.c  # c > 0 since e > 0
            if U_eat > 0:
                return Action(name='eat')

        # Move toward nearest food if any visible (R7)
        if food_positions:
            best_action = None
            best_utility = float('-inf')

            moves = [
                ('move_up',    (0, -1)),
                ('move_down',  (0,  1)),
                ('move_left',  (-1, 0)),
                ('move_right', (1,  0)),
            ]
            for action_name, (dx, dy) in moves:
                p_prime = (
                    self._clamp(pos[0] + dx, 0, grid_width - 1),
                    self._clamp(pos[1] + dy, 0, grid_height - 1),
                )
                min_dist = min(
                    abs(p_prime[0] - fx) + abs(p_prime[1] - fy)
                    for fx, fy in food_positions
                )
                U_move = self.c * (1.0 / (1 + min_dist))
                if U_move > best_utility:
                    best_utility = U_move
                    best_action = action_name
            return Action(name=best_action)

        # No food visible: random exploration (R8 / fallback)
        return Action(name=random.choice(['move_up', 'move_down', 'move_left', 'move_right']))

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Store the last action taken for use in the next decide() call."""
        self._last_action_name = action.name

    def get_state(self) -> dict:
        return {
            'energy': self.A,
            'error_signal': self.e,
            'proportional_control': self.c_P,
            'integral_control': self.c_I,
            'total_control_signal': self.c,
        }
