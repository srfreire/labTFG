"""
ODE-Based Dynamic Attribute Valuation with Cognitive Control
============================================================
Formulation ID: ode-based-dynamic-attribute-valuation-with-cognitive-control
Paradigm:       attribute-based-value-computation

Continuous-time ODE system (Euler-discretized) where attribute weights, hunger
state, and a cognitive control variable co-evolve.  The cognitive control
variable K represents dlPFC engagement that dynamically up-weights abstract /
quality attributes.  A Q-learning component captures environmental structure
and is blended with attribute-based values for action selection.

References
----------
Rangel (2013) Nature Neuroscience 16, 1717-1724.
Rangel, Camerer & Montague (2008) Nature Reviews Neuroscience 9, 545-556.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


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

def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


def _find_nearest_food(
    nx: int, ny: int, food_list: List[dict]
) -> Optional[dict]:
    """Return the food dict closest to (nx, ny), or None if food_list is empty."""
    best: Optional[dict] = None
    best_d = float("inf")
    for f in food_list:
        d = _manhattan(nx, ny, f["x"], f["y"])
        if d < best_d:
            best_d = d
            best = f
    return best


def _softmax_sample(scores: Dict[str, float], beta: float, rng: random.Random) -> str:
    """Numerically stable softmax sampling."""
    keys = list(scores.keys())
    logits = [beta * scores[k] for k in keys]
    max_logit = max(logits)
    exps = [math.exp(l - max_logit) for l in logits]
    total = sum(exps)
    probs = [e / total for e in exps]
    r = rng.random()
    cumulative = 0.0
    for k, p in zip(keys, probs):
        cumulative += p
        if r <= cumulative:
            return k
    return keys[-1]


# ---------------------------------------------------------------------------
# Candidate actions & movement deltas
# ---------------------------------------------------------------------------

_ACTIONS: List[str] = [
    "move_up", "move_down", "move_left", "move_right", "stay", "eat"
]
_DELTAS: Dict[str, Tuple[int, int]] = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": ( 1, 0),
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class OdeBasedDynamicAttributeValuationWithCognitiveControlModel:
    """
    DecisionModel implementing ODE-based dynamic attribute valuation with
    cognitive control (dlPFC depletion-recovery dynamics).

    Public interface
    ----------------
    decide(perception)                    -> Action
    update(action, reward, new_perception) -> None
    get_state()                            -> dict
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        # --- parameters from spec ---
        eta_H: float = 0.01,
        R_food: float = 0.3,
        tau_K: float = 50.0,
        K_0: float = 0.5,
        c_K: float = 0.02,
        phi: float = 1.5,
        tau_w: float = 5.0,
        beta: float = 5.0,
        alpha_Q: float = 0.1,
        gamma: float = 0.9,
        seed: Optional[int] = None,
    ) -> None:
        # --- parameters ---
        self.eta_H = eta_H
        self.R_food = R_food
        self.tau_K = tau_K
        self.K_0 = K_0
        self.c_K = c_K
        self.phi = phi
        self.tau_w = tau_w
        self.beta = beta
        self.alpha_Q = alpha_Q
        self.gamma = gamma

        # --- state variables (initial values from spec) ---
        self.H_t: float = 0.5           # hunger
        self.K_t: float = 0.5           # cognitive control
        self.w_imm: float = 0.5         # immediate weight
        self.w_abs: float = 0.5         # abstract weight
        self.w_imm_star: float = 0.5    # immediate weight target
        self.w_abs_star: float = 0.5    # abstract weight target
        self.V_o: float = 0.0           # option value (last computed)
        self.a_imm: float = 0.0         # immediate attribute value
        self.a_abs: float = 0.0         # abstract attribute value

        # --- Q-table: keys = (state_key, action_name) ---
        self._Q: Dict[Tuple[Tuple[int, int], str], float] = {}

        # --- cached q_values (blended U_a) for get_state() ---
        self._q_values: Dict[str, float] = {a: 0.0 for a in _ACTIONS}

        # --- last decide perception (for update's R9 old-state) ---
        self._last_perception: Optional[dict] = None
        self._last_action_name: str = "stay"

        # --- RNG ---
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_Q(self, state_key: Tuple[int, int], action: str) -> float:
        return self._Q.get((state_key, action), 0.0)

    def _compute_action_scores(
        self,
        pos: Tuple[int, int],
        food_list: List[dict],
        grid_w: int,
        grid_h: int,
    ) -> Dict[str, float]:
        """
        Compute blended U_a scores for every candidate action given current
        weights.  Pure computation — no state mutation.
        """
        max_dist = grid_w + grid_h - 2
        state_key = pos
        food_at_pos = [f for f in food_list if f["x"] == pos[0] and f["y"] == pos[1]]

        scores: Dict[str, float] = {}
        for a in _ACTIONS:
            # --- R5: attribute values ---
            if a == "eat":
                if food_at_pos:
                    a_imm_a = 1.0
                    palat = food_at_pos[0]["palatability"]
                    a_abs_a = 2.0 * (palat - 0.1) / 0.9 - 1.0
                else:
                    a_imm_a = 0.0
                    a_abs_a = 0.0
            elif a == "stay":
                a_imm_a = 0.0
                a_abs_a = 0.0
            else:
                dx, dy = _DELTAS[a]
                nx = _clip(pos[0] + dx, 0, grid_w - 1)
                ny = _clip(pos[1] + dy, 0, grid_h - 1)
                nearest = _find_nearest_food(nx, ny, food_list)
                if nearest and max_dist > 0:
                    dist = _manhattan(nx, ny, nearest["x"], nearest["y"])
                    a_imm_a = 1.0 - dist / max_dist
                    palat = nearest["palatability"]
                    a_abs_a = 2.0 * (palat - 0.1) / 0.9 - 1.0
                else:
                    a_imm_a = 0.0
                    a_abs_a = 0.0

            # --- R6: option value ---
            V_o_a = self.w_imm * a_imm_a + self.w_abs * a_abs_a

            # --- R7: blended value ---
            Q_val = self._get_Q(state_key, a)
            U_a = 0.5 * V_o_a + 0.5 * Q_val
            scores[a] = U_a

        return scores

    # ------------------------------------------------------------------
    # decide  (READ-ONLY — no state mutation)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Select an action using current (pre-update) state.
        NOTE: ODE dynamics are applied in update(), not here.
        """
        food_list: List[dict] = perception.get("resources", {}).get("food", [])
        pos = (perception["x"], perception["y"])
        grid_w: int = perception["grid_width"]
        grid_h: int = perception["grid_height"]

        # Compute scores using CURRENT (un-updated) weights
        scores = self._compute_action_scores(pos, food_list, grid_w, grid_h)

        # Cache for get_state()
        self._q_values = dict(scores)

        # R8: softmax action selection
        selected = _softmax_sample(scores, self.beta, self._rng)

        # Cache perception for update()
        self._last_perception = perception
        self._last_action_name = selected

        return Action(name=selected)

    # ------------------------------------------------------------------
    # update  (ALL state mutation goes here)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all ODE rules (R1-R4) and Q-learning update (R9).
        Called after action is executed and reward observed.
        """
        # --- R1: Hunger dynamics ---
        last_result = new_perception.get("last_action_result", {})
        consumed = last_result.get("consumed", False)
        ate = 1 if (action.name == "eat" and (consumed or reward > 0)) else 0
        self.H_t = _clip(self.H_t + self.eta_H - self.R_food * ate, 0.0, 1.0)

        # --- R2: Cognitive control dynamics ---
        self.K_t = _clip(
            self.K_t + (self.K_0 - self.K_t) / self.tau_K - self.c_K,
            0.0, 1.0
        )

        # --- R3: Compute equilibrium weight targets ---
        denom = 2.0 + self.H_t + self.phi * self.K_t
        self.w_imm_star = (1.0 + self.H_t) / denom
        self.w_abs_star = (1.0 + self.phi * self.K_t) / denom

        # --- R4: Smooth weight tracking (Euler ODE step) ---
        self.w_imm = self.w_imm + (self.w_imm_star - self.w_imm) / self.tau_w
        self.w_abs = self.w_abs + (self.w_abs_star - self.w_abs) / self.tau_w

        # --- R9: Q-learning TD(0) update ---
        old_perception = self._last_perception
        if old_perception is not None:
            state_key = (old_perception["x"], old_perception["y"])
            new_state_key = (new_perception["x"], new_perception["y"])

            max_Q_next = max(
                self._get_Q(new_state_key, a) for a in _ACTIONS
            )
            current_Q = self._get_Q(state_key, action.name)
            td_target = reward + self.gamma * max_Q_next
            self._Q[(state_key, action.name)] = (
                current_Q + self.alpha_Q * (td_target - current_Q)
            )

        # Recompute q_values scores with updated weights for next get_state()
        food_list: List[dict] = new_perception.get("resources", {}).get("food", [])
        pos = (new_perception["x"], new_perception["y"])
        grid_w: int = new_perception["grid_width"]
        grid_h: int = new_perception["grid_height"]
        self._q_values = self._compute_action_scores(pos, food_list, grid_w, grid_h)

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "H_t":          self.H_t,
            "K_t":          self.K_t,
            "w_imm":        self.w_imm,
            "w_abs":        self.w_abs,
            "w_imm_star":   self.w_imm_star,
            "w_abs_star":   self.w_abs_star,
            "V_o":          self.V_o,
            "a_imm":        self.a_imm,
            "a_abs":        self.a_abs,
            "q_values":     dict(self._q_values),
        }
