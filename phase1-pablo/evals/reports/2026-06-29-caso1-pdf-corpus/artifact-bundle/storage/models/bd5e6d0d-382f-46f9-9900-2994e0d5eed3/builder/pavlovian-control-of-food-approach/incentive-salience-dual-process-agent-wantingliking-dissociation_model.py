"""
Incentive Salience Dual-Process Agent (Wanting–Liking Dissociation)

Dual-channel Pavlovian agent maintaining separate 'wanting' (dopamine-mediated
incentive salience) and 'liking' (opioid-mediated hedonic value) maps, each with
independent learning dynamics. Wanting drives approach vigor proportional to hunger,
while liking tracks hedonic experience modulated by alliesthesia.

References:
    Berridge & Robinson (2003), Rangel (2013).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class IncentiveSalienceDualProcessAgentWantinglikingDissociationModel:
    """
    Dual-process Pavlovian agent with separate wanting (W) and liking (L) value maps.

    - W: dopamine-mediated incentive salience, fast learning (alpha_W = 0.12)
    - L: opioid-mediated hedonic value, slow learning (alpha_L = 0.05)
    - Hunger (h_t) multiplicatively gates wanting and modulates liking via alliesthesia.
    - Combined Q_total = w_W * Q_W + w_L * Q_L - c_step * (movement)
    - Softmax action selection with inverse temperature beta.
    """

    MOVEMENT_ACTIONS = ("move_up", "move_down", "move_left", "move_right")
    ALL_ACTIONS = ("move_up", "move_down", "move_left", "move_right", "stay", "eat")

    def __init__(
        self,
        wanting_learning_rate: float = 0.12,   # alpha_W
        liking_learning_rate: float = 0.05,    # alpha_L
        inverse_temperature: float = 5.0,      # beta
        hunger_wanting_gain: float = 1.5,      # mu
        alliesthesia_coefficient: float = 1.0, # lam
        wanting_weight: float = 0.6,           # w_W
        liking_weight: float = 0.4,            # w_L
        food_reward_magnitude: float = 1.0,    # r_food
        hunger_increment_rate: float = 0.02,   # alpha_h
        satiation_decrement: float = 0.20,     # gamma_sat
        movement_cost: float = 0.01,           # c_step
        max_wanting: float = 2.0,              # W_max
        max_liking: float = 2.0,               # L_max
    ) -> None:
        # --- Parameters ---
        self.alpha_W = wanting_learning_rate
        self.alpha_L = liking_learning_rate
        self.beta = inverse_temperature
        self.mu = hunger_wanting_gain
        self.lam = alliesthesia_coefficient
        self.w_W = wanting_weight
        self.w_L = liking_weight
        self.r_food = food_reward_magnitude
        self.alpha_h = hunger_increment_rate
        self.gamma_sat = satiation_decrement
        self.c_step = movement_cost
        self.W_max = max_wanting
        self.L_max = max_liking

        # --- State variables ---
        self.W: Dict[Tuple[int, int], float] = {}   # wanting map
        self.L: Dict[Tuple[int, int], float] = {}   # liking map
        self.wanting_prediction_error: float = 0.0  # delta_W
        self.liking_prediction_error: float = 0.0   # delta_L
        self.hunger_level: float = 0.5              # h_t
        self.reward_received: float = 0.0           # r_t

        # Combined action values and probabilities (recomputed each step)
        self.combined_action_values: Dict[str, float] = {a: 0.0 for a in self.ALL_ACTIONS}
        self.action_probabilities: Dict[str, float] = {a: 1.0 / len(self.ALL_ACTIONS) for a in self.ALL_ACTIONS}

        # q_values for get_state (cached from last update or init)
        self._q_values: Dict[str, float] = {a: 0.0 for a in self.ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Helper: compute Q_total dict for a given perception snapshot
    # ------------------------------------------------------------------
    def _compute_q_total(
        self,
        pos: Tuple[int, int],
        food_positions: set,
        grid_w: int,
        grid_h: int,
        h_t: float,
    ) -> Dict[str, float]:
        """Compute the combined action value for each action (R6, R7, R8)."""
        destinations = {
            "move_up":    (pos[0], pos[1] - 1),
            "move_down":  (pos[0], pos[1] + 1),
            "move_left":  (pos[0] - 1, pos[1]),
            "move_right": (pos[0] + 1, pos[1]),
            "stay":       pos,
            "eat":        pos,
        }
        food_at_pos = pos in food_positions
        h_lam = h_t ** self.lam  # alliesthesia factor

        q_total: Dict[str, float] = {}
        for action_name, dest in destinations.items():
            dx, dy = dest

            # Availability masking
            if action_name == "eat" and not food_at_pos:
                q_total["eat"] = -1e9
                continue
            if action_name in self.MOVEMENT_ACTIONS:
                if not (0 <= dx < grid_w and 0 <= dy < grid_h):
                    q_total[action_name] = -1e9
                    continue

            # R6: hunger-modulated wanting contribution
            Q_W = self.mu * h_t * self.W.get(dest, 0.0)
            # R7: alliesthesia-modulated liking contribution
            Q_L = h_lam * self.L.get(dest, 0.0)
            # R8: combined value
            is_movement = action_name in self.MOVEMENT_ACTIONS
            q_total[action_name] = (
                self.w_W * Q_W + self.w_L * Q_L
                - self.c_step * (1.0 if is_movement else 0.0)
            )

        return q_total

    # ------------------------------------------------------------------
    # Helper: softmax over q_total → action probabilities
    # ------------------------------------------------------------------
    @staticmethod
    def _softmax(q_total: Dict[str, float], beta: float) -> Dict[str, float]:
        """Numerically stable softmax (R9)."""
        # Exclude sentinel values from softmax peak (keep -1e9 as effectively 0 prob)
        max_q = max(q_total.values())
        exp_vals = {a: math.exp(beta * (q - max_q)) for a, q in q_total.items()}
        Z = sum(exp_vals.values())
        return {a: v / Z for a, v in exp_vals.items()}

    # ------------------------------------------------------------------
    # decide: READ-ONLY — select action from current state
    # ------------------------------------------------------------------
    def decide(self, perception: dict) -> Action:
        """
        Compute Q_total and softmax, then sample an action.
        Must NOT modify any state variables.
        """
        pos = (perception["x"], perception["y"])
        food_list: List[dict] = perception.get("resources", {}).get("food", [])
        food_positions = {(f["x"], f["y"]) for f in food_list}
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]

        # Compute combined values using current h_t (read-only)
        q_total = self._compute_q_total(pos, food_positions, grid_w, grid_h, self.hunger_level)

        # Softmax probabilities (R9)
        p_a = self._softmax(q_total, self.beta)

        # Sample action
        actions = list(p_a.keys())
        weights = [p_a[a] for a in actions]
        selected = random.choices(actions, weights=weights, k=1)[0]

        return Action(name=selected)

    # ------------------------------------------------------------------
    # update: WRITE — apply all rules, update state
    # ------------------------------------------------------------------
    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all learning rules (R1–R5) and refresh q_values cache.
        All state mutation happens here.
        """
        pos = (new_perception["x"], new_perception["y"])
        food_list: List[dict] = new_perception.get("resources", {}).get("food", [])
        food_positions = {(f["x"], f["y"]) for f in food_list}
        grid_w = new_perception["grid_width"]
        grid_h = new_perception["grid_height"]
        last_result: dict = new_perception.get("last_action_result", {})

        # Determine if eat succeeded
        ate = 0.0
        if action.name == "eat":
            # last_action_result may have 'consumed': True or 'success': True
            consumed = last_result.get("consumed", last_result.get("success", False))
            if consumed:
                ate = 1.0

        # r_t: reward received
        self.reward_received = reward

        # ---- R1: wanting prediction error ----
        self.wanting_prediction_error = reward - self.W.get(pos, 0.0)

        # ---- R2: wanting value update ----
        new_w = self.W.get(pos, 0.0) + self.alpha_W * self.wanting_prediction_error
        self.W[pos] = max(0.0, min(self.W_max, new_w))

        # ---- R3: liking prediction error (alliesthesia) ----
        h_lam = self.hunger_level ** self.lam
        self.liking_prediction_error = reward * h_lam - self.L.get(pos, 0.0)

        # ---- R4: liking value update ----
        new_l = self.L.get(pos, 0.0) + self.alpha_L * self.liking_prediction_error
        self.L[pos] = max(0.0, min(self.L_max, new_l))

        # ---- R5: hunger dynamics ----
        self.hunger_level = max(
            0.0,
            min(1.0, self.hunger_level + self.alpha_h - self.gamma_sat * ate),
        )

        # ---- Cache Q_total and P_a for get_state / visualization ----
        q_total = self._compute_q_total(
            pos, food_positions, grid_w, grid_h, self.hunger_level
        )
        self.combined_action_values = q_total.copy()
        self._q_values = {
            a: q for a, q in q_total.items() if q > -1e8  # exclude masked actions
        }
        # Keep masked actions with a very low but representable float for completeness
        for a, q in q_total.items():
            if a not in self._q_values:
                self._q_values[a] = -1e9

        self.action_probabilities = self._softmax(q_total, self.beta)

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        return {
            "wanting_values": dict(self.W),
            "liking_values": dict(self.L),
            "wanting_prediction_error": self.wanting_prediction_error,
            "liking_prediction_error": self.liking_prediction_error,
            "hunger_level": self.hunger_level,
            "reward_received": self.reward_received,
            "combined_action_values": dict(self.combined_action_values),
            "action_probabilities": dict(self.action_probabilities),
            "q_values": dict(self._q_values),
        }
