"""
Attribute-Reweighting Algebraic Model (Rangel variant)
Paradigm: dlpfc-self-control-modulation

dlPFC dynamically modulates attribute weights (taste vs health) in vmPFC composite
chosen value computation. Conflict between immediate and long-term preferences triggers
dlPFC engagement, shifting weights toward health. Softmax action selection.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class AttributeReweightingAlgebraicModelModel:
    """
    Algebraic weighted-sum valuation model where dlPFC modulates relative weights of
    hedonic (taste) vs. abstract (health) attributes in vmPFC composite chosen value.
    """

    def __init__(
        self,
        baseline_health_weight: float = 0.2,    # w_h0
        baseline_taste_weight: float = 0.8,      # w_tau0
        coupling_gain_on_health_weight: float = 0.6,  # gamma_C
        softmax_inverse_temperature: float = 5.0,     # beta
        depletion_rate_per_control_event: float = 0.08,  # alpha_D
        passive_recovery_rate: float = 0.04,     # beta_D
        conflict_sensitivity: float = 1.5,       # lambda_K
        goal_decay_rate: float = 0.05,           # eta_G
        goal_boost_on_healthy_choice: float = 0.3,  # goal_boost
        distance_discount_factor: float = 0.9,   # distance_discount
    ):
        # Parameters
        self.w_h0 = baseline_health_weight
        self.w_tau0 = baseline_taste_weight
        self.gamma_C = coupling_gain_on_health_weight
        self.beta = softmax_inverse_temperature
        self.alpha_D = depletion_rate_per_control_event
        self.beta_D = passive_recovery_rate
        self.lambda_K = conflict_sensitivity
        self.eta_G = goal_decay_rate
        self.goal_boost = goal_boost_on_healthy_choice
        self.distance_discount = distance_discount_factor

        # State variables (initial values per spec)
        self.composite_chosen_value: float = 0.0   # CCV_a (last computed)
        self.health_weight: float = 0.2            # w_h
        self.taste_weight: float = 0.8             # w_tau
        self.dlpfc_coupling: float = 0.0           # C
        self.conflict_signal: float = 0.0          # K
        self.goal_activation: float = 0.5          # G
        self.depletion_level: float = 0.0          # D

        # q_values: utility score per action (initialized to 0.0)
        self._candidate_actions = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
        self.q_values: dict[str, float] = {a: 0.0 for a in self._candidate_actions}

        # Internal cache for decide() to use
        self._cached_ccvs: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_foods(self, perception: dict) -> list:
        """Extract food resource list from perception."""
        resources = perception.get("resources", {})
        return resources.get("food", [])

    def _food_at_pos(self, x: int, y: int, foods: list) -> Optional[dict]:
        """Return first food at (x, y), or None."""
        for f in foods:
            if f.get("x") == x and f.get("y") == y:
                return f
        return None

    def _manhattan(self, x1: int, y1: int, x2: int, y2: int) -> int:
        return abs(x1 - x2) + abs(y1 - y2)

    def _nearest_food_from(self, tx: int, ty: int, foods: list) -> Optional[dict]:
        """Return the nearest food to position (tx, ty) by Manhattan distance."""
        if not foods:
            return None
        return min(foods, key=lambda f: self._manhattan(tx, ty, f.get("x", 0), f.get("y", 0)))

    def _direction_delta(self, action_name: str) -> tuple[int, int]:
        return {
            "move_up": (0, -1),
            "move_down": (0, 1),
            "move_left": (-1, 0),
            "move_right": (1, 0),
        }[action_name]

    def _compute_conflict(self, foods: list) -> float:
        """R1: Compute conflict signal K."""
        if len(foods) < 1:
            return 0.0
        taste_vals = {i: f.get("palatability", 0.5) for i, f in enumerate(foods)}
        health_vals = {i: 1.0 - f.get("palatability", 0.5) for i, f in enumerate(foods)}

        tastiest_id = max(taste_vals, key=lambda i: taste_vals[i])
        healthiest_id = max(health_vals, key=lambda i: health_vals[i])

        if tastiest_id != healthiest_id:
            K = taste_vals[tastiest_id] - taste_vals[healthiest_id]
        else:
            K = 0.0
        return K

    def _compute_coupling(self, K: float, G: float, D: float) -> float:
        """R2: Compute dlPFC coupling strength C."""
        sigmoid_K = 1.0 / (1.0 + math.exp(-self.lambda_K * K))
        return sigmoid_K * G * (1.0 - D)

    def _compute_weights(self, C: float) -> tuple[float, float]:
        """R3: Compute modulated attribute weights."""
        w_h = self.w_h0 + self.gamma_C * C
        w_h = min(w_h, 1.0)
        w_tau = 1.0 - w_h
        return w_h, w_tau

    def _compute_ccv(
        self,
        action_name: str,
        px: int,
        py: int,
        foods: list,
        w_tau: float,
        w_h: float,
    ) -> float:
        """R4: Compute Composite Chosen Value for a candidate action."""
        if action_name == "eat":
            food = self._food_at_pos(px, py, foods)
            if food is not None:
                taste_a = food.get("palatability", 0.5)
                health_a = 1.0 - taste_a
                return w_tau * taste_a + w_h * health_a
            else:
                return 0.0
        elif action_name in ("move_up", "move_down", "move_left", "move_right"):
            dx, dy = self._direction_delta(action_name)
            tx, ty = px + dx, py + dy
            nearest = self._nearest_food_from(tx, ty, foods)
            if nearest is not None:
                dist = self._manhattan(tx, ty, nearest.get("x", 0), nearest.get("y", 0))
                taste_a = nearest.get("palatability", 0.5)
                health_a = 1.0 - taste_a
                ccv = (w_tau * taste_a + w_h * health_a) * (self.distance_discount ** dist)
                return ccv
            else:
                return 0.0
        else:  # stay
            return 0.0

    def _softmax_sample(self, ccvs: dict[str, float]) -> str:
        """R5: Sample action from softmax distribution over CCV values."""
        actions = list(ccvs.keys())
        vals = [ccvs[a] for a in actions]

        # Numerically stable softmax
        max_v = max(vals)
        exp_vals = [math.exp(self.beta * (v - max_v)) for v in vals]
        total = sum(exp_vals)
        probs = [e / total for e in exp_vals]

        r = random.random()
        cumulative = 0.0
        for action_name, prob in zip(actions, probs):
            cumulative += prob
            if r <= cumulative:
                return action_name
        return actions[-1]

    def _build_ccvs(self, perception: dict) -> dict[str, float]:
        """Compute CCVs for all candidate actions given a perception."""
        px = perception.get("x", 0)
        py = perception.get("y", 0)
        foods = self._get_foods(perception)

        # Compute intermediates using current cached state
        w_h = self.health_weight
        w_tau = self.taste_weight

        food_here = self._food_at_pos(px, py, foods)
        candidates = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here is not None:
            candidates.append("eat")

        ccvs = {}
        for a in candidates:
            ccvs[a] = self._compute_ccv(a, px, py, foods, w_tau, w_h)
        return ccvs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Read-only: Select an action based on current state and perception.
        Weights (w_h, w_tau) are already updated in update() or reflect initial values.
        """
        px = perception.get("x", 0)
        py = perception.get("y", 0)
        foods = self._get_foods(perception)

        w_h = self.health_weight
        w_tau = self.taste_weight

        food_here = self._food_at_pos(px, py, foods)
        candidates = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here is not None:
            candidates.append("eat")

        ccvs: dict[str, float] = {}
        for a in candidates:
            ccvs[a] = self._compute_ccv(a, px, py, foods, w_tau, w_h)

        # Cache for reference (not used in update)
        self._cached_ccvs = ccvs

        chosen = self._softmax_sample(ccvs)
        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all rules and update internal state:
        - R1: Compute conflict signal K
        - R2: Compute dlPFC coupling C
        - R3: Modulate attribute weights
        - R4: Compute CCVs and update q_values
        - R6: Update depletion level D
        - R7: Update goal activation G
        """
        px = new_perception.get("x", 0)
        py = new_perception.get("y", 0)
        foods = self._get_foods(new_perception)
        last_result = new_perception.get("last_action_result", {})

        # R1: Conflict signal
        K = self._compute_conflict(foods)
        self.conflict_signal = K

        # R2: dlPFC coupling (uses current G and D before update)
        C = self._compute_coupling(K, self.goal_activation, self.depletion_level)
        self.dlpfc_coupling = C

        # R3: Modulate attribute weights
        w_h, w_tau = self._compute_weights(C)
        self.health_weight = w_h
        self.taste_weight = w_tau

        # R4: Compute CCVs with updated weights and store as q_values
        food_here = self._food_at_pos(px, py, foods)
        candidates = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here is not None:
            candidates.append("eat")

        ccvs: dict[str, float] = {}
        for a in candidates:
            ccvs[a] = self._compute_ccv(a, px, py, foods, w_tau, w_h)

        # Update q_values for all known actions
        for a in self._candidate_actions:
            self.q_values[a] = ccvs.get(a, 0.0)

        # Store last CCV for the taken action
        self.composite_chosen_value = ccvs.get(action.name, 0.0)

        # R6: Update depletion level
        D_new = self.depletion_level + self.alpha_D * C - self.beta_D * (1.0 - C)
        self.depletion_level = max(0.0, min(1.0, D_new))

        # R7: Update goal activation
        # Determine if agent chose healthy (ate food with palatability < 0.5)
        chose_healthy = False
        if action.name == "eat":
            # Check last_action_result for palatability, or find food at position
            pal = last_result.get("palatability", None)
            if pal is None:
                # Fallback: check foods at current position (before move)
                ate_pos_x = last_result.get("x", px)
                ate_pos_y = last_result.get("y", py)
                food_eaten = self._food_at_pos(ate_pos_x, ate_pos_y, foods)
                if food_eaten is not None:
                    pal = food_eaten.get("palatability", 0.5)
            if pal is not None and pal < 0.5:
                chose_healthy = True

        boost = self.goal_boost if chose_healthy else 0.0
        G_new = self.goal_activation * (1.0 - self.eta_G) + boost
        self.goal_activation = max(0.0, min(1.0, G_new))

    def get_state(self) -> dict:
        return {
            "composite_chosen_value": self.composite_chosen_value,
            "health_weight": self.health_weight,
            "taste_weight": self.taste_weight,
            "dlpfc_coupling": self.dlpfc_coupling,
            "conflict_signal": self.conflict_signal,
            "goal_activation": self.goal_activation,
            "depletion_level": self.depletion_level,
            "q_values": dict(self.q_values),
        }
