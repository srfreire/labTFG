"""
Drive-Reduction ODE with Goal-Directed Valuation
=================================================
A continuous-time homeostatic ODE system (discretized to grid steps) that couples
an internal energy store to a sigmoid hunger drive, which modulates multi-attribute
food valuation. Deterministic argmax action selection over analytically computed
action values.

References:
  - Jacquier (2016) energy-balance ODEs
  - Rangel (2013) multi-attribute value computation (P1, P3, P6)
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class DriveReductionOdeWithGoalDirectedValuationModel:
    """
    DecisionModel implementing drive-reduction ODE + goal-directed multi-attribute
    food valuation.

    Variables
    ---------
    E  : energy_store          — normalized internal energy reserve [0, 1]
    H  : hunger_drive          — sigmoid of energy deficit [0, 1]
    w_c: caloric_weight        — equals H
    w_e: effort_weight         — equals 1 - H
    d  : resource_distance     — Manhattan distance to nearest food
    ate: ate_flag              — 1 if ate on previous step, else 0

    Parameters
    ----------
    alpha_E : basal_metabolic_cost      (default 0.01)
    c_food  : energy_gain_from_eating   (default 0.3)
    E_set   : energy_set_point          (default 0.5)
    k_H     : hunger_sensitivity        (default 4.0)
    r_food  : base_food_reward          (default 1.0)
    c_step  : step_cost                 (default -0.05)
    theta   : eat_threshold             (default 0.3)
    """

    # All recognized action names
    MOVE_ACTIONS = ["move_up", "move_down", "move_left", "move_right"]
    ALL_ACTIONS = MOVE_ACTIONS + ["eat", "stay"]

    def __init__(
        self,
        alpha_E: float = 0.01,
        c_food: float = 0.3,
        E_set: float = 0.5,
        k_H: float = 4.0,
        r_food: float = 1.0,
        c_step: float = -0.05,
        theta: float = 0.3,
    ):
        # Parameters
        self.alpha_E = alpha_E
        self.c_food = c_food
        self.E_set = E_set
        self.k_H = k_H
        self.r_food = r_food
        self.c_step = c_step
        self.theta = theta

        # State variables
        self.E: float = 0.5          # energy_store
        self.H: float = 0.5          # hunger_drive
        self.w_c: float = 0.5        # caloric_weight
        self.w_e: float = 0.5        # effort_weight
        self.d: int = 0              # resource_distance
        self.ate: int = 0            # ate_flag

        # Q-values (action scores) — initialized to zero
        self.q_values: dict = {a: 0.0 for a in self.ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _manhattan(x1: int, y1: int, x2: int, y2: int) -> int:
        return abs(x1 - x2) + abs(y1 - y2)

    def _nearest_food_distance(
        self, x: int, y: int, food_list: list, grid_width: int, grid_height: int
    ) -> int:
        """Return Manhattan distance to the nearest food item, or max grid distance if none."""
        if not food_list:
            return grid_width + grid_height
        return min(self._manhattan(x, y, f["x"], f["y"]) for f in food_list)

    @staticmethod
    def _apply_move(
        x: int, y: int, action: str, grid_width: int, grid_height: int
    ):
        """Return (new_x, new_y) after applying a move action, clamped to grid bounds."""
        nx, ny = x, y
        if action == "move_up":
            ny = max(0, y - 1)
        elif action == "move_down":
            ny = min(grid_height - 1, y + 1)
        elif action == "move_left":
            nx = max(0, x - 1)
        elif action == "move_right":
            nx = min(grid_width - 1, x + 1)
        return nx, ny

    def _sigmoid_hunger(self, E: float) -> float:
        """H = 1 / (1 + exp(-k_H * (E_set - E)))  (R2)"""
        return 1.0 / (1.0 + math.exp(-self.k_H * (self.E_set - E)))

    def _compute_action_values(
        self,
        x: int,
        y: int,
        grid_width: int,
        grid_height: int,
        food_list: list,
    ) -> dict:
        """
        Compute action value V for every candidate action.

        R4: V_eat = w_c * r_food * H                               (if on food & H >= theta)
        R5: V_move_a = w_c * r_food * H / (1 + d_after) + c_step * w_e
        R6: V_stay = 0.0
        """
        values: dict = {}

        food_at_cell = any(
            f["x"] == x and f["y"] == y for f in food_list
        )

        # --- eat ---
        if food_at_cell:
            if self.H >= self.theta:
                values["eat"] = self.w_c * self.r_food * self.H  # R4
            else:
                values["eat"] = 0.0  # below meal-initiation threshold

        # --- move actions ---
        for move_action in self.MOVE_ACTIONS:
            nx, ny = self._apply_move(x, y, move_action, grid_width, grid_height)
            d_after = self._nearest_food_distance(nx, ny, food_list, grid_width, grid_height)
            values[move_action] = (
                self.w_c * self.r_food * self.H / (1.0 + d_after)
                + self.c_step * self.w_e
            )  # R5

        # --- stay ---
        values["stay"] = 0.0  # R6

        return values

    # ------------------------------------------------------------------
    # Public DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: select action based on current internal state and perception.
        All state mutations happen in update().
        """
        x: int = perception["x"]
        y: int = perception["y"]
        grid_width: int = perception["grid_width"]
        grid_height: int = perception["grid_height"]
        food_list: list = perception.get("resources", {}).get("food", [])

        action_values = self._compute_action_values(
            x, y, grid_width, grid_height, food_list
        )

        # Argmax with random tiebreak
        max_val = max(action_values.values())
        best_actions = [a for a, v in action_values.items() if v == max_val]
        chosen = random.choice(best_actions)

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply ALL rules and state updates:
          R1: Update E (energy dynamics)
          R2: Recompute H (hunger drive)
          R3: Recompute w_c, w_e (attribute weights)
          Also refresh q_values, d, ate from new_perception.
        """
        # --- Extract ate_flag from last_action_result ---
        last_result = new_perception.get("last_action_result", {})
        # Eating succeeded if action was "eat" and result shows consumption
        if action.name == "eat":
            # Check various possible keys indicating success
            consumed = (
                last_result.get("consumed", False)
                or last_result.get("success", False)
                or last_result.get("ate", False)
                or reward > 0
            )
            self.ate = 1 if consumed else 0
        else:
            self.ate = 0

        # R1: Energy dynamics
        self.E = self._clamp(
            self.E - self.alpha_E + self.c_food * self.ate, 0.0, 1.0
        )

        # R2: Hunger drive
        self.H = self._sigmoid_hunger(self.E)

        # R3: Attribute weights
        self.w_c = self.H
        self.w_e = 1.0 - self.H

        # Update resource_distance from new_perception
        x: int = new_perception["x"]
        y: int = new_perception["y"]
        grid_width: int = new_perception["grid_width"]
        grid_height: int = new_perception["grid_height"]
        food_list: list = new_perception.get("resources", {}).get("food", [])

        self.d = self._nearest_food_distance(x, y, food_list, grid_width, grid_height)

        # Refresh q_values using updated state and new_perception
        action_values = self._compute_action_values(
            x, y, grid_width, grid_height, food_list
        )
        # Populate all action slots (default 0 for actions not in action_values)
        for a in self.ALL_ACTIONS:
            self.q_values[a] = action_values.get(a, 0.0)

    def get_state(self) -> dict:
        return {
            "E": self.E,
            "H": self.H,
            "w_c": self.w_c,
            "w_e": self.w_e,
            "d": self.d,
            "ate": self.ate,
            "q_values": dict(self.q_values),
        }
