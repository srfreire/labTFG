"""
Continuous Drive-Dynamics with Urgency-Threshold Policy Model
=============================================================
Paradigm : homeostatic-regulation
Formulation: continuous-drive-dynamics-with-urgency-threshold-policy

ODE-based continuous-time drive dynamics with a deterministic threshold-and-
gradient policy.  The agent maintains a scalar energy level governed by linear
decay and discrete intake events.  Drive is the asymmetric (deficit-only)
squared deviation from setpoint.  A cybernetic negative-feedback controller
uses two thresholds (D_crit and D_low) plus drive velocity to gate between
three behavioural modes: REST, EAT, and FORAGE.

References
----------
Cannon (1929) · Hull (1943) · Keramati & Gutkin (2014, eLife 3:e04811)
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Action dataclass (inline — no external imports)
# ---------------------------------------------------------------------------

@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manhattan(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(x1 - x2) + abs(y1 - y2)


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ContinuousDriveDynamicsWithUrgencyThresholdPolicyModel:
    """
    Deterministic cybernetic controller implementing drive-reduction homeostasis.

    decide()  – read-only: compute mode from current internal state + perception,
                return the appropriate action.
    update()  – write: apply ODE rules R1–R3, update mode (R5), refresh q_values.
    """

    # Move action name → (dx, dy)
    _MOVE_DELTAS: Dict[str, tuple] = {
        "move_up":    (0, -1),
        "move_down":  (0,  1),
        "move_left":  (-1, 0),
        "move_right": ( 1, 0),
    }
    _MOVE_ACTIONS: List[str] = ["move_up", "move_down", "move_left", "move_right"]
    _ALL_ACTIONS:  List[str] = ["move_up", "move_down", "move_left", "move_right",
                                 "stay", "eat"]

    def __init__(
        self,
        setpoint:                 float = 0.8,
        drive_exponent:           int   = 2,
        natural_decay_rate:       float = 0.02,
        eating_restoration:       float = 0.3,
        movement_cost:            float = 0.005,
        critical_drive_threshold: float = 0.15,
        low_drive_threshold:      float = 0.02,
    ) -> None:
        # --- parameters ---
        self.h_star         = setpoint                  # h*
        self.n              = drive_exponent            # n
        self.lambda_decay   = natural_decay_rate        # λ
        self.c_eat          = eating_restoration        # c_eat
        self.c_move         = movement_cost             # c_move
        self.D_crit         = critical_drive_threshold  # D_crit
        self.D_low          = low_drive_threshold       # D_low

        # --- state variables ---
        self.h              = 0.8           # energy_level
        self.D              = 0.0           # drive
        self.D_prev         = 0.0           # previous_drive
        self.dD_dt          = 0.0           # drive_velocity
        self.mode           = "REST"        # behavioural_mode

        # --- q_values: utility score for each action (updated in update()) ---
        self.q_values: Dict[str, float] = {a: 0.0 for a in self._ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Internal: drive and mode computation (shared by decide and update)
    # ------------------------------------------------------------------

    def _compute_drive(self, h: float) -> float:
        """R2: asymmetric squared deficit."""
        return (max(self.h_star - h, 0.0)) ** self.n

    def _select_mode(
        self,
        D: float,
        dD_dt: float,
        food_here: bool,
    ) -> str:
        """R5: threshold gating."""
        if D < self.D_low:
            return "REST"
        elif food_here and D > 0:
            return "EAT"
        elif D >= self.D_crit or dD_dt > 0:
            return "FORAGE"
        else:
            return "REST"

    def _best_forage_action(
        self,
        cx: int, cy: int,
        grid_width: int, grid_height: int,
        food_list: List[Dict[str, Any]],
    ) -> str:
        """R4: greedy Manhattan gradient toward nearest food."""
        if not food_list:
            return random.choice(self._MOVE_ACTIONS)

        best_action   = None
        best_gradient = -math.inf

        d_current = min(_manhattan(cx, cy, f["x"], f["y"]) for f in food_list)

        for a in self._MOVE_ACTIONS:
            dx, dy = self._MOVE_DELTAS[a]
            nx = _clip(cx + dx, 0, grid_width  - 1)
            ny = _clip(cy + dy, 0, grid_height - 1)
            d_after = min(_manhattan(nx, ny, f["x"], f["y"]) for f in food_list)
            g = d_current - d_after  # positive → moving closer
            if g > best_gradient:
                best_gradient = g
                best_action   = a

        return best_action if best_action is not None else random.choice(self._MOVE_ACTIONS)

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY.  Select an action from the current internal state and
        the current perception.  No state mutation here.
        """
        cx          = perception["x"]
        cy          = perception["y"]
        grid_width  = perception["grid_width"]
        grid_height = perception["grid_height"]
        food_list   = perception["resources"].get("food", [])
        food_here   = any(
            f["x"] == cx and f["y"] == cy for f in food_list
        )

        # Drive and velocity from current (already-updated) state
        D     = self.D
        dD_dt = self.dD_dt

        # Mode selection (R5)
        mode = self._select_mode(D, dD_dt, food_here)

        # Action execution
        if mode == "REST":
            return Action("stay")
        elif mode == "EAT":
            return Action("eat")
        else:  # FORAGE
            return Action(
                self._best_forage_action(cx, cy, grid_width, grid_height, food_list)
            )

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE.  Apply all rules (R1–R5) and refresh q_values.

        Uses new_perception (which contains last_action_result) to
        determine what actually happened.
        """
        last_result = new_perception.get("last_action_result", {})

        # R1: energy dynamics
        moved = 1 if action.name in self._MOVE_ACTIONS else 0
        ate   = 1 if (
            action.name == "eat" and last_result.get("consumed", False)
        ) else 0
        self.h = _clip(
            self.h + (-self.lambda_decay + self.c_eat * ate - self.c_move * moved),
            0.0, 1.0,
        )

        # R2: drive
        new_D     = self._compute_drive(self.h)
        # R3: drive velocity  (compare new drive to previous drive)
        new_dDdt  = new_D - self.D

        # Store state
        self.D_prev = self.D
        self.D      = new_D
        self.dD_dt  = new_dDdt

        # R5: mode (for get_state readout)
        cx        = new_perception["x"]
        cy        = new_perception["y"]
        food_list = new_perception["resources"].get("food", [])
        food_here = any(f["x"] == cx and f["y"] == cy for f in food_list)
        self.mode = self._select_mode(self.D, self.dD_dt, food_here)

        # Refresh q_values: utility = drive reduction each action would produce
        # next step (prospective one-step lookahead, ignoring food uncertainty).
        h_stay = _clip(self.h - self.lambda_decay,                       0.0, 1.0)
        h_eat  = _clip(self.h - self.lambda_decay + self.c_eat,          0.0, 1.0)
        h_move = _clip(self.h - self.lambda_decay - self.c_move,         0.0, 1.0)

        d_stay = self._compute_drive(h_stay)
        d_eat  = self._compute_drive(h_eat)
        d_move = self._compute_drive(h_move)

        # Utility = drive reduction relative to current drive
        u_stay = self.D - d_stay
        u_eat  = self.D - d_eat
        u_move = self.D - d_move

        self.q_values = {
            "stay":       u_stay,
            "eat":        u_eat,
            "move_up":    u_move,
            "move_down":  u_move,
            "move_left":  u_move,
            "move_right": u_move,
        }

    def get_state(self) -> dict:
        return {
            "energy_level":     self.h,
            "setpoint":         self.h_star,
            "drive":            self.D,
            "previous_drive":   self.D_prev,
            "drive_velocity":   self.dD_dt,
            "behavioural_mode": self.mode,
            "q_values":         dict(self.q_values),
        }
