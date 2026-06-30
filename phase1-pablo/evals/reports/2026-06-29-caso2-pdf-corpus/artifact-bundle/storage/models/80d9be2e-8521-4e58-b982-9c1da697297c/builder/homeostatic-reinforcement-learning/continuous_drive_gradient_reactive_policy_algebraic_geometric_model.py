"""
Continuous Drive-Gradient Reactive Policy (Algebraic/Geometric)
Paradigm: homeostatic-reinforcement-learning
Formulation: continuous-drive-gradient-reactive-policy-algebraic-geometric

Memoryless reactive policy based on:
- Keramati & Gutkin (2014) homeostatic RL postulates P1 and P4
- Hull (1943) drive-reduction theory
- Cabanac (1971) alliesthesia (drive-weighted proximity utility)
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class ContinuousDriveGradientReactivePolicyAlgebraicGeometricModel:
    """
    Reactive (memoryless) homeostatic agent that selects actions by computing
    one-step-ahead drive-reduction utilities for each candidate action.

    No Q-table or learned values are maintained. Utilities are computed
    analytically each step from the current hunger level and resource positions.
    """

    def __init__(
        self,
        n: float = 2,
        m: float = 1.0,
        K: float = 3.0,
        lambda_drift: float = 0.1,
        h_star: float = 0.0,
        h_max: float = 10.0,
        w_prox: float = 0.5,
        beta: float = 5.0,
        eta: float = 0.5,
    ):
        # Parameters
        self.n = n
        self.m = m
        self.K = K
        self.lambda_drift = lambda_drift
        self.h_star = h_star
        self.h_max = h_max
        self.w_prox = w_prox
        self.beta = beta
        self.eta = eta

        # State variables
        self.h_t: float = 0.0           # hunger_level
        self.homeostatic_setpoint: float = 0.0  # h_star (fixed)
        self.D_t: float = 0.0           # current drive
        self.position: tuple = (0, 0)   # s_t
        self.resource_positions: list = []  # R
        self.nearest_food_distance: int = 0  # d_nearest
        self.action_utility: float = 0.0    # U_a
        self.eat_drive_reduction: float = 0.0  # delta_D_eat
        self.proximity_gain: int = 0       # Prox_a
        self.ate_food_flag: int = 0        # ate_t

        # q_values: utility score for each action (updated in update())
        self.q_values: dict = {
            "move_up": 0.0,
            "move_down": 0.0,
            "move_left": 0.0,
            "move_right": 0.0,
            "stay": 0.0,
            "eat": 0.0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _drive(self, h: float) -> float:
        """D(h) = m * |h - h_star|^n   (Rule R1)"""
        return self.m * abs(h - self.h_star) ** self.n

    def _clip(self, value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def _d_nearest(self, pos: tuple, resources: list, grid_w: int, grid_h: int) -> int:
        """Manhattan distance from pos to nearest food resource (Rule R3)."""
        if not resources:
            return grid_w + grid_h
        return min(abs(pos[0] - r[0]) + abs(pos[1] - r[1]) for r in resources)

    def _compute_utilities(self, perception: dict) -> tuple:
        """
        Compute one-step-ahead utilities for all candidate actions.
        Pure computation — does NOT modify self.
        Returns (utilities_dict, D_t, d_current, R).
        """
        x = perception["x"]
        y = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception["resources"].get("food", [])
        R = [(f["x"], f["y"]) for f in food_list]
        food_at_position = (x, y) in R

        # Current drive (R1)
        D_t = self._drive(self.h_t)

        # Nearest food distance from current position
        d_current = self._d_nearest((x, y), R, grid_w, grid_h)

        utilities = {}

        # Movement actions (R3, R4) — drive-weighted proximity gain
        delta_map = {
            "move_up":    (0, -1),
            "move_down":  (0,  1),
            "move_left":  (-1, 0),
            "move_right": (1,  0),
        }
        for action_name, (dx, dy) in delta_map.items():
            new_x = self._clip(x + dx, 0, grid_w - 1)
            new_y = self._clip(y + dy, 0, grid_h - 1)
            d_after = self._d_nearest((new_x, new_y), R, grid_w, grid_h)
            prox_a = d_current - d_after  # positive = getting closer
            utilities[action_name] = self.w_prox * D_t * prox_a  # R4

        # Stay (R6) — always incurs metabolic drift cost
        D_after_stay = self._drive(self.h_t + self.lambda_drift)
        utilities["stay"] = -(D_after_stay - D_t)

        # Eat (R2, R5) — gated by satiation threshold
        if food_at_position and D_t > self.eta:
            h_after_eat = self._clip(self.h_t + self.lambda_drift - self.K, 0.0, self.h_max)
            D_after_eat = self._drive(h_after_eat)
            utilities["eat"] = D_t - D_after_eat   # delta_D_eat
        else:
            utilities["eat"] = -1e9

        return utilities, D_t, d_current, R

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: compute utilities and sample action via softmax (R7).
        Does NOT modify any state.
        """
        utilities, _, _, _ = self._compute_utilities(perception)

        all_actions = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
        u_vals = [utilities[a] for a in all_actions]

        # Softmax (R7) — numerically stable via max-shift
        max_u = max(u_vals)
        exp_vals = [math.exp(self.beta * (u - max_u)) for u in u_vals]
        sum_exp = sum(exp_vals)
        probs = [e / sum_exp for e in exp_vals]

        chosen = random.choices(all_actions, weights=probs, k=1)[0]
        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: apply all rules (R8 + state refresh).
        Updates hunger, drive, position, resource cache, and q_values.
        """
        last_result = new_perception.get("last_action_result", {})

        # ate_t: successful food consumption flag (R8)
        self.ate_food_flag = 1 if (
            action.name == "eat" and last_result.get("consumed", False)
        ) else 0

        # Update hunger (R8): metabolic drift ± consumption
        self.h_t = self._clip(
            self.h_t + self.lambda_drift - self.K * self.ate_food_flag,
            0.0,
            self.h_max,
        )

        # Refresh position and resource cache from new_perception
        self.position = (new_perception["x"], new_perception["y"])
        food_list = new_perception["resources"].get("food", [])
        self.resource_positions = [(f["x"], f["y"]) for f in food_list]
        grid_w = new_perception["grid_width"]
        grid_h = new_perception["grid_height"]
        self.nearest_food_distance = self._d_nearest(
            self.position, self.resource_positions, grid_w, grid_h
        )

        # Recompute current drive (R1)
        self.D_t = self._drive(self.h_t)

        # Update q_values (utilities) from new_perception for get_state() readout
        utilities, _, _, _ = self._compute_utilities(new_perception)
        for a in self.q_values:
            self.q_values[a] = utilities[a]

    def get_state(self) -> dict:
        return {
            "hunger_level": self.h_t,
            "homeostatic_setpoint": self.homeostatic_setpoint,
            "drive": self.D_t,
            "position": self.position,
            "resource_positions": self.resource_positions,
            "nearest_food_distance": self.nearest_food_distance,
            "action_utility": self.action_utility,
            "eat_drive_reduction": self.eat_drive_reduction,
            "proximity_gain": self.proximity_gain,
            "ate_food_flag": self.ate_food_flag,
            "q_values": self.q_values,
        }
