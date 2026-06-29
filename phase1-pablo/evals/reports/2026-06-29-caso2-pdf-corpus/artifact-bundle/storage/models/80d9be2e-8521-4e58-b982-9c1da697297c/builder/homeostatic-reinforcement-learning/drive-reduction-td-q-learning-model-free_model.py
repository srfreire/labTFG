"""
Drive-Reduction TD Q-Learning (Model-Free)
==========================================
Tabular Q-learning over a joint (grid-position × discretized-hunger) state space
where primary reward is defined as reduction in homeostatic drive.

Reference: Keramati & Gutkin (2014). Homeostatic reinforcement learning for
integrating reward collection and physiological stability. eLife 3:e04811.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# All available actions (index 5 = 'eat')
ALL_ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']
EAT_INDEX = 5


class DriveReductionTdQLearningModelFreeModel:
    """
    Model-free homeostatic RL agent using tabular Q-learning.

    State space: (position_tuple, hunger_bin)
    Reward:      drive reduction r_t = D(h_t) - D(h_{t+1})
    Policy:      softmax over Q-values, eating filtered when no food present
    """

    def __init__(
        self,
        drive_exponent: float = 2,
        drive_scaling: float = 1.0,
        discount_factor: float = 0.95,
        learning_rate: float = 0.1,
        softmax_inv_temperature: float = 5.0,
        setpoint: float = 0.0,
        max_hunger: float = 10.0,
        resource_nutritive_value: float = 3.0,
        metabolic_drift_rate: float = 0.1,
        hunger_discretization_bins: int = 10,
    ):
        # ---------- parameters ----------
        self.n = drive_exponent
        self.m = drive_scaling
        self.gamma = discount_factor
        self.alpha = learning_rate
        self.beta = softmax_inv_temperature
        self.h_star = setpoint
        self.h_max = max_hunger
        self.K = resource_nutritive_value
        self.lambda_drift = metabolic_drift_rate
        self.h_bins = hunger_discretization_bins

        # ---------- variables ----------
        self.h_t: float = 0.0              # hunger_level
        self.D_t: float = 0.0              # drive
        self.r_t: float = 0.0              # homeostatic_reward
        self.Q: dict = {}                  # q_table
        self.delta_t: float = 0.0          # hRPE
        self.s_t: tuple = (0, 0)           # external_state
        self.h_bin: int = 0                # hunger_bin
        self.ate_t: int = 0                # ate_food_flag

        # cached q_values for get_state() — updated in update()
        self._q_values: dict = {a: 0.0 for a in ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_drive(self, h: float) -> float:
        """D(h) = m * |h - h*|^n  (R1)"""
        return self.m * abs(h - self.h_star) ** self.n

    def _discretize_hunger(self, h: float) -> int:
        """h_bin = clamp(int(h / h_max * h_bins), 0, h_bins-1)  (R4)"""
        return min(int(h / self.h_max * self.h_bins), self.h_bins - 1)

    def _get_q(self, pos: tuple, hb: int, action_name: str) -> float:
        return self.Q.get((pos, hb, action_name), 0.0)

    def _max_q_next(self, pos_next: tuple, hb_next: int) -> float:
        return max(self._get_q(pos_next, hb_next, a) for a in ALL_ACTIONS)

    def _softmax_probs(self, q_vals: list) -> list:
        """Numerically stable softmax."""
        max_q = max(q_vals)
        exp_vals = [math.exp(self.beta * (q - max_q)) for q in q_vals]
        total = sum(exp_vals)
        return [e / total for e in exp_vals]

    def _food_at_position(self, x: int, y: int, resources: dict) -> bool:
        food_list = resources.get('food', [])
        return any(f['x'] == x and f['y'] == y for f in food_list)

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: select action based on current internal state + perception.

        Uses softmax over Q-values for the joint state (s_t, h_bin).
        Filters out 'eat' when no food is present at the agent's position.
        """
        x = perception['x']
        y = perception['y']
        s_t = (x, y)
        resources = perception.get('resources', {})

        food_here = self._food_at_position(x, y, resources)

        # Discretize current hunger (READ-ONLY from self.h_t)
        h_bin = self._discretize_hunger(self.h_t)

        # Gather Q-values for the current state
        q_vals = [self._get_q(s_t, h_bin, a) for a in ALL_ACTIONS]

        # Filter eat when no food present
        if not food_here:
            q_vals[EAT_INDEX] = -1e9

        # Softmax action selection
        probs = self._softmax_probs(q_vals)
        chosen = random.choices(ALL_ACTIONS, weights=probs, k=1)[0]

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: apply all rules and update internal state + Q-table.

        Updates: h_t, D_t, r_t, delta_t, h_bin, ate_t, Q, s_t, _q_values
        """
        action_name = action.name

        # --- read current state before update ---
        s_old = self.s_t
        h_old = self.h_t
        h_bin_old = self._discretize_hunger(h_old)

        # --- R2: determine ate_t from last_action_result ---
        last_result = new_perception.get('last_action_result', {})
        consumed = last_result.get('consumed', False)
        ate_t = 1 if (action_name == 'eat' and consumed) else 0
        self.ate_t = ate_t

        # --- R2: internal state dynamics ---
        h_next = min(max(h_old + self.lambda_drift - self.K * ate_t, 0.0), self.h_max)

        # --- R3: homeostatic reward (drive reduction) ---
        D_before = self._compute_drive(h_old)
        D_after = self._compute_drive(h_next)
        r_t = D_before - D_after

        # --- R4/R5: discretize next hunger, get next state position ---
        s_next = (new_perception['x'], new_perception['y'])
        h_bin_next = self._discretize_hunger(h_next)

        # --- R5: hRPE ---
        max_q_next = self._max_q_next(s_next, h_bin_next)
        q_old = self._get_q(s_old, h_bin_old, action_name)
        delta_t = r_t + self.gamma * max_q_next - q_old

        # --- R6: Q-table update ---
        self.Q[(s_old, h_bin_old, action_name)] = q_old + self.alpha * delta_t

        # --- Advance internal state variables ---
        self.h_t = h_next
        self.D_t = D_after
        self.r_t = r_t
        self.delta_t = delta_t
        self.s_t = s_next
        self.h_bin = h_bin_next

        # --- Cache q_values for new state (for get_state()) ---
        self._q_values = {
            a: self._get_q(s_next, h_bin_next, a) for a in ALL_ACTIONS
        }

    def get_state(self) -> dict:
        return {
            'hunger_level': self.h_t,
            'homeostatic_setpoint': self.h_star,
            'drive': self.D_t,
            'homeostatic_reward': self.r_t,
            'q_table_size': len(self.Q),
            'hRPE': self.delta_t,
            'external_state': self.s_t,
            'hunger_bin': self.h_bin,
            'ate_food_flag': self.ate_t,
            'q_values': dict(self._q_values),
        }
