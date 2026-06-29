"""
Dual-Controller Competition with Pavlovian Override
====================================================
Three-system architecture:
  1. Goal-directed controller  (model-based, hunger-sensitive)
  2. Habitual controller       (model-free Q-learning, hunger-insensitive)
  3. Pavlovian override        (cue-driven eat response when food at cell)

Arbitration weight omega shifts from goal-directed → habitual as eating
experience accumulates. The Pavlovian system injects a fixed probability of
eating whenever food is present at the agent's cell.

Reference: Rangel (2013) Postulates P5 & P6; Jacquier (2016) energy dynamics.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _manhattan(ax: int, ay: int, bx: int, by: int) -> float:
    return float(abs(ax - bx) + abs(ay - by))


def _nearest_food(x: int, y: int, food_list: list) -> Any:
    """Return the food dict closest (Manhattan) to (x, y), or None."""
    if not food_list:
        return None
    return min(food_list, key=lambda f: _manhattan(x, y, f["x"], f["y"]))


def _sign(v: int) -> int:
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def _apply_move(x: int, y: int, action: str, grid_width: int, grid_height: int):
    """Return (nx, ny) after applying move, clamped to grid bounds."""
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


def _dist_to_nearest_food_after_move(x: int, y: int, action: str,
                                     grid_width: int, grid_height: int,
                                     food_list: list) -> float:
    """Manhattan distance to nearest food from position after executing action."""
    nx, ny = _apply_move(x, y, action, grid_width, grid_height)
    if not food_list:
        return float("inf")
    return min(_manhattan(nx, ny, f["x"], f["y"]) for f in food_list)


def _softmax(values: dict, beta: float) -> dict:
    """Numerically stable softmax over a dict[action → float]."""
    if not values:
        return {}
    max_v = max(values.values())
    raw = {a: math.exp(beta * (v - max_v)) for a, v in values.items()}
    total = sum(raw.values())
    return {a: p / total for a, p in raw.items()}


def _weighted_choice(actions: list, weights: list) -> str:
    """Sample one action from a list given corresponding probability weights."""
    r = random.random()
    cumulative = 0.0
    for a, w in zip(actions, weights):
        cumulative += w
        if r <= cumulative:
            return a
    return actions[-1]  # fallback due to float rounding


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

MOVE_ACTIONS = ["move_up", "move_down", "move_left", "move_right"]
ALL_ACTIONS = MOVE_ACTIONS + ["stay", "eat"]


class DualControllerCompetitionWithPavlovianOverrideModel:
    """
    Dual-Controller Competition with Pavlovian Override DecisionModel.

    Goal-directed system  : hunger-sensitive action values (model-based)
    Habitual system       : TD Q-learning with unmodulated reward
    Pavlovian override    : fixed eat probability when food is at cell

    decide()  → read-only, selects action from cached state
    update()  → all state mutations happen here
    """

    def __init__(
        self,
        # Parameters (with defaults from spec)
        alpha_E: float = 0.01,
        c_food: float = 0.3,
        eta_H: float = 0.02,
        kappa_H: float = 0.4,
        alpha_Q: float = 0.05,
        gamma: float = 0.9,
        beta: float = 5.0,
        lambda_omega: float = 0.002,
        omega_0: float = 0.8,
        p_pav: float = 0.2,
        r_food: float = 1.0,
        c_step: float = -0.02,
        E_set: float = 0.5,
        k_H: float = 4.0,
        seed: int = None,
    ):
        # ── Parameters ──────────────────────────────────────────────────────
        self.alpha_E = alpha_E
        self.c_food = c_food
        self.eta_H = eta_H
        self.kappa_H = kappa_H
        self.alpha_Q = alpha_Q
        self.gamma = gamma
        self.beta = beta
        self.lambda_omega = lambda_omega
        self.omega_0 = omega_0
        self.p_pav = p_pav
        self.r_food = r_food
        self.c_step = c_step
        self.E_set = E_set
        self.k_H = k_H

        # ── State variables ──────────────────────────────────────────────────
        self.energy_store: float = 0.5          # E
        self.hunger_drive: float = 0.3          # H
        self.goal_directed_value: float = 0.0   # V_GD (scalar summary)
        self.habitual_q_value: dict = {}         # Q_H[(s, a)] → float
        self.arbitration_weight: float = omega_0  # omega
        self.eating_experience_count: int = 0   # n_eat
        self.pavlovian_override_probability: float = 0.0  # pi_pav
        self.habitual_prediction_error: float = 0.0       # delta
        self.ate_flag: int = 0                  # ate

        # ── Internal bookkeeping for TD update ──────────────────────────────
        self._prev_state_key = None   # s_{t-1}
        self._prev_action: str = None  # a_{t-1}

        # ── Cached q_values for get_state() ─────────────────────────────────
        self.q_values: dict = {a: 0.0 for a in ALL_ACTIONS}

        if seed is not None:
            random.seed(seed)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _get_q_H(self, state_key, action: str) -> float:
        return self.habitual_q_value.get((state_key, action), 0.0)

    def _set_q_H(self, state_key, action: str, value: float) -> None:
        self.habitual_q_value[(state_key, action)] = value

    def _build_state_key(self, x: int, y: int, food_at_cell: bool,
                         food_list: list):
        """Discrete state: (x, y, food_at_cell, dx_sign, dy_sign)."""
        nearest = _nearest_food(x, y, food_list)
        if nearest is not None:
            dx_sign = _sign(nearest["x"] - x)
            dy_sign = _sign(nearest["y"] - y)
        else:
            dx_sign, dy_sign = 0, 0
        return (x, y, int(food_at_cell), dx_sign, dy_sign)

    def _compute_v_int(self, s_key, x: int, y: int, food_at_cell: bool,
                       food_list: list, grid_width: int, grid_height: int
                       ) -> dict:
        """
        Compute integrated action values for all actions.
        V_int[a] = omega * V_GD[a] + (1-omega) * Q_H[s,a]
        """
        H = self.hunger_drive
        omega = self.arbitration_weight

        v_int = {}
        for a in ALL_ACTIONS:
            # Goal-directed value
            if a == "eat":
                if food_at_cell:
                    v_gd = H * self.r_food
                else:
                    v_gd = 0.0  # eat is meaningless without food
            elif a == "stay":
                v_gd = 0.0
            else:  # move actions
                d_after = _dist_to_nearest_food_after_move(
                    x, y, a, grid_width, grid_height, food_list
                )
                if math.isinf(d_after):
                    v_gd = self.c_step
                else:
                    v_gd = H * self.r_food / (1.0 + d_after) + self.c_step

            # Habitual value
            v_hab = self._get_q_H(s_key, a)

            v_int[a] = omega * v_gd + (1.0 - omega) * v_hab

        return v_int

    def _compute_final_probs(self, v_int: dict, food_at_cell: bool) -> dict:
        """
        1. Softmax base policy over integrated values.
        2. Pavlovian override: inject p_pav eat probability if food at cell.
        """
        p_base = _softmax(v_int, self.beta)

        if food_at_cell:
            pi_pav = self.p_pav
            p_final = {}
            for a in ALL_ACTIONS:
                if a == "eat":
                    p_final[a] = (1.0 - pi_pav) * p_base.get(a, 0.0) + pi_pav
                else:
                    p_final[a] = (1.0 - pi_pav) * p_base.get(a, 0.0)
        else:
            p_final = dict(p_base)

        return p_final

    # -----------------------------------------------------------------------
    # DecisionModel interface
    # -----------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Read-only: compute action probabilities from CURRENT cached state
        and sample an action.

        NOTE: decide() receives perception WITHOUT last_action_result.
        All state mutations happen in update().
        """
        x = perception["x"]
        y = perception["y"]
        grid_width = perception["grid_width"]
        grid_height = perception["grid_height"]
        food_list = perception.get("resources", {}).get("food", [])

        food_at_cell = any(
            f["x"] == x and f["y"] == y for f in food_list
        )

        s_key = self._build_state_key(x, y, food_at_cell, food_list)

        # Compute integrated values and final probabilities
        v_int = self._compute_v_int(
            s_key, x, y, food_at_cell, food_list, grid_width, grid_height
        )
        p_final = self._compute_final_probs(v_int, food_at_cell)

        # Sample action
        actions = list(p_final.keys())
        weights = [p_final[a] for a in actions]
        selected = _weighted_choice(actions, weights)

        return Action(name=selected)

    def update(self, action: Action, reward: float,
               new_perception: dict) -> None:
        """
        Apply all rules and update internal state.

        Called AFTER the environment has executed the action.
        new_perception includes last_action_result.
        """
        x = new_perception["x"]
        y = new_perception["y"]
        grid_width = new_perception["grid_width"]
        grid_height = new_perception["grid_height"]
        food_list = new_perception.get("resources", {}).get("food", [])
        last_result = new_perception.get("last_action_result", {})

        # ── Step 1: Determine ate flag ───────────────────────────────────────
        # A successful eat is indicated by a "consumed" or positive result key.
        ate = 0
        if last_result:
            # Check common result keys that indicate successful consumption
            if last_result.get("consumed", False):
                ate = 1
            elif last_result.get("success", False) and action.name == "eat":
                ate = 1
            elif last_result.get("food_consumed", False):
                ate = 1
            elif last_result.get("result") == "consumed":
                ate = 1
            elif last_result.get("outcome") == "consumed":
                ate = 1
        self.ate_flag = ate

        # ── Step 2: Update eating experience count (R5 input) ────────────────
        if ate == 1:
            self.eating_experience_count += 1  # n_eat += 1

        # ── Step 3: R1 – Energy dynamics ─────────────────────────────────────
        self.energy_store = _clamp(
            self.energy_store - self.alpha_E + self.c_food * ate,
            0.0, 1.0
        )

        # ── Step 4: R2 – Hunger dynamics ─────────────────────────────────────
        self.hunger_drive = _clamp(
            self.hunger_drive + self.eta_H - self.kappa_H * ate,
            0.0, 1.0
        )

        # ── Step 5: Build new state key (s_t) ────────────────────────────────
        food_at_cell_new = any(
            f["x"] == x and f["y"] == y for f in food_list
        )
        s_new = self._build_state_key(x, y, food_at_cell_new, food_list)

        # ── Step 6: R4 – Habitual Q-value TD update ──────────────────────────
        # Uses UNMODULATED reward — devaluation-insensitive by design.
        if self._prev_state_key is not None and self._prev_action is not None:
            R_H = self.r_food if ate == 1 else self.c_step

            # Max Q over next state actions
            max_q_next = max(
                self._get_q_H(s_new, a) for a in ALL_ACTIONS
            )

            q_prev = self._get_q_H(self._prev_state_key, self._prev_action)
            delta = R_H + self.gamma * max_q_next - q_prev
            self.habitual_prediction_error = delta

            new_q = q_prev + self.alpha_Q * delta
            self._set_q_H(self._prev_state_key, self._prev_action, new_q)

        # ── Step 7: R5 – Arbitration weight (habitization) ───────────────────
        self.arbitration_weight = max(
            self.omega_0 - self.lambda_omega * self.eating_experience_count,
            0.0
        )

        # ── Step 8: Compute updated integrated values + Pavlovian ────────────
        # (for q_values caching used by get_state)
        v_int_new = self._compute_v_int(
            s_new, x, y, food_at_cell_new, food_list, grid_width, grid_height
        )
        p_final_new = self._compute_final_probs(v_int_new, food_at_cell_new)

        # Cache V_GD summary (eat value) for get_state
        self.goal_directed_value = self.hunger_drive * self.r_food
        self.pavlovian_override_probability = (
            self.p_pav if food_at_cell_new else 0.0
        )

        # Update cached q_values (integrated values = what get_state exposes)
        self.q_values = dict(v_int_new)

        # ── Step 9: Store state/action for next TD update ────────────────────
        self._prev_state_key = s_new
        self._prev_action = action.name

    def get_state(self) -> dict:
        """Return full state snapshot including q_values."""
        return {
            "energy_store": self.energy_store,
            "hunger_drive": self.hunger_drive,
            "goal_directed_value": self.goal_directed_value,
            "arbitration_weight": self.arbitration_weight,
            "eating_experience_count": self.eating_experience_count,
            "pavlovian_override_probability": self.pavlovian_override_probability,
            "habitual_prediction_error": self.habitual_prediction_error,
            "ate_flag": self.ate_flag,
            "q_values": dict(self.q_values),
        }
