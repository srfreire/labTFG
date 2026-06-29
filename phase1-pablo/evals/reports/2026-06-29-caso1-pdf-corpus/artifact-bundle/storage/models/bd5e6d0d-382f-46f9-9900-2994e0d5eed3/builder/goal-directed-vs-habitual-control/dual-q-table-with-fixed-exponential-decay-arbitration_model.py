"""
Dual Q-Table with Fixed Exponential-Decay Arbitration Model

Maintains two separate Q-tables (model-free / habitual and model-based /
goal-directed) blended via a deterministic arbitration weight omega that
decays exponentially with state visit count, implementing the
overtraining-to-habit shift (Rangel, Camerer & Montague, 2008).

Paradigm : goal-directed-vs-habitual-control
Formulation : dual-q-table-with-fixed-exponential-decay-arbitration
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Action dataclass (defined inline — no external imports)
# ---------------------------------------------------------------------------

@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ACTIONS: List[str] = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
OUTCOMES: List[str] = ["food", "nofood"]

_MOVE_DELTA: Dict[str, Tuple[int, int]] = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": ( 1, 0),
}


def _softmax(values: List[float], beta: float) -> List[float]:
    """Numerically-stable softmax with inverse temperature beta."""
    scaled = [beta * v for v in values]
    max_v = max(scaled)
    exps = [math.exp(v - max_v) for v in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _next_state(
    s: Tuple[int, int],
    action: str,
    grid_width: int,
    grid_height: int,
) -> Tuple[int, int]:
    """Return clamped next state after applying a move action."""
    dx, dy = _MOVE_DELTA[action]
    nx = _clip(s[0] + dx, 0, grid_width - 1)
    ny = _clip(s[1] + dy, 0, grid_height - 1)
    return (int(nx), int(ny))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class DualQTableWithFixedExponentialDecayArbitrationModel:
    """
    Dual-system RL agent.

    * Q_MF  — model-free (habitual) Q-table, updated by TD(0).
    * Q_MB  — model-based (goal-directed) values, recomputed prospectively
               each decide() call from the learned transition model p_hat and
               current hunger-modulated desirability.
    * omega — arbitration weight = exp(-lambda_habit * N(s)), decays with
               training toward pure-habit control.
    """

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        alpha_MF: float = 0.10,
        alpha_T: float = 0.20,
        gamma: float = 0.95,
        beta: float = 5.0,
        lambda_habit: float = 0.05,
        eta: float = 0.02,
        phi: float = 0.30,
        r_food: float = 1.0,
        c_step: float = -0.01,
        seed: int | None = None,
    ) -> None:
        # Parameters
        self.alpha_MF = alpha_MF
        self.alpha_T = alpha_T
        self.gamma = gamma
        self.beta = beta
        self.lambda_habit = lambda_habit
        self.eta = eta
        self.phi = phi
        self.r_food = r_food
        self.c_step = c_step

        if seed is not None:
            random.seed(seed)

        # ---- State variables ----
        # Hunger drive  h ∈ [0, 1]
        self.h: float = 0.5

        # Model-free Q-table: (state, action) → float
        self.Q_MF: Dict[Tuple, float] = {}

        # Transition model: (state, action, outcome) → probability
        self.p_hat: Dict[Tuple, float] = {}

        # Visit counts: state → int
        self.N: Dict[Tuple[int, int], int] = {}

        # Last computed model-based values (for get_state / q_values)
        self._last_Q_MB: Dict[str, float] = {a: 0.0 for a in ACTIONS}

        # Arbitration weight (cached, updated in update())
        self.omega: float = 1.0

        # TD prediction error (last computed)
        self.delta: float = 0.0

        # q_values — cached net action values for the current state
        self.q_values: Dict[str, float] = {a: 0.0 for a in ACTIONS}

        # Cache of previous state/action used in update()
        self._prev_state: Tuple[int, int] | None = None
        self._prev_action: str | None = None

        # Grid dimensions (updated from perception)
        self._grid_width: int = 10
        self._grid_height: int = 10

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_Q_MF(self, state: Tuple[int, int], action: str) -> float:
        return self.Q_MF.get((state, action), 0.0)

    def _get_p_hat(self, state: Tuple[int, int], action: str, outcome: str) -> float:
        return self.p_hat.get((state, action, outcome), 0.5)

    def _compute_Q_MB(
        self,
        s: Tuple[int, int],
        food_here: bool,
        gw: int,
        gh: int,
    ) -> Dict[str, float]:
        """Compute model-based Q-values prospectively (R3, R2)."""
        r_D_food = self.h * self.r_food   # R2
        r_D_nofood = self.c_step           # R2

        q_mb: Dict[str, float] = {}
        for a in ACTIONS:
            if a == "eat" and food_here:
                # R3: eat at food location — probabilistic outcome
                p_food = self._get_p_hat(s, a, "food")
                q_mb[a] = p_food * r_D_food + (1.0 - p_food) * r_D_nofood
            elif a in _MOVE_DELTA:
                # R3: move — transition to next cell, bootstrap from Q_MF
                s_next = _next_state(s, a, gw, gh)
                max_qmf_next = max(
                    self._get_Q_MF(s_next, a2) for a2 in ACTIONS
                )
                q_mb[a] = self.c_step + self.gamma * max_qmf_next
            else:
                # stay / eat-with-no-food
                q_mb[a] = self.c_step
        return q_mb

    def _compute_omega(self, s: Tuple[int, int]) -> float:
        """R7: arbitration weight based on visit count."""
        return math.exp(-self.lambda_habit * self.N.get(s, 0))

    def _compute_q_net(
        self,
        s: Tuple[int, int],
        q_mb: Dict[str, float],
        omega: float,
    ) -> Dict[str, float]:
        """R8: blend model-based and model-free Q-values."""
        return {
            a: omega * q_mb[a] + (1.0 - omega) * self._get_Q_MF(s, a)
            for a in ACTIONS
        }

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY decision step.
        Computes Q_MB, blends into Q_net, and selects action via softmax.
        No state mutation here.
        """
        s: Tuple[int, int] = (perception["x"], perception["y"])
        gw: int = perception.get("grid_width", self._grid_width)
        gh: int = perception.get("grid_height", self._grid_height)

        food_list = perception.get("resources", {}).get("food", [])
        food_here: bool = any(
            f["x"] == s[0] and f["y"] == s[1] for f in food_list
        )

        # R2 + R3: compute model-based values
        q_mb = self._compute_Q_MB(s, food_here, gw, gh)

        # R7: arbitration weight
        omega = self._compute_omega(s)

        # R8: blend
        q_net = self._compute_q_net(s, q_mb, omega)

        # R9: softmax selection
        net_vals = [q_net[a] for a in ACTIONS]
        probs = _softmax(net_vals, self.beta)
        chosen = random.choices(ACTIONS, weights=probs, k=1)[0]

        return Action(name=chosen, params={"state": s, "food_here": food_here})

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE step — all state mutations happen here.
        Applies rules R1, R4, R5, R6, R7, R8, R10 and caches q_values.
        """
        # Recover previous state from the action params (set in decide)
        s: Tuple[int, int] = action.params.get("state", (0, 0))
        a_name: str = action.name
        food_here_prev: bool = action.params.get("food_here", False)

        last_result = new_perception.get("last_action_result", {})
        ate_food: bool = (a_name == "eat" and bool(last_result.get("consumed", False)))

        # R1: hunger dynamics
        self.h = _clip(self.h + self.eta - self.phi * int(ate_food), 0.0, 1.0)

        # R4: transition model update
        o_obs = "food" if ate_food else "nofood"
        for o in OUTCOMES:
            target = 1.0 if o == o_obs else 0.0
            key = (s, a_name, o)
            old_p = self.p_hat.get(key, 0.5)
            self.p_hat[key] = old_p + self.alpha_T * (target - old_p)

        # R5 + R6: TD prediction error and model-free Q update
        s_next: Tuple[int, int] = (
            new_perception["x"],
            new_perception["y"],
        )
        r_received = reward  # use env-provided reward

        max_qmf_next = max(self._get_Q_MF(s_next, a2) for a2 in ACTIONS)
        self.delta = (
            r_received
            + self.gamma * max_qmf_next
            - self._get_Q_MF(s, a_name)
        )
        self.Q_MF[(s, a_name)] = self._get_Q_MF(s, a_name) + self.alpha_MF * self.delta

        # R10: visit count increment
        self.N[s] = self.N.get(s, 0) + 1

        # Cache omega for get_state
        self.omega = self._compute_omega(s)

        # Update grid dimensions
        self._grid_width = new_perception.get("grid_width", self._grid_width)
        self._grid_height = new_perception.get("grid_height", self._grid_height)

        # Recompute Q_MB and Q_net with updated state (for q_values caching)
        s_curr: Tuple[int, int] = (new_perception["x"], new_perception["y"])
        food_list_new = new_perception.get("resources", {}).get("food", [])
        food_here_new: bool = any(
            f["x"] == s_curr[0] and f["y"] == s_curr[1] for f in food_list_new
        )

        q_mb_new = self._compute_Q_MB(
            s_curr,
            food_here_new,
            self._grid_width,
            self._grid_height,
        )
        self._last_Q_MB = q_mb_new

        omega_new = self._compute_omega(s_curr)
        q_net_new = self._compute_q_net(s_curr, q_mb_new, omega_new)
        self.q_values = {a: float(q_net_new[a]) for a in ACTIONS}

    def get_state(self) -> dict:
        return {
            "h": self.h,
            "omega": self.omega,
            "delta": self.delta,
            "Q_MF_size": len(self.Q_MF),
            "p_hat_size": len(self.p_hat),
            "N_total_visits": sum(self.N.values()),
            "q_values": dict(self.q_values),
            "last_Q_MB": dict(self._last_Q_MB),
        }
