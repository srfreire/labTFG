"""
Interoceptive Active Inference (IAI) with Free-Energy Minimisation
==================================================================
Probabilistic Bayesian framework implementing the Free Energy Principle
(Friston 2010) combined with a Kalman-filter interoceptive inference model
(Petzschner et al. 2021). The agent:
  1. Infers its true energy via Kalman filtering on noisy interoceptive signals.
  2. Evaluates actions by computing Expected Free Energy = pragmatic + epistemic value.
  3. Selects actions via softmax over -G (lower free energy = higher selection prob).

paradigm: homeostatic-regulation
formulation: interoceptive-active-inference-iai-with-free-energy-minimisation
"""

import math
import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Action dataclass (defined inline — no external dependencies)
# ---------------------------------------------------------------------------

@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOVE_ACTIONS = frozenset(["move_up", "move_down", "move_left", "move_right"])
_MOVE_DELTA = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
}


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Main Model
# ---------------------------------------------------------------------------

class InteroceptiveActiveInferenceIaiWithFreeEnergyMinimisationModel:
    """
    Interoceptive Active Inference model using the Free Energy Principle.

    Variables (all mutable state kept on self):
      h           - true (hidden) energy level
      mu          - posterior mean energy estimate (Kalman)
      sigma2_q    - posterior variance
      mu_prior    - prior prediction (before Kalman update)
      epsilon_int - interoceptive prediction error
      o           - interoceptive observation
      K_gain      - Kalman gain

    Parameters (fixed at construction):
      h_star, sigma2_w, sigma2_s, lambda_decay, c_eat,
      c_move, beta_G, kappa
    """

    def __init__(
        self,
        h_star: float = 0.8,
        sigma2_w: float = 0.04,
        sigma2_s: float = 0.01,
        lambda_decay: float = 0.02,
        c_eat: float = 0.3,
        c_move: float = 0.005,
        beta_G: float = 4.0,
        kappa: float = 0.5,
    ):
        # ---- Parameters ----
        self.h_star = h_star
        self.sigma2_w = sigma2_w
        self.sigma2_s = sigma2_s
        self.lambda_decay = lambda_decay
        self.c_eat = c_eat
        self.c_move = c_move
        self.beta_G = beta_G
        self.kappa = kappa

        # ---- State variables ----
        self.h: float = 0.8           # true hidden energy
        self.mu: float = 0.8          # posterior mean
        self.sigma2_q: float = 0.04   # posterior variance
        self.mu_prior: float = 0.8    # prior prediction
        self.epsilon_int: float = 0.0 # interoceptive prediction error
        self.o: float = 0.8           # noisy observation
        self.K_gain: float = 0.5      # Kalman gain
        self.G: float = 0.0           # last computed free energy (for tracking)

        # ---- Bookkeeping for next update ----
        # Track what the previous action was and whether food was consumed
        self._prev_action_name: str = "stay"
        self._prev_consumed: bool = False

        # ---- q_values cache (action → -G score; higher = better) ----
        self.q_values: dict = {
            "move_up": 0.0,
            "move_down": 0.0,
            "move_left": 0.0,
            "move_right": 0.0,
            "stay": 0.0,
            "eat": 0.0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_action_G(
        self, action_name: str, food_here: bool
    ) -> float:
        """
        Compute Expected Free Energy G for a single candidate action.
        Uses current self.mu and self.sigma2_q (READ-ONLY).

        G_a = -V_prag_a - kappa * V_epist_a          (R8)
        """
        # --- R6: Pragmatic value ---
        moved_a = 1 if action_name in _MOVE_ACTIONS else 0
        ate_a = 1 if (action_name == "eat" and food_here) else 0
        mu_pred_a = _clip(
            self.mu - self.lambda_decay
            + self.c_eat * ate_a
            - self.c_move * moved_a,
            0.0, 1.0,
        )
        V_prag_a = -((mu_pred_a - self.h_star) ** 2)

        # --- R7: Epistemic value ---
        s2_prior_a = self.sigma2_q + self.sigma2_w
        s2_post_a = (1.0 - s2_prior_a / (s2_prior_a + self.sigma2_s)) * s2_prior_a
        V_epist_a = 0.5 * math.log(s2_prior_a / max(s2_post_a, 1e-10))

        # --- R8: Expected free energy ---
        G_a = -V_prag_a - self.kappa * V_epist_a
        return G_a

    def _available_actions(self, perception: dict) -> list:
        """Build list of candidate actions for the current perception."""
        food_list = perception.get("resources", {}).get("food", [])
        px, py = perception["x"], perception["y"]
        food_here = any(
            f["x"] == px and f["y"] == py for f in food_list
        )
        actions = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here:
            actions.append("eat")
        return actions, food_here, food_list

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY. Select an action based on current model state.

        1. Determine available actions and food context.
        2. Compute G for each action using current mu and sigma2_q.
        3. Apply spatial tie-breaking bonus toward nearest food.
        4. Softmax over -beta_G * G → sample action.
        """
        px = perception["x"]
        py = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception.get("resources", {}).get("food", [])
        food_here = any(f["x"] == px and f["y"] == py for f in food_list)

        available_actions = ["move_up", "move_down", "move_left", "move_right", "stay"]
        if food_here:
            available_actions.append("eat")

        # --- Compute G for each action (R6, R7, R8) ---
        G_values: dict = {}
        for a in available_actions:
            G_values[a] = self._compute_action_G(a, food_here)

        # --- Spatial tie-breaking bonus toward nearest food (R navigation) ---
        if food_list:
            nearest = min(
                food_list,
                key=lambda f: abs(f["x"] - px) + abs(f["y"] - py),
            )
            for a in _MOVE_ACTIONS:
                if a in G_values:
                    dx, dy = _MOVE_DELTA[a]
                    nx = _clip(px + dx, 0, grid_w - 1)
                    ny = _clip(py + dy, 0, grid_h - 1)
                    d_new = abs(nx - nearest["x"]) + abs(ny - nearest["y"])
                    d_old = abs(px - nearest["x"]) + abs(py - nearest["y"])
                    # tiny bonus for reducing distance (lower G = better)
                    G_values[a] -= 0.001 * (d_old - d_new)

        # --- R9: Softmax over -beta_G * G ---
        actions_list = list(G_values.keys())
        logits = [-self.beta_G * G_values[a] for a in actions_list]
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        sum_exp = sum(exp_logits)
        probs = [e / sum_exp for e in exp_logits]

        chosen = random.choices(actions_list, weights=probs, k=1)[0]
        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE. Apply ALL rules and update internal state.

        Order:
          R1  - true energy dynamics
          R2  - interoceptive observation
          R3a - prior prediction
          R3b - prior variance propagation
          R3c - Kalman gain
          R3d - posterior update
          R4  - posterior variance update
          R5  - prediction error
          Refresh q_values cache
        """
        last_result = new_perception.get("last_action_result", {})
        consumed = bool(last_result.get("consumed", False))

        action_name = action.name

        # ---- R1: True energy dynamics (hidden state transition) ----
        moved = 1 if action_name in _MOVE_ACTIONS else 0
        ate = 1 if (action_name == "eat" and consumed) else 0
        process_noise = random.gauss(0.0, math.sqrt(self.sigma2_w))
        self.h = _clip(
            self.h - self.lambda_decay + self.c_eat * ate
            - self.c_move * moved + process_noise,
            0.0, 1.0,
        )

        # ---- R2: Interoceptive observation (noisy channel) ----
        sensory_noise = random.gauss(0.0, math.sqrt(self.sigma2_s))
        self.o = _clip(self.h + sensory_noise, 0.0, 1.0)

        # ---- R3a: Prior prediction (based on previous action) ----
        moved_prev = 1 if self._prev_action_name in _MOVE_ACTIONS else 0
        ate_prev = 1 if (self._prev_action_name == "eat" and self._prev_consumed) else 0
        self.mu_prior = _clip(
            self.mu - self.lambda_decay + self.c_eat * ate_prev
            - self.c_move * moved_prev,
            0.0, 1.0,
        )

        # ---- R3b: Prior variance propagation ----
        sigma2_q_prior = self.sigma2_q + self.sigma2_w

        # ---- R3c: Kalman gain ----
        self.K_gain = sigma2_q_prior / (sigma2_q_prior + self.sigma2_s)

        # ---- R3d: Posterior update (Bayesian state inference) ----
        self.mu = _clip(
            self.mu_prior + self.K_gain * (self.o - self.mu_prior),
            0.0, 1.0,
        )

        # ---- R4: Posterior variance update ----
        self.sigma2_q = (1.0 - self.K_gain) * sigma2_q_prior

        # ---- R5: Interoceptive prediction error ----
        self.epsilon_int = self.o - self.mu_prior

        # ---- Update bookkeeping for next cycle ----
        self._prev_action_name = action_name
        self._prev_consumed = consumed

        # ---- Refresh q_values cache using new mu/sigma2_q ----
        # Determine food context from new_perception
        food_list = new_perception.get("resources", {}).get("food", [])
        nx_pos = new_perception.get("x", 0)
        ny_pos = new_perception.get("y", 0)
        food_here_new = any(f["x"] == nx_pos and f["y"] == ny_pos for f in food_list)

        all_actions = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
        new_q: dict = {}
        for a in all_actions:
            G_a = self._compute_action_G(a, food_here_new)
            # q_value convention: higher = better → store -G
            new_q[a] = -G_a
        self.q_values = new_q

        # Track last G for reporting
        # (use stay as reference scalar)
        self.G = self._compute_action_G("stay", food_here_new)

    def get_state(self) -> dict:
        """Return a snapshot of all model state variables."""
        return {
            "h": self.h,
            "mu": self.mu,
            "sigma2_q": self.sigma2_q,
            "mu_prior": self.mu_prior,
            "epsilon_int": self.epsilon_int,
            "o": self.o,
            "K_gain": self.K_gain,
            "G": self.G,
            # Parameters (included for transparency)
            "h_star": self.h_star,
            "sigma2_w": self.sigma2_w,
            "sigma2_s": self.sigma2_s,
            "lambda_decay": self.lambda_decay,
            "c_eat": self.c_eat,
            "c_move": self.c_move,
            "beta_G": self.beta_G,
            "kappa": self.kappa,
            # q_values: -G per action (higher = better for the agent)
            "q_values": dict(self.q_values),
        }
