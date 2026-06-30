"""
Uncertainty-Based Bayesian Arbitration Model
Paradigm: goal-directed-vs-habitual-control
Formulation: uncertainty-based-bayesian-arbitration

Probabilistic dual-system RL agent. Both model-free (habitual) and model-based
(goal-directed) systems maintain Gaussian posterior beliefs over action values.
Arbitration is driven by relative uncertainty (precision): omega = sigmoid(kappa *
(sigma2_MF - sigma2_MB)). High MF uncertainty → goal-directed dominates; high MB
uncertainty (or low MF uncertainty) → habitual dominates.

References:
  Rangel, Camerer & Montague (2008) Nat Rev Neurosci 9:545-556
  Rangel (2013) Nat Neurosci 16(12):1717-1724
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
OUTCOMES = ["food", "nofood"]

_MOVE_DELTAS = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
}


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _sigmoid(x):
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        e = math.exp(x)
        return e / (1.0 + e)


def _softmax(values):
    max_v = max(values)
    exps = [math.exp(v - max_v) for v in values]
    s = sum(exps)
    return [e / s for e in exps]


class UncertaintyBasedBayesianArbitrationModel:
    """
    Dual-system Bayesian arbitration model.

    Model-free system: Kalman-filter-style Bayesian TD updates.
    Model-based system: prospective computation from learned transition model.
    Arbitration: omega = sigmoid(kappa * (sigma2_MF - sigma2_MB)).
    """

    def __init__(
        self,
        sigma2_0: float = 1.0,
        mu_0: float = 0.0,
        sigma2_obs_MF: float = 0.50,
        sigma2_obs_MB: float = 0.25,
        alpha_T: float = 0.20,
        kappa: float = 3.0,
        beta: float = 5.0,
        gamma: float = 0.95,
        eta: float = 0.02,
        phi: float = 0.30,
        r_food: float = 1.0,
        c_step: float = -0.01,
    ):
        # --- Parameters ---
        self.sigma2_0 = sigma2_0
        self.mu_0 = mu_0
        self.sigma2_obs_MF = sigma2_obs_MF
        self.sigma2_obs_MB = sigma2_obs_MB
        self.alpha_T = alpha_T
        self.kappa = kappa
        self.beta = beta
        self.gamma = gamma
        self.eta = eta
        self.phi = phi
        self.r_food = r_food
        self.c_step = c_step

        # --- Internal state variables ---
        # h: hunger drive, clipped to [0, 1]
        self.h: float = 0.5

        # Model-free: Gaussian posteriors over (state, action) action values
        self.mu_MF: dict = {}       # (s, a) -> float
        self.sigma2_MF: dict = {}   # (s, a) -> float

        # Model-based: computed prospectively each step
        self.mu_MB: dict = {}       # (s, a) -> float
        self.sigma2_MB: dict = {}   # (s, a) -> float

        # Transition model: p_hat[(s, a, outcome)] -> float
        self.p_hat: dict = {}

        # Experience counts for MB uncertainty scaling
        self.N_MB: dict = {}        # (s, a) -> int

        # Arbitration weights and fused values (current step)
        self.omega: dict = {}       # (s, a) -> float
        self.mu_hat: dict = {}      # (s, a) -> float

        # q_values for get_state() — maps action name -> fused value for current state
        self.q_values: dict = {a: 0.0 for a in ACTIONS}

        # Track last state used in decide() so update() can reference it
        self._last_s = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mf_mean(self, s, a):
        return self.mu_MF.get((s, a), self.mu_0)

    def _mf_var(self, s, a):
        return self.sigma2_MF.get((s, a), self.sigma2_0)

    def _mb_mean(self, s, a):
        return self.mu_MB.get((s, a), 0.0)

    def _mb_var(self, s, a):
        return self.sigma2_MB.get((s, a), self.sigma2_0)

    def _p_hat_food(self, s, a):
        return self.p_hat.get((s, a, "food"), 0.5)

    def _apply_move(self, s, action, grid_width, grid_height):
        """Return next state after a move action, clamped to grid bounds."""
        dx, dy = _MOVE_DELTAS.get(action, (0, 0))
        nx = _clamp(s[0] + dx, 0, grid_width - 1)
        ny = _clamp(s[1] + dy, 0, grid_height - 1)
        return (nx, ny)

    def _compute_mb_values(self, s, food_here, grid_width, grid_height):
        """
        R3 + R4: Compute model-based mean and variance for all actions.
        Uses current hunger h to compute decision-time desirability.
        """
        r_D_food = self.h * self.r_food   # R2
        r_D_nofood = self.c_step          # R2

        for a in ACTIONS:
            n = self.N_MB.get((s, a), 0)
            if a == "eat" and food_here:
                # R3: eat with food present
                p_f = self._p_hat_food(s, a)
                mu = p_f * r_D_food + (1.0 - p_f) * r_D_nofood
                # R4: outcome variance + scaled observation noise
                outcome_var = (
                    p_f * (r_D_food - mu) ** 2
                    + (1.0 - p_f) * (r_D_nofood - mu) ** 2
                )
                sigma2 = outcome_var + self.sigma2_obs_MB / (1.0 + n)
            elif a in _MOVE_DELTAS:
                # R3: movement bootstraps from MF at next state
                s_next = self._apply_move(s, a, grid_width, grid_height)
                best_mf_next = max(self._mf_mean(s_next, a2) for a2 in ACTIONS)
                mu = self.c_step + self.gamma * best_mf_next
                # R4: movement MB variance
                sigma2 = self.sigma2_obs_MB / (1.0 + n)
            else:
                # stay or eat-without-food
                mu = self.c_step
                sigma2 = self.sigma2_obs_MB / (1.0 + n)

            self.mu_MB[(s, a)] = mu
            self.sigma2_MB[(s, a)] = sigma2

    def _compute_arbitration_and_fusion(self, s):
        """
        R7 + R8: Compute per-action arbitration weights and fused values.
        """
        for a in ACTIONS:
            s2_mf = self._mf_var(s, a)
            s2_mb = self._mb_var(s, a)
            # R7: sigmoid of variance difference
            w = _sigmoid(self.kappa * (s2_mf - s2_mb))
            self.omega[(s, a)] = w
            # R8: precision-weighted fusion
            self.mu_hat[(s, a)] = w * self._mb_mean(s, a) + (1.0 - w) * self._mf_mean(s, a)

    def _update_q_values(self, s):
        """Refresh the q_values dict for get_state() based on current state s."""
        for a in ACTIONS:
            self.q_values[a] = self.mu_hat.get((s, a), 0.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Read-only: select action based on current state.
        Calls MB computation then softmax selection.
        """
        x = perception["x"]
        y = perception["y"]
        s = (x, y)
        grid_width = perception["grid_width"]
        grid_height = perception["grid_height"]

        food_list = perception.get("resources", {}).get("food", [])
        food_here = any(f["x"] == x and f["y"] == y for f in food_list)

        # R3, R4: compute model-based values
        self._compute_mb_values(s, food_here, grid_width, grid_height)

        # R7, R8: compute arbitration and fused values
        self._compute_arbitration_and_fusion(s)

        # Update q_values snapshot (used by get_state before next update)
        self._update_q_values(s)

        # Remember state so update() can reference the previous state
        self._last_s = s

        # R9: softmax selection
        scores = [self.beta * self.mu_hat.get((s, a), 0.0) for a in ACTIONS]
        probs = _softmax(scores)
        chosen = random.choices(ACTIONS, weights=probs, k=1)[0]
        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all learning rules: R1, R5a-R5c, R6, R10.
        Also recomputes MB values and q_values for the new state.
        """
        # Derive previous state from _last_s (set in decide)
        s = self._last_s
        if s is None:
            # Fallback: can't update without a prior state
            return

        a_name = action.name
        last_result = new_perception.get("last_action_result", {})

        # Determine whether food was consumed
        ate_food = (a_name == "eat") and bool(last_result.get("consumed", False))
        r_received = self.r_food if ate_food else self.c_step

        # R1: Hunger dynamics
        self.h = _clamp(self.h + self.eta - self.phi * float(ate_food), 0.0, 1.0)

        # R6: Update transition model
        o_obs = "food" if ate_food else "nofood"
        for o in OUTCOMES:
            target = 1.0 if o == o_obs else 0.0
            key = (s, a_name, o)
            prev = self.p_hat.get(key, 0.5)
            self.p_hat[key] = prev + self.alpha_T * (target - prev)

        # R5a: Kalman gain
        s2_mf = self._mf_var(s, a_name)
        K = s2_mf / (s2_mf + self.sigma2_obs_MF)

        # R5b: TD target using new state
        x_new = new_perception["x"]
        y_new = new_perception["y"]
        s_next = (x_new, y_new)
        best_mf_next = max(self._mf_mean(s_next, a2) for a2 in ACTIONS)
        td_target = r_received + self.gamma * best_mf_next
        prev_mu = self._mf_mean(s, a_name)
        self.mu_MF[(s, a_name)] = prev_mu + K * (td_target - prev_mu)

        # R5c: Variance update
        self.sigma2_MF[(s, a_name)] = (1.0 - K) * s2_mf

        # R10: Increment MB experience count
        self.N_MB[(s, a_name)] = self.N_MB.get((s, a_name), 0) + 1

        # Recompute MB values and arbitration for new state (for q_values)
        grid_width = new_perception["grid_width"]
        grid_height = new_perception["grid_height"]
        food_list_new = new_perception.get("resources", {}).get("food", [])
        food_here_new = any(f["x"] == x_new and f["y"] == y_new for f in food_list_new)

        s_new = (x_new, y_new)
        self._compute_mb_values(s_new, food_here_new, grid_width, grid_height)
        self._compute_arbitration_and_fusion(s_new)
        self._update_q_values(s_new)
        self._last_s = s_new

    def get_state(self) -> dict:
        """Return current internal state snapshot."""
        return {
            "h": self.h,
            "mu_MF": dict(self.mu_MF),
            "sigma2_MF": dict(self.sigma2_MF),
            "mu_MB": dict(self.mu_MB),
            "sigma2_MB": dict(self.sigma2_MB),
            "omega": dict(self.omega),
            "mu_hat": dict(self.mu_hat),
            "p_hat": dict(self.p_hat),
            "N_MB": dict(self.N_MB),
            "q_values": dict(self.q_values),
        }
