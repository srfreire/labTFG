"""
Rescorla–Wagner Cached-Value Agent with Softmax Action Selection
Paradigm: Pavlovian Control of Food Approach

A Pavlovian agent that learns cached state values V(s) for each grid cell via
the Rescorla–Wagner (TD(0)) prediction-error rule, then selects actions
stochastically via softmax over hunger-modulated Pavlovian action values.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class RescorlawagnerCachedValueAgentWithSoftmaxActionSelectionModel:
    """
    Rescorla–Wagner Cached-Value Agent with Softmax Action Selection.

    Variables:
      V          - pavlovian_state_values: dict[(x,y) -> float]
      delta_t    - reward_prediction_error: float
      h_t        - hunger_level: float (0..1)
      r_t        - reward_received: float
      Q_Pav      - pavlovian_action_values: dict[str -> float]
      P_a        - action_probabilities: dict[str -> float]

    Parameters:
      alpha      - learning_rate (default 0.15)
      beta       - inverse_temperature (default 5.0)
      r_food     - food_reward_magnitude (default 1.0)
      alpha_h    - hunger_increment_rate (default 0.02)
      gamma_sat  - satiation_decrement (default 0.20)
      mu         - hunger_value_gain (default 1.5)
      c_step     - movement_cost (default 0.01)
      R_max      - maximum_value (default 2.0)
    """

    ACTION_NAMES = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def __init__(
        self,
        alpha: float = 0.15,
        beta: float = 5.0,
        r_food: float = 1.0,
        alpha_h: float = 0.02,
        gamma_sat: float = 0.20,
        mu: float = 1.5,
        c_step: float = 0.01,
        R_max: float = 2.0,
    ):
        # Parameters
        self.alpha = alpha
        self.beta = beta
        self.r_food = r_food
        self.alpha_h = alpha_h
        self.gamma_sat = gamma_sat
        self.mu = mu
        self.c_step = c_step
        self.R_max = R_max

        # Variables
        self.V: dict = {}               # pavlovian_state_values
        self.delta_t: float = 0.0      # reward_prediction_error
        self.h_t: float = 0.5          # hunger_level
        self.r_t: float = 0.0          # reward_received
        self.Q_Pav: dict = {a: 0.0 for a in self.ACTION_NAMES}   # pavlovian_action_values
        self.P_a: dict = {a: 1.0 / len(self.ACTION_NAMES) for a in self.ACTION_NAMES}  # action_probabilities

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clip(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def _compute_qpav(self, perception: dict) -> dict:
        """Compute hunger-modulated Pavlovian action values (R4)."""
        x = perception["x"]
        y = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception.get("resources", {}).get("food", [])
        food_positions = set((f["x"], f["y"]) for f in food_list)
        food_at_position = (x, y) in food_positions

        pos = (x, y)
        destinations = {
            "move_up":    (x, y - 1),
            "move_down":  (x, y + 1),
            "move_left":  (x - 1, y),
            "move_right": (x + 1, y),
            "stay":       pos,
            "eat":        pos,
        }

        Q_Pav = {}
        for action_name, dest in destinations.items():
            if action_name == "eat":
                if food_at_position:
                    Q_Pav["eat"] = self.mu * self.h_t * self.V.get(pos, 0.0)
                else:
                    Q_Pav["eat"] = -1e9
            elif action_name == "stay":
                Q_Pav["stay"] = self.mu * self.h_t * self.V.get(pos, 0.0)
            else:
                dx, dy = dest
                if 0 <= dx < grid_w and 0 <= dy < grid_h:
                    Q_Pav[action_name] = self.mu * self.h_t * self.V.get(dest, 0.0) - self.c_step
                else:
                    Q_Pav[action_name] = -1e9
        return Q_Pav

    def _softmax(self, Q_Pav: dict) -> dict:
        """Compute numerically stable softmax probabilities (R5)."""
        max_q = max(Q_Pav.values())
        exp_vals = {a: math.exp(self.beta * (q - max_q)) for a, q in Q_Pav.items()}
        Z = sum(exp_vals.values())
        return {a: v / Z for a, v in exp_vals.items()}

    # ------------------------------------------------------------------
    # DecisionModel contract
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: Compute Q_Pav and softmax probabilities from current state,
        then sample an action. No state mutation.
        """
        Q_Pav = self._compute_qpav(perception)
        P_a = self._softmax(Q_Pav)

        actions = list(P_a.keys())
        weights = [P_a[a] for a in actions]

        # random.choices uses cumulative weights; equivalent to weighted sample
        selected = random.choices(actions, weights=weights, k=1)[0]
        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: Apply all rules (R1–R5) and update internal state.
        Called after the action has been executed by the environment.
        """
        x = new_perception["x"]
        y = new_perception["y"]
        pos = (x, y)

        # r_t: the actual reward received this step
        self.r_t = reward

        # R1: Reward prediction error
        self.delta_t = self.r_t - self.V.get(pos, 0.0)

        # R2: Pavlovian value update (Rescorla–Wagner / TD(0))
        current_v = self.V.get(pos, 0.0)
        self.V[pos] = self._clip(current_v + self.alpha * self.delta_t, 0.0, self.R_max)

        # R3: Hunger dynamics
        last_result = new_perception.get("last_action_result", {})
        eat_succeeded = (
            action.name == "eat"
            and bool(last_result.get("consumed", False))
        )
        ate = 1.0 if eat_succeeded else 0.0
        self.h_t = self._clip(self.h_t + self.alpha_h - self.gamma_sat * ate, 0.0, 1.0)

        # R4 + R5: Recompute Q_Pav and P_a based on new_perception (cache for get_state)
        self.Q_Pav = self._compute_qpav(new_perception)
        self.P_a = self._softmax(self.Q_Pav)

    def get_state(self) -> dict:
        """Return a snapshot of all internal state, including q_values."""
        return {
            "pavlovian_state_values": dict(self.V),
            "reward_prediction_error": self.delta_t,
            "hunger_level": self.h_t,
            "reward_received": self.r_t,
            "pavlovian_action_values": dict(self.Q_Pav),
            "action_probabilities": dict(self.P_a),
            # q_values: flat dict required by simulation infrastructure
            "q_values": dict(self.Q_Pav),
        }
