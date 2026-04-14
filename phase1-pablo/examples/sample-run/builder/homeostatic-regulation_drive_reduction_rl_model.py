"""
Homeostatic Reinforcement Learning (Drive-Reduction MDP)
formulation_id: homeostatic-regulation_drive_reduction_rl

Tabular Q-learning agent where reward = drive reduction (decrease in quadratic
discomfort from homeostatic set point).  Action selection uses softmax (Boltzmann)
exploration over Q-values.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ALL_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compass(dx: int, dy: int) -> str:
    """Map (dx, dy) offset to a compass direction string, or 'here'."""
    if dx == 0 and dy == 0:
        return "here"
    # normalise to -1, 0, +1
    sx = (1 if dx > 0 else -1) if dx != 0 else 0
    sy = (1 if dy > 0 else -1) if dy != 0 else 0
    mapping = {
        (0, -1): "N",
        (1, -1): "NE",
        (1,  0): "E",
        (1,  1): "SE",
        (0,  1): "S",
        (-1,  1): "SW",
        (-1,  0): "W",
        (-1, -1): "NW",
    }
    return mapping.get((sx, sy), "none")


def _discretize(energy: float, food_list: list, pos: tuple,
                n_bins: int, x_max: float) -> tuple:
    """Return (energy_bin, direction_to_nearest_food)."""
    energy_bin = min(int(energy * n_bins / x_max), n_bins - 1)
    if not food_list:
        direction = "none"
    else:
        nearest = min(
            food_list,
            key=lambda f: abs(f["x"] - pos[0]) + abs(f["y"] - pos[1])
        )
        dx = nearest["x"] - pos[0]
        dy = nearest["y"] - pos[1]
        direction = _compass(dx, dy)
    return (energy_bin, direction)


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

class HomeostaticDriveReductionRL:
    """Drive-reduction Q-learning homeostatic agent."""

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
        # --- parameters ---
        self.s = energy_set_point
        self.phi = drive_weight
        self.x_max = max_energy
        self.d = passive_energy_decay
        self.delta_eat = energy_from_eating
        self.alpha = td_learning_rate
        self.gamma = discount_factor
        self.beta = softmax_inv_temperature
        self.n_bins = energy_discretization_bins

        # --- variables ---
        self.x: float = 50.0                          # energy
        self.D: float = self.phi * (self.x - self.s) ** 2  # drive
        self.r: float = 0.0                           # reward
        self.Q: dict = defaultdict(float)             # Q-table
        self.z: tuple = (5, "none")                   # discretized state
        self.x_prev: float = 50.0
        self.z_prev: tuple = (5, "none")
        self.a_prev: str = "stay"

        # internal flag – skip TD update on very first call to update()
        self._first_update: bool = True

    # ------------------------------------------------------------------
    # decide  (READ-ONLY – no state mutation)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """Select an action via softmax over current Q-values."""
        pos = (perception["x"], perception["y"])
        food_list = perception.get("resources", {}).get("food", [])
        food_at_position = any(
            f["x"] == pos[0] and f["y"] == pos[1] for f in food_list
        )

        z = self.z  # current discretized state (set during last update)

        q_vals: dict[str, float] = {}
        for a in ALL_ACTIONS:
            if a == "eat" and not food_at_position:
                q_vals[a] = float("-inf")
            else:
                q_vals[a] = self.Q.get((z, a), 0.0)

        finite_vals = [v for v in q_vals.values() if v != float("-inf")]
        max_q = max(finite_vals) if finite_vals else 0.0

        exp_vals: dict[str, float] = {}
        for a, v in q_vals.items():
            if v == float("-inf"):
                exp_vals[a] = 0.0
            else:
                exp_vals[a] = math.exp(self.beta * (v - max_q))

        total = sum(exp_vals.values())
        if total == 0.0:
            total = 1.0  # fallback – uniform over feasible

        probs = {a: ev / total for a, ev in exp_vals.items()}
        selected = random.choices(
            list(probs.keys()), weights=list(probs.values()), k=1
        )[0]
        return Action(name=selected)

    # ------------------------------------------------------------------
    # update  (ALL state mutations live here)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Apply energy dynamics, compute drive-reduction reward, TD-update Q."""
        last_result = new_perception.get("last_action_result", {})
        consumed = last_result.get("consumed", False)
        pos = (new_perception["x"], new_perception["y"])
        food_list = new_perception.get("resources", {}).get("food", [])

        # R1 – energy dynamics
        ate = 1 if (action.name == "eat" and consumed) else 0
        self.x = _clamp(self.x - self.d + self.delta_eat * ate, 0.0, self.x_max)

        # R2 – current drive
        self.D = self.phi * (self.x - self.s) ** 2

        # R3 – reward = drive reduction
        D_prev = self.phi * (self.x_prev - self.s) ** 2
        D_curr = self.D
        self.r = D_prev - D_curr

        # R4 – discretize new state
        self.z = _discretize(self.x, food_list, pos, self.n_bins, self.x_max)

        # R5 & R6 – TD update (skip on first step)
        if not self._first_update:
            best_future = max(
                self.Q.get((self.z, a), 0.0) for a in ALL_ACTIONS
            )
            delta = self.r + self.gamma * best_future - self.Q.get(
                (self.z_prev, self.a_prev), 0.0
            )
            self.Q[(self.z_prev, self.a_prev)] = (
                self.Q.get((self.z_prev, self.a_prev), 0.0) + self.alpha * delta
            )

        self._first_update = False

        # store for next update
        self.x_prev = self.x
        self.z_prev = self.z
        self.a_prev = action.name

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "energy": self.x,
            "drive": self.D,
            "reward": self.r,
            "q_values": {a: self.Q.get((self.z, a), 0.0) for a in ALL_ACTIONS},
            "q_table": dict(self.Q),
            "discretized_state": self.z,
            "previous_energy": self.x_prev,
            "previous_state": self.z_prev,
            "previous_action": self.a_prev,
        }
