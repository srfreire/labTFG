"""
Proportional-Integral (PI) Negative-Feedback Controller
formulation_id: homeostatic-regulation_pi_negative_feedback

A PI-controller homeostatic agent that maintains internal energy via proportional
and integral error correction.  Action selection is deterministic and utility-based.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

class HomeostaticPINegativeFeedback:
    """PI negative-feedback homeostatic controller agent."""

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
        # --- parameters ---
        self.s = energy_set_point
        self.k_P = proportional_gain
        self.k_I = integral_gain
        self.d = passive_energy_decay
        self.delta_eat = energy_from_eating
        self.A_max = max_energy
        self.c_I_max = integral_windup_cap

        # --- variables (initial values from spec) ---
        self.A: float = 50.0          # energy
        self.e: float = self.s - self.A  # error = 30.0
        self.c_P: float = self.k_P * self.e  # 15.0
        self.c_I: float = 0.0         # integral control
        self.c: float = self.c_P + self.c_I  # total control = 15.0

        # --- action scores (for decision trace visualization) ---
        self._q_values: dict[str, float] = {
            "move_up": 0.0, "move_down": 0.0,
            "move_left": 0.0, "move_right": 0.0,
            "stay": 0.0, "eat": 0.0,
        }

    # ------------------------------------------------------------------
    # decide  (READ-ONLY)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """Select action based on current PI control signal."""
        pos = (perception["x"], perception["y"])
        grid_w = perception.get("grid_width", 10)
        grid_h = perception.get("grid_height", 10)
        food_list = perception.get("resources", {}).get("food", [])
        food_positions = {(f["x"], f["y"]) for f in food_list}
        food_at_position = pos in food_positions

        # R8 – stay utility
        # R6 decision: if error <= 0, agent is at or above set point → stay
        if self.e <= 0:
            return Action(name="stay")

        # R6 – eat utility
        if food_at_position:
            U_eat = self.c  # c > 0 since e > 0
            if U_eat > 0:
                return Action(name="eat")

        # R7 – move utility: pick best adjacent cell
        if food_positions:
            moves = [
                ("move_up",    0, -1),
                ("move_down",  0,  1),
                ("move_left", -1,  0),
                ("move_right", 1,  0),
            ]
            best_action = None
            best_utility = float("-inf")
            for action_name, dx, dy in moves:
                px = _clamp(pos[0] + dx, 0, grid_w - 1)
                py = _clamp(pos[1] + dy, 0, grid_h - 1)
                min_dist = min(
                    abs(px - fx) + abs(py - fy) for fx, fy in food_positions
                )
                U_move = self.c * (1.0 / (1 + min_dist))
                if U_move > best_utility:
                    best_utility = U_move
                    best_action = action_name
            return Action(name=best_action)

        # No food visible – random exploration
        return Action(
            name=random.choice(["move_up", "move_down", "move_left", "move_right"])
        )

    # ------------------------------------------------------------------
    # update  (ALL state mutations live here)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Apply PI controller rules and energy dynamics."""
        last_result = new_perception.get("last_action_result", {})
        consumed = last_result.get("consumed", False)

        # R5 – energy dynamics
        ate = 1 if (action.name == "eat" and consumed) else 0
        self.A = _clamp(self.A - self.d + self.delta_eat * ate, 0.0, self.A_max)

        # R1 – error signal
        self.e = self.s - self.A

        # R2 – proportional control
        self.c_P = self.k_P * self.e

        # R3 – integral control with anti-windup
        self.c_I = _clamp(self.c_I + self.k_I * self.e, -self.c_I_max, self.c_I_max)

        # R4 – total control signal
        self.c = self.c_P + self.c_I

        # Cache action utilities for decision trace visualization
        pos = (new_perception["x"], new_perception["y"])
        grid_w = new_perception.get("grid_width", 10)
        grid_h = new_perception.get("grid_height", 10)
        food_list = new_perception.get("resources", {}).get("food", [])
        food_positions = {(f["x"], f["y"]) for f in food_list}

        scores: dict[str, float] = {}
        scores["stay"] = 0.0 if self.e > 0 else abs(self.c)
        scores["eat"] = self.c if (self.e > 0 and pos in food_positions) else 0.0
        for name, dx, dy in [("move_up", 0, -1), ("move_down", 0, 1),
                              ("move_left", -1, 0), ("move_right", 1, 0)]:
            if self.e > 0 and food_positions:
                px = _clamp(pos[0] + dx, 0, grid_w - 1)
                py = _clamp(pos[1] + dy, 0, grid_h - 1)
                min_dist = min(abs(px - fx) + abs(py - fy) for fx, fy in food_positions)
                scores[name] = self.c * (1.0 / (1 + min_dist))
            else:
                scores[name] = 0.0
        self._q_values = scores

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "energy": self.A,
            "error_signal": self.e,
            "proportional_control": self.c_P,
            "integral_control": self.c_I,
            "total_control_signal": self.c,
            "q_values": dict(self._q_values),
        }
