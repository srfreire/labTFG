"""
Continuous Free-Energy Gradient Descent with Precision-Weighted Prediction Errors

Implements the core perception-action loop of interoceptive active inference:
  - Belief update via gradient descent on variational free energy F
  - Action selection via softmax over negative predicted free energy
  - No persistent Q-table; relies on real-time prediction error minimization
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _softmax(logits: Dict[str, float]) -> Dict[str, float]:
    """Numerically-stable softmax over a dict of logits."""
    keys = list(logits.keys())
    vals = [logits[k] for k in keys]
    max_v = max(vals)
    exps = [math.exp(v - max_v) for v in vals]
    total = sum(exps)
    return {k: e / total for k, e in zip(keys, exps)}


def _sample_action(probs: Dict[str, float]) -> str:
    """Sample an action name from a probability dict."""
    keys = list(probs.keys())
    cumulative = 0.0
    r = random.random()
    for k in keys:
        cumulative += probs[k]
        if r <= cumulative:
            return k
    return keys[-1]


def _manhattan(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _direction_toward(pos: Tuple[int, int], target: Tuple[int, int]) -> Optional[str]:
    """Return the single-step action that most reduces Manhattan distance."""
    dx = target[0] - pos[0]
    dy = target[1] - pos[1]
    if dx == 0 and dy == 0:
        return None  # already at target
    if abs(dx) >= abs(dy):
        return "move_right" if dx > 0 else "move_left"
    else:
        return "move_down" if dy > 0 else "move_up"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

ALL_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]


class ContinuousFreeEnergyGradientDescentWithPrecisionWeightedPredictionErrorsModel:
    """
    Active-inference agent that minimises variational free energy F:
        F = 0.5 * pi_s * eps_s² + 0.5 * pi_p * eps_p²

    Belief update (R6):
        mu ← clip(mu + kappa * (pi_s * eps_s - pi_p * eps_p), 0, 1)

    Action selection (R7-R9):
        Predict s under each action → compute F_pred → softmax(-beta * F_pred)
    """

    def __init__(
        self,
        pi_s: float = 1.0,
        pi_p: float = 2.0,
        kappa: float = 0.5,
        mu_p_value: float = 1.0,
        sigma_s: float = 0.2,
        beta: float = 5.0,
        energy_gain_eat: float = 0.3,
        c_move: float = 0.05,
        c_stay: float = 0.02,
        c_move_toward: float = 0.03,
        rng_seed: Optional[int] = None,
    ):
        # Parameters
        self.pi_s = pi_s
        self.pi_p = pi_p
        self.kappa = kappa
        self.mu_p_value = mu_p_value
        self.sigma_s = sigma_s
        self.beta = beta
        self.energy_gain_eat = energy_gain_eat
        self.c_move = c_move
        self.c_stay = c_stay
        self.c_move_toward = c_move_toward

        if rng_seed is not None:
            random.seed(rng_seed)

        # State variables (initial values from spec)
        self.s_t: float = 0.5           # interoceptive_observation
        self.mu: float = 0.5            # belief_state
        self.mu_p: float = mu_p_value   # interoceptive_prior (fixed)
        self.eps_s: float = 0.0         # sensory_prediction_error
        self.eps_p: float = 0.0         # prior_prediction_error
        self.F: float = 0.0             # variational_free_energy
        self.energy: float = 0.5        # internal_energy

        # Q-values (predicted free energies; lower = better, stored as negative F_pred)
        self.q_values: Dict[str, float] = {a: 0.0 for a in ALL_ACTIONS}

        # Bookkeeping
        self._last_action_name: str = "stay"

    # ------------------------------------------------------------------
    # decide (READ-ONLY)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Select action by evaluating predicted free energy under each candidate
        action. Uses current self.mu, self.s_t set during the last update().
        Does NOT modify any state.
        """
        x = perception["x"]
        y = perception["y"]
        food_list: List[dict] = perception.get("resources", {}).get("food", [])

        # Check for food at current position
        food_at_pos = any(
            f["x"] == x and f["y"] == y for f in food_list
        )

        # Find direction toward nearest food (for anticipatory cost reduction)
        direction_toward = None
        if food_list:
            nearest = min(food_list, key=lambda f: _manhattan((x, y), (f["x"], f["y"])))
            direction_toward = _direction_toward((x, y), (nearest["x"], nearest["y"]))

        # R7: Predict sensory outcome for each action (uses self.s_t from update)
        s_pred: Dict[str, float] = {}
        for a in ALL_ACTIONS:
            if a == "eat":
                if food_at_pos:
                    # Eating available food → energy gain
                    # Use mean palatability or default 1.0 if available
                    food_here = [f for f in food_list if f["x"] == x and f["y"] == y]
                    palatability = food_here[0].get("palatability", 1.0) if food_here else 1.0
                    s_pred[a] = _clip(self.s_t + self.energy_gain_eat * palatability, 0.0, 1.0)
                else:
                    # Failed eat → same as stay
                    s_pred[a] = self.s_t - self.c_stay
            elif a in ("move_up", "move_down", "move_left", "move_right"):
                if a == direction_toward:
                    s_pred[a] = self.s_t - self.c_move_toward
                else:
                    s_pred[a] = self.s_t - self.c_move
            else:  # stay
                s_pred[a] = self.s_t - self.c_stay

        # R8: Predicted free energy under each action
        F_pred: Dict[str, float] = {}
        for a in ALL_ACTIONS:
            eps_s_pred = s_pred[a] - self.mu
            eps_p_curr = self.mu - self.mu_p
            F_pred[a] = (
                0.5 * self.pi_s * eps_s_pred ** 2
                + 0.5 * self.pi_p * eps_p_curr ** 2
            )

        # R9: Softmax selection over negative predicted free energy
        logits = {a: -self.beta * F_pred[a] for a in ALL_ACTIONS}
        probs = _softmax(logits)
        selected = _sample_action(probs)

        return Action(name=selected)

    # ------------------------------------------------------------------
    # update (ALL state mutations here)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all rules (R1–R6) and refresh q_values using new_perception.
        """
        last_action_result = new_perception.get("last_action_result", {})
        self._last_action_name = action.name

        # R1: Internal energy dynamics
        consumed = last_action_result.get("consumed", False)
        if action.name == "eat" and consumed:
            # Get palatability from last_action_result or default
            palatability = last_action_result.get("palatability", 1.0)
            self.energy = _clip(
                self.energy + self.energy_gain_eat * palatability, 0.0, 1.0
            )
        elif action.name in ("move_up", "move_down", "move_left", "move_right"):
            self.energy = _clip(self.energy - self.c_move, 0.0, 1.0)
        else:
            # stay or failed eat
            self.energy = _clip(self.energy - self.c_stay, 0.0, 1.0)

        # R2: Noisy interoceptive observation
        noise = random.gauss(0.0, self.sigma_s)
        self.s_t = _clip(self.energy + noise, 0.0, 1.0)

        # R3: Sensory prediction error
        self.eps_s = self.s_t - self.mu

        # R4: Prior prediction error
        self.eps_p = self.mu - self.mu_p

        # R5: Variational free energy
        self.F = (
            0.5 * self.pi_s * self.eps_s ** 2
            + 0.5 * self.pi_p * self.eps_p ** 2
        )

        # R6: Belief update (gradient descent on F)
        self.mu = _clip(
            self.mu + self.kappa * (self.pi_s * self.eps_s - self.pi_p * self.eps_p),
            0.0,
            1.0,
        )

        # Refresh q_values (stored as negative F_pred; higher = better action)
        # Recompute predictions using updated s_t and mu
        x = new_perception["x"]
        y = new_perception["y"]
        food_list: List[dict] = new_perception.get("resources", {}).get("food", [])
        food_at_pos = any(f["x"] == x and f["y"] == y for f in food_list)
        direction_toward = None
        if food_list:
            nearest = min(food_list, key=lambda f: _manhattan((x, y), (f["x"], f["y"])))
            direction_toward = _direction_toward((x, y), (nearest["x"], nearest["y"]))

        for a in ALL_ACTIONS:
            if a == "eat":
                if food_at_pos:
                    food_here = [f for f in food_list if f["x"] == x and f["y"] == y]
                    palatability = food_here[0].get("palatability", 1.0) if food_here else 1.0
                    sp = _clip(self.s_t + self.energy_gain_eat * palatability, 0.0, 1.0)
                else:
                    sp = self.s_t - self.c_stay
            elif a in ("move_up", "move_down", "move_left", "move_right"):
                sp = self.s_t - self.c_move_toward if a == direction_toward else self.s_t - self.c_move
            else:
                sp = self.s_t - self.c_stay

            eps_s_pred = sp - self.mu
            eps_p_curr = self.mu - self.mu_p
            f_pred = (
                0.5 * self.pi_s * eps_s_pred ** 2
                + 0.5 * self.pi_p * eps_p_curr ** 2
            )
            # Store negative F_pred as q_value (higher = agent prefers this action)
            self.q_values[a] = -f_pred

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "s_t": self.s_t,
            "mu": self.mu,
            "mu_p": self.mu_p,
            "eps_s": self.eps_s,
            "eps_p": self.eps_p,
            "F": self.F,
            "energy": self.energy,
            "q_values": dict(self.q_values),
        }
