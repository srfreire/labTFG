"""
Hormonal Modulation with Softmax Reinforcement Learning Model
=============================================================
A model-free Q-learning agent whose action selection is modulated by simulated
ghrelin (orexigenic) and leptin (anorexigenic) hormone proxies.

Grounded in:
  - Rangel (2013) hormonal modulation of decision circuitry (P2, P4)
  - Jacquier (2016) ghrelin/leptin dynamics
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class HormonalModulationWithSoftmaxReinforcementLearningModel:
    """
    Q-learning agent with hormonal modulation (ghrelin/leptin) applied to food-related
    Q-values before softmax action selection.
    """

    # All possible actions the agent can take
    ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    # Food-related actions (always modulated by M)
    FOOD_ACTIONS = {"eat"}

    def __init__(
        self,
        # Parameters
        alpha_E: float = 0.01,
        c_food: float = 0.3,
        lambda_G: float = 0.03,
        kappa_G: float = 0.5,
        k_L: float = 1.0,
        w_G: float = 2.0,
        w_L: float = 2.0,
        alpha: float = 0.1,
        gamma: float = 0.9,
        beta: float = 5.0,
        r_food: float = 1.0,
        c_step: float = -0.02,
        seed: int = None,
    ):
        # --- Parameters ---
        self.alpha_E = alpha_E
        self.c_food = c_food
        self.lambda_G = lambda_G
        self.kappa_G = kappa_G
        self.k_L = k_L
        self.w_G = w_G
        self.w_L = w_L
        self.alpha = alpha
        self.gamma = gamma
        self.beta = beta
        self.r_food = r_food
        self.c_step = c_step

        # --- State variables (initial values from spec) ---
        self.E = 0.5          # energy_store
        self.G = 0.3          # ghrelin_proxy
        self.L = 0.5          # leptin_proxy  (= E^k_L initially)
        self.M = 1.0          # hormonal_modulator
        self.delta = 0.0      # td_error
        self.R = 0.0          # reward_signal
        self.ate = 0          # ate_flag

        # Q-table: keys are (x, y, food_at_cell, dx_sign, dy_sign, hunger_bin, action)
        self.Q: dict = {}     # action_value_table

        # For Q-learning: remember the previous (state, action) pair
        self._prev_state = None
        self._prev_action = None

        # Cache of modulated Q-values (for get_state q_values reporting)
        self._q_values: dict = {a: 0.0 for a in self.ACTIONS}

        # Random state
        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _sign(v: float) -> int:
        if v > 0:
            return 1
        elif v < 0:
            return -1
        return 0

    def _get_q(self, state_key: tuple, action: str) -> float:
        """Return Q-value for (state, action), defaulting to 0.0."""
        return self.Q.get((state_key, action), 0.0)

    def _set_q(self, state_key: tuple, action: str, value: float) -> None:
        self.Q[(state_key, action)] = self._clamp(value, -10.0, 10.0)

    def _discretize_state(self, perception: dict) -> tuple:
        """
        Encode perception into a discrete state tuple:
          (x, y, food_at_cell, dx_sign, dy_sign, hunger_bin)
        """
        x = perception["x"]
        y = perception["y"]

        food_list = perception.get("resources", {}).get("food", [])

        # Is there food at the current cell?
        food_at_cell = int(any(f["x"] == x and f["y"] == y for f in food_list))

        # Direction to nearest food (by Manhattan distance)
        nearest = self._nearest_food(x, y, food_list)
        if nearest is not None:
            dx_sign = self._sign(nearest["x"] - x)
            dy_sign = self._sign(nearest["y"] - y)
        else:
            dx_sign = 0
            dy_sign = 0

        # Hunger bin from ghrelin proxy
        hunger_bin = 0 if self.G < 0.33 else (1 if self.G < 0.67 else 2)

        return (x, y, food_at_cell, dx_sign, dy_sign, hunger_bin)

    @staticmethod
    def _nearest_food(x: int, y: int, food_list: list):
        """Return the food dict nearest to (x, y) by Manhattan distance, or None."""
        best = None
        best_dist = float("inf")
        for f in food_list:
            d = abs(f["x"] - x) + abs(f["y"] - y)
            if d < best_dist:
                best_dist = d
                best = f
        return best

    def _is_food_related(self, action: str, x: int, y: int, nearest) -> bool:
        """
        Return True if action moves the agent closer to food OR is 'eat'.
        Movement direction that decreases Manhattan distance to nearest food is food-related.
        """
        if action == "eat":
            return True
        if nearest is None:
            return False
        dx = nearest["x"] - x
        dy = nearest["y"] - y
        if action == "move_right" and dx > 0:
            return True
        if action == "move_left" and dx < 0:
            return True
        if action == "move_down" and dy > 0:
            return True
        if action == "move_up" and dy < 0:
            return True
        return False

    def _compute_modulated_qvalues(
        self, state_key: tuple, perception: dict
    ) -> dict:
        """
        Compute hormonally-modulated Q-values Q̃(s,a) for all actions.
        Food-related actions are multiplied by M; others are not.
        """
        x = perception["x"]
        y = perception["y"]
        food_list = perception.get("resources", {}).get("food", [])
        nearest = self._nearest_food(x, y, food_list)

        modulated = {}
        for a in self.ACTIONS:
            q = self._get_q(state_key, a)
            if self._is_food_related(a, x, y, nearest):
                modulated[a] = self.M * q
            else:
                modulated[a] = q
        return modulated

    def _softmax_sample(self, modulated_values: dict) -> str:
        """Numerically stable softmax sampling."""
        actions = list(modulated_values.keys())
        scores = list(modulated_values.values())
        max_score = max(scores)
        exp_scores = [math.exp(self.beta * (s - max_score)) for s in scores]
        total = sum(exp_scores)
        probs = [e / total for e in exp_scores]

        r = random.random()
        cumulative = 0.0
        for a, p in zip(actions, probs):
            cumulative += p
            if r <= cumulative:
                return a
        return actions[-1]  # fallback

    # ------------------------------------------------------------------
    # DecisionModel contract
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Read-only: select an action using hormonally-modulated softmax over Q-values.
        State is NOT modified here.
        """
        state_key = self._discretize_state(perception)
        modulated = self._compute_modulated_qvalues(state_key, perception)
        selected = self._softmax_sample(modulated)
        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all rules (R1–R7) and update internal state.
        Called AFTER the action has been executed in the environment.
        """
        # ---- R1/R2: Determine ate_flag from last_action_result ----
        last_result = new_perception.get("last_action_result", {})
        # Eating is successful when the result indicates a resource was consumed
        ate = 0
        if action.name == "eat":
            # env sets success=True and/or consumed=True / resource_consumed key
            if (
                last_result.get("success", False)
                or last_result.get("consumed", False)
                or last_result.get("resource_consumed", False)
            ):
                ate = 1
        self.ate = ate

        # ---- R1: Energy dynamics ----
        self.E = self._clamp(self.E - self.alpha_E + self.c_food * ate, 0.0, 1.0)

        # ---- R2: Ghrelin dynamics ----
        self.G = self._clamp(self.G + self.lambda_G - self.kappa_G * ate, 0.0, 1.0)

        # ---- R3: Leptin proxy ----
        self.L = self.E ** self.k_L

        # ---- R4: Hormonal modulator ----
        self.M = (1.0 + self.w_G * self.G) / (1.0 + self.w_L * self.L)

        # ---- R5: Compute reward signal ----
        if ate == 1:
            self.R = self.M * self.r_food
        else:
            self.R = self.c_step

        # ---- R6: Q-learning TD update ----
        # Discretize the NEW state (after action)
        new_state_key = self._discretize_state(new_perception)

        # Maximum Q-value in new state (over all actions, unmodulated per standard Q-learning)
        max_q_next = max(self._get_q(new_state_key, a) for a in self.ACTIONS)

        if self._prev_state is not None and self._prev_action is not None:
            prev_q = self._get_q(self._prev_state, self._prev_action)
            self.delta = self.R + self.gamma * max_q_next - prev_q
            new_q = prev_q + self.alpha * self.delta
            self._set_q(self._prev_state, self._prev_action, new_q)

        # ---- Store current (state, action) for next step's update ----
        # Current state before update was the state we decided from
        # We discretize from new_perception for consistency — the "current" state
        # for the NEXT update is the new_state_key
        self._prev_state = new_state_key
        self._prev_action = action.name

        # ---- Update cached q_values for get_state() reporting ----
        # Report modulated Q-values at the new state
        modulated = self._compute_modulated_qvalues(new_state_key, new_perception)
        self._q_values = {a: float(modulated[a]) for a in self.ACTIONS}

    def get_state(self) -> dict:
        """Return current internal state including q_values."""
        return {
            "energy_store": self.E,
            "ghrelin_proxy": self.G,
            "leptin_proxy": self.L,
            "hormonal_modulator": self.M,
            "td_error": self.delta,
            "reward_signal": self.R,
            "ate_flag": self.ate,
            "q_table_size": len(self.Q),
            "q_values": dict(self._q_values),
        }
