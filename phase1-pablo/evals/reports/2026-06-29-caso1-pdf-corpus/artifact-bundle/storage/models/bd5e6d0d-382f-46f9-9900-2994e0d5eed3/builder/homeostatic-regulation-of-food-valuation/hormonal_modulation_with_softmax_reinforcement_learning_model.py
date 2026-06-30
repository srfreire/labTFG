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

    Rules implemented:
      R1 - Energy dynamics: E = clamp(E - alpha_E + c_food*ate, 0, 1)
      R2 - Ghrelin dynamics: G = clamp(G + lambda_G - kappa_G*ate, 0, 1)
      R3 - Leptin proxy: L = E^k_L
      R4 - Hormonal modulator: M = (1+w_G*G)/(1+w_L*L)
      R5 - State-dependent reward: R = M*r_food if ate else c_step
      R6 - TD-error and Q-value update
      R7 - Modulated softmax action selection
    """

    # All possible actions the agent can take
    ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    def __init__(
        self,
        # Parameters (with spec defaults)
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
        self.E: float = 0.5      # energy_store
        self.G: float = 0.3      # ghrelin_proxy
        self.L: float = 0.5      # leptin_proxy  (= E^k_L initially)
        self.M: float = 1.0      # hormonal_modulator
        self.delta: float = 0.0  # td_error
        self.R: float = 0.0      # reward_signal
        self.ate: int = 0        # ate_flag

        # Q-table: keys are ((x, y, food_at_cell, dx_sign, dy_sign, hunger_bin), action_str)
        self.Q: dict = {}        # action_value_table

        # For Q-learning: store the (state_key, action_name) from the last decide() call.
        # This is the state we were IN when we chose the action, used in update() for TD.
        self._decide_state: tuple = None   # state_key at the time of last decide()
        self._decide_action: str = None    # action name chosen at last decide()

        # Cached modulated Q-values for get_state() reporting (updated in update())
        self._q_values: dict = {a: 0.0 for a in self.ACTIONS}

        # Seed random for reproducibility
        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        """Clamp v to [lo, hi]."""
        return max(lo, min(hi, v))

    @staticmethod
    def _sign(v: float) -> int:
        """Return +1, 0, or -1."""
        if v > 0:
            return 1
        elif v < 0:
            return -1
        return 0

    def _get_q(self, state_key: tuple, action: str) -> float:
        """Return Q(state, action), defaulting to 0.0 for unseen pairs."""
        return self.Q.get((state_key, action), 0.0)

    def _set_q(self, state_key: tuple, action: str, value: float) -> None:
        """Set Q(state, action) clamped to [-10, 10]."""
        self.Q[(state_key, action)] = self._clamp(value, -10.0, 10.0)

    @staticmethod
    def _nearest_food(x: int, y: int, food_list: list):
        """Return the food dict with smallest Manhattan distance to (x,y), or None."""
        best = None
        best_dist = float("inf")
        for f in food_list:
            d = abs(f["x"] - x) + abs(f["y"] - y)
            if d < best_dist:
                best_dist = d
                best = f
        return best

    def _discretize_state(self, perception: dict) -> tuple:
        """
        Encode perception into a discrete state tuple:
          (x, y, food_at_cell, dx_sign, dy_sign, hunger_bin)

        hunger_bin: 0 if G < 0.33, 1 if 0.33 <= G < 0.67, 2 if G >= 0.67
        Uses CURRENT self.G for hunger_bin (read-only in decide, updated in update).
        """
        x = perception["x"]
        y = perception["y"]
        food_list = perception.get("resources", {}).get("food", [])

        # Food presence at current cell
        food_at_cell = int(any(f["x"] == x and f["y"] == y for f in food_list))

        # Direction to nearest food
        nearest = self._nearest_food(x, y, food_list)
        if nearest is not None:
            dx_sign = self._sign(nearest["x"] - x)
            dy_sign = self._sign(nearest["y"] - y)
        else:
            dx_sign = 0
            dy_sign = 0

        # Hunger bin based on current ghrelin proxy
        hunger_bin = 0 if self.G < 0.33 else (1 if self.G < 0.67 else 2)

        return (x, y, food_at_cell, dx_sign, dy_sign, hunger_bin)

    def _is_food_related(self, action: str, x: int, y: int, nearest) -> bool:
        """
        R7: An action is food-related if it is 'eat' or if it moves the agent
        strictly closer to the nearest food source (decreasing Manhattan distance).
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
        R7: Compute Q̃(s, a) for all actions.
        Food-related actions: Q̃ = M * Q(s, a)
        Non-food actions:     Q̃ = Q(s, a)
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
        """
        Numerically-stable softmax sampling:
          P(a) = exp(beta * (Q̃(a) - max_Q̃)) / Z
        """
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
        return actions[-1]  # numerical fallback

    # ------------------------------------------------------------------
    # DecisionModel contract
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: Select an action using hormonally-modulated softmax over Q-values.
        Caches the current state_key and selected action for use in update().
        No physiological state (E, G, L, M) is modified here.
        """
        state_key = self._discretize_state(perception)
        modulated = self._compute_modulated_qvalues(state_key, perception)
        selected = self._softmax_sample(modulated)

        # Cache so update() knows which (state, action) to apply the TD update to
        self._decide_state = state_key
        self._decide_action = selected

        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply ALL rules and update internal state. This is the ONLY place
        state is mutated.

        Execution order:
          1. Determine ate_flag from last_action_result
          2. R1 – energy dynamics
          3. R2 – ghrelin dynamics
          4. R3 – leptin proxy
          5. R4 – hormonal modulator
          6. R5 – reward signal
          7. R6 – TD-error and Q-value update (uses _decide_state/_decide_action)
          8. Cache modulated Q-values for get_state()
        """
        # ---- Step 1: ate_flag ----
        last_result = new_perception.get("last_action_result", {})
        ate = 0
        if action.name == "eat":
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

        # ---- R5: State-dependent reward ----
        if ate == 1:
            self.R = self.M * self.r_food
        else:
            self.R = self.c_step

        # ---- R6: TD-error and Q-value update ----
        # Discretize the NEW state (s_{t+1}, after action execution)
        new_state_key = self._discretize_state(new_perception)
        max_q_next = max(self._get_q(new_state_key, a) for a in self.ACTIONS)

        # Apply TD update to Q[s_t, a_t] — the (state, action) from last decide()
        if self._decide_state is not None and self._decide_action is not None:
            prev_q = self._get_q(self._decide_state, self._decide_action)
            self.delta = self.R + self.gamma * max_q_next - prev_q
            updated_q = prev_q + self.alpha * self.delta
            self._set_q(self._decide_state, self._decide_action, updated_q)

        # ---- Cache modulated Q-values for reporting ----
        modulated = self._compute_modulated_qvalues(new_state_key, new_perception)
        self._q_values = {a: float(modulated[a]) for a in self.ACTIONS}

    def get_state(self) -> dict:
        """Return all internal state variables plus q_values for visualization."""
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
