"""
Homeostatic Reinforcement Learning (HRL) with Drive-Reduction Reward
Formulation: homeostatic-reinforcement-learning-hrl-with-drive-reduction-reward
Paradigm: homeostatic-regulation

Implements tabular Q-learning where reward = drive reduction, per
Keramati & Gutkin (2014). Energy decays each step and is restored by
eating food. Drive is |h - h*|^n. Q-table maps (x, y, energy_bin) →
action values; softmax selection with inverse temperature beta.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# All possible action names (used to initialise q_values keys)
ALL_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]


class HomeostaticReinforcementLearningHrlWithDriveReductionRewardModel:
    """
    Homeostatic Reinforcement Learning with Drive-Reduction Reward.

    Variables
    ---------
    h        : energy_level ∈ [0, 1]
    h_star   : setpoint (also used as parameter)
    D        : drive = |h - h_star|^n
    r        : reward (drive reduction from last step)
    Q        : action-value table  {(state_tuple, action_name): float}
    delta    : TD error from last update
    s        : current discretised state  (x, y, energy_bin)

    Parameters
    ----------
    n              : drive_exponent            (default 2)
    c_dec          : energy_decay_rate         (default 0.02)
    c_eat          : energy_gain_from_eating   (default 0.3)
    c_move         : movement_energy_cost      (default 0.005)
    gamma          : discount_factor           (default 0.95)
    alpha          : learning_rate             (default 0.1)
    beta           : inverse_temperature       (default 5.0)
    n_energy_bins  : energy_discretisation_bins (default 10)
    """

    def __init__(
        self,
        setpoint: float = 0.8,
        drive_exponent: int = 2,
        energy_decay_rate: float = 0.02,
        energy_gain_from_eating: float = 0.3,
        movement_energy_cost: float = 0.005,
        discount_factor: float = 0.95,
        learning_rate: float = 0.1,
        inverse_temperature: float = 5.0,
        energy_discretisation_bins: int = 10,
        rng_seed: Optional[int] = None,
    ) -> None:
        # --- Parameters ---
        self.h_star: float = setpoint
        self.n: int = drive_exponent
        self.c_dec: float = energy_decay_rate
        self.c_eat: float = energy_gain_from_eating
        self.c_move: float = movement_energy_cost
        self.gamma: float = discount_factor
        self.alpha: float = learning_rate
        self.beta: float = inverse_temperature
        self.n_energy_bins: int = energy_discretisation_bins

        # --- State variables ---
        self.h: float = 0.8           # energy_level
        self.D: float = 0.0           # drive
        self.r: float = 0.0           # reward
        self.delta: float = 0.0       # TD error
        self.s: Optional[Tuple] = None  # discretised state

        # --- Q-table: {(state_tuple, action_str): float} ---
        self.Q: Dict[Tuple, float] = {}

        # --- q_values for get_state(): flat {action_str: float} for CURRENT state ---
        self.q_values: Dict[str, float] = {a: 0.0 for a in ALL_ACTIONS}

        # --- RNG ---
        self._rng = random.Random(rng_seed)

        # --- Bookkeeping for update() ---
        self._last_s: Optional[Tuple] = None   # state when decide() was called
        self._last_action_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _energy_bin(self, h: float) -> int:
        """Discretise energy value into integer bin."""
        raw = int(h * self.n_energy_bins)
        return max(0, min(raw, self.n_energy_bins - 1))

    def _discretise_state(self, perception: dict) -> Tuple:
        """Return (x, y, energy_bin) tuple."""
        x = perception["x"]
        y = perception["y"]
        ebin = self._energy_bin(self.h)
        return (x, y, ebin)

    def _drive(self, h: float) -> float:
        """D = |h - h*|^n"""
        return abs(h - self.h_star) ** self.n

    def _q_get(self, state: Tuple, action: str) -> float:
        return self.Q.get((state, action), 0.0)

    def _softmax_sample(self, actions: list, state: Tuple) -> str:
        """Numerically-stable softmax over Q-values, returns sampled action."""
        logits = [self.beta * self._q_get(state, a) for a in actions]
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        sum_exp = sum(exp_logits)
        probs = [e / sum_exp for e in exp_logits]

        # Weighted random choice
        r = self._rng.random()
        cumulative = 0.0
        for a, p in zip(actions, probs):
            cumulative += p
            if r <= cumulative:
                return a
        return actions[-1]  # fallback for floating-point rounding

    def _available_actions(self, perception: dict) -> list:
        """Build list of available actions for this perception."""
        food_here = any(
            f["x"] == perception["x"] and f["y"] == perception["y"]
            for f in perception.get("resources", {}).get("food", [])
        )
        actions = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here:
            actions.append("eat")
        return actions

    def _refresh_q_values(self, state: Tuple, available_actions: list) -> None:
        """Update the flat q_values dict for get_state()."""
        for a in ALL_ACTIONS:
            self.q_values[a] = self._q_get(state, a)

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """READ-ONLY: select an action via softmax over Q-values."""
        # Compute current discretised state (uses self.h, not modified here)
        s = self._discretise_state(perception)
        self._last_s = s  # cache for update()

        # Determine available actions
        available = self._available_actions(perception)

        # Softmax action selection (R6)
        chosen = self._softmax_sample(available, s)
        self._last_action_name = chosen

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """WRITE: apply energy dynamics, compute drive-reduction reward, update Q-table."""
        last_action_result = new_perception.get("last_action_result", {})
        action_name = action.name

        # ---- R1: Energy dynamics ----
        moved = 1 if action_name in ("move_up", "move_down", "move_left", "move_right") else 0
        ate = 1 if (action_name == "eat" and last_action_result.get("consumed", False)) else 0

        h_old = self.h
        h_new = self.h - self.c_dec - self.c_move * moved + self.c_eat * ate
        h_new = max(0.0, min(1.0, h_new))  # clip to [0,1]
        self.h = h_new

        # ---- R2: Drive update ----
        self.D = self._drive(self.h)

        # ---- R3: Drive-reduction reward ----
        D_old = self._drive(h_old)
        D_new = self._drive(h_new)
        self.r = D_old - D_new

        # ---- Discretise new state ----
        s_new = self._discretise_state(new_perception)
        s_old = self._last_s if self._last_s is not None else s_new

        # ---- R4: TD error ----
        # max Q over all actions in new state
        max_q_new = max(self._q_get(s_new, a) for a in ALL_ACTIONS)
        self.delta = self.r + self.gamma * max_q_new - self._q_get(s_old, action_name)

        # ---- R5: Q-value update ----
        key = (s_old, action_name)
        self.Q[key] = self._q_get(s_old, action_name) + self.alpha * self.delta

        # ---- Update current state ----
        self.s = s_new

        # ---- Refresh q_values for get_state() ----
        all_available_new = self._available_actions(new_perception)
        self._refresh_q_values(s_new, all_available_new)

    def get_state(self) -> dict:
        """Return full snapshot of model state including q_values."""
        return {
            "h": self.h,
            "h_star": self.h_star,
            "D": self.D,
            "r": self.r,
            "delta": self.delta,
            "s": self.s,
            "q_values": dict(self.q_values),
            # Parameters
            "n": self.n,
            "c_dec": self.c_dec,
            "c_eat": self.c_eat,
            "c_move": self.c_move,
            "gamma": self.gamma,
            "alpha": self.alpha,
            "beta": self.beta,
            "n_energy_bins": self.n_energy_bins,
        }
