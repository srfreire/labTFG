"""
Hierarchical Precision-Weighted Prediction Error Minimization (Gradient-Descent ODE)
Formulation: hierarchical-precision-weighted-prediction-error-minimization-gradient-descent-ode
Paradigm: predictive-coding

Two-level hierarchical generative model with ODE-based gradient descent on precision-weighted
variational free energy. Beliefs iteratively refined via prediction error minimization.
Actions selected via softmax over predicted free energy reduction.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

# Delta table for movement actions
ACTION_DELTAS = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
    "stay":       (0,  0),
    "eat":        (0,  0),
}


class HierarchicalPrecisionWeightedPredictionErrorMinimizationGradientDescentOdeModel:
    """
    Hierarchical predictive coding agent with two belief levels.

    Level-1 (mu_1): 5-dim vector encoding immediate environmental state.
    Level-2 (mu_2): scalar encoding abstract resource density context.

    Inference runs N_iter Euler gradient-descent steps each tick to minimise
    variational free energy F = 0.5*Pi_1*||eps_1||^2 + 0.5*Pi_2*||eps_2||^2
                                 - 0.5*(ln Pi_1 + ln Pi_2)
    Actions chosen via softmax over negative predicted free energy.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        kappa: float = 0.5,
        Pi_1_init: float = 2.0,
        Pi_2_init: float = 1.0,
        eta_Pi: float = 0.1,
        N_iter: int = 5,
        beta: float = 4.0,
        lam: float = 0.8,
        sigma2_init: float = 1.0,
    ):
        # Parameters
        self.kappa = kappa
        self.eta_Pi = eta_Pi
        self.N_iter = N_iter
        self.beta = beta
        self.lam = lam
        self.sigma2_init = sigma2_init

        # State variables
        self.s = [0.5, 0.5, 0.0, 0.0, 1.0]          # sensory observation (5-dim)
        self.mu_1 = [0.5, 0.5, 0.0, 0.0, 1.0]        # level-1 belief (5-dim)
        self.mu_2 = 0.5                                # level-2 belief (scalar)
        self.eps_1 = [0.0, 0.0, 0.0, 0.0, 0.0]       # level-1 prediction error
        self.eps_2 = [0.0, 0.0, 0.0, 0.0, 0.0]       # level-2 prediction error
        self.Pi_1 = Pi_1_init                          # level-1 precision
        self.Pi_2 = Pi_2_init                          # level-2 precision
        self.F = 0.0                                   # variational free energy
        self.a = "stay"                                # last selected action

        # Q-values: negative predicted free energy per action (cached)
        self.q_values: dict = {a: 0.0 for a in ACTIONS}

    # ------------------------------------------------------------------
    # Helper: sensory encoding
    # ------------------------------------------------------------------

    def _encode_sensory(self, perception: dict) -> list:
        """Encode perception dict into 5-dim normalised sensory vector."""
        x = perception["x"]
        y = perception["y"]
        gw = perception["grid_width"]
        gh = perception["grid_height"]
        food_sources = perception.get("resources", {}).get("food", [])

        # Food at current position
        food_here = 1.0 if any(
            f["x"] == x and f["y"] == y for f in food_sources
        ) else 0.0

        # Nearby food count (Manhattan distance ≤ 3)
        nearby = [f for f in food_sources if abs(f["x"] - x) + abs(f["y"] - y) <= 3]
        max_food = max(len(food_sources), 1)
        nearby_count_norm = len(nearby) / max_food

        # Average Manhattan distance to all food (normalised)
        if food_sources:
            avg_dist = sum(
                abs(f["x"] - x) + abs(f["y"] - y) for f in food_sources
            ) / len(food_sources)
            avg_dist_norm = avg_dist / (gw + gh)
        else:
            avg_dist_norm = 1.0

        return [
            x / max(gw, 1),
            y / max(gh, 1),
            nearby_count_norm,
            food_here,
            min(avg_dist_norm, 1.0),
        ]

    # ------------------------------------------------------------------
    # Helper: dot product
    # ------------------------------------------------------------------

    @staticmethod
    def _dot(a: list, b: list) -> float:
        return sum(ai * bi for ai, bi in zip(a, b))

    # ------------------------------------------------------------------
    # Helper: vector operations
    # ------------------------------------------------------------------

    @staticmethod
    def _vec_add(a: list, b: list) -> list:
        return [ai + bi for ai, bi in zip(a, b)]

    @staticmethod
    def _vec_sub(a: list, b: list) -> list:
        return [ai - bi for ai, bi in zip(a, b)]

    @staticmethod
    def _vec_scale(v: list, s: float) -> list:
        return [vi * s for vi in v]

    @staticmethod
    def _clip_scalar(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _clip_vec(v: list, lo: float, hi: float) -> list:
        return [max(lo, min(hi, vi)) for vi in v]

    # ------------------------------------------------------------------
    # Helper: generative model
    # ------------------------------------------------------------------

    def _g2_pred(self, mu_1: list, mu_2: float) -> list:
        """Level-2 top-down prediction of level-1 state.
        Position dims pass through; resource dims predicted from mu_2."""
        return [mu_1[0], mu_1[1], mu_2, mu_2, 1.0 - mu_2]

    # ------------------------------------------------------------------
    # Helper: inference loop
    # ------------------------------------------------------------------

    def _run_inference(self, s: list) -> tuple:
        """
        Run N_iter Euler gradient-descent steps on free energy.
        Returns (mu_1, mu_2, eps_1, eps_2) after inference.
        """
        mu_1 = list(self.mu_1)
        mu_2 = self.mu_2

        eps_1 = [0.0] * 5
        eps_2 = [0.0] * 5

        for _ in range(self.N_iter):
            # R1: level-1 prediction error (g_1 = identity)
            eps_1 = self._vec_sub(s, mu_1)

            # R2: level-2 prediction error
            g2 = self._g2_pred(mu_1, mu_2)
            eps_2 = self._vec_sub(mu_1, g2)

            # R4: level-1 belief update
            # dmu_1 = kappa * (Pi_1 * eps_1 - Pi_2 * eps_2)
            term1 = self._vec_scale(eps_1, self.Pi_1)
            term2 = self._vec_scale(eps_2, self.Pi_2)
            dmu_1 = self._vec_scale(self._vec_sub(term1, term2), self.kappa)
            mu_1 = self._clip_vec(self._vec_add(mu_1, dmu_1), 0.0, 1.0)

            # R5: level-2 belief update
            # dg2/dmu_2 = [0, 0, 1, 1, -1]
            dg2_dmu2 = [0.0, 0.0, 1.0, 1.0, -1.0]
            dmu_2 = self.kappa * self.Pi_2 * self._dot(dg2_dmu2, eps_2)
            mu_2 = self._clip_scalar(mu_2 + dmu_2, 0.0, 1.0)

        return mu_1, mu_2, eps_1, eps_2

    # ------------------------------------------------------------------
    # Helper: predict sensory outcome of an action
    # ------------------------------------------------------------------

    def _predict_sensory(
        self,
        action_name: str,
        perception: dict,
        food_sources: list,
    ) -> list:
        """Predict the sensory vector that would result from taking action."""
        x = perception["x"]
        y = perception["y"]
        gw = perception["grid_width"]
        gh = perception["grid_height"]

        dx, dy = ACTION_DELTAS[action_name]
        nx = max(0, min(gw - 1, x + dx))
        ny = max(0, min(gh - 1, y + dy))

        # For eat: same position, predict food consumed (food_here → 1.0)
        if action_name == "eat":
            food_here = 1.0
            # Remaining food after eating (remove one food at current pos)
            remaining = [f for f in food_sources if not (f["x"] == x and f["y"] == y)]
            if not remaining:
                # No food to eat – predict same sensory
                nearby = [f for f in food_sources if abs(f["x"] - nx) + abs(f["y"] - ny) <= 3]
                max_food = max(len(food_sources), 1)
                nearby_count_norm = len(nearby) / max_food
                avg_dist_norm = 1.0
            else:
                max_food = max(len(food_sources), 1)
                nearby = [f for f in remaining if abs(f["x"] - nx) + abs(f["y"] - ny) <= 3]
                nearby_count_norm = len(nearby) / max_food
                avg_dist = sum(abs(f["x"] - nx) + abs(f["y"] - ny) for f in remaining) / len(remaining)
                avg_dist_norm = min(avg_dist / (gw + gh), 1.0)
        else:
            food_here = 1.0 if any(f["x"] == nx and f["y"] == ny for f in food_sources) else 0.0
            max_food = max(len(food_sources), 1)
            nearby = [f for f in food_sources if abs(f["x"] - nx) + abs(f["y"] - ny) <= 3]
            nearby_count_norm = len(nearby) / max_food
            if food_sources:
                avg_dist = sum(abs(f["x"] - nx) + abs(f["y"] - ny) for f in food_sources) / len(food_sources)
                avg_dist_norm = min(avg_dist / (gw + gh), 1.0)
            else:
                avg_dist_norm = 1.0

        return [
            nx / max(gw, 1),
            ny / max(gh, 1),
            nearby_count_norm,
            food_here,
            avg_dist_norm,
        ]

    # ------------------------------------------------------------------
    # Helper: compute predicted free energy for each action
    # ------------------------------------------------------------------

    def _compute_action_free_energies(
        self,
        perception: dict,
        mu_1: list,
        eps_2: list,
    ) -> dict:
        """Compute predicted F for each candidate action (R7)."""
        food_sources = perception.get("resources", {}).get("food", [])
        x = perception["x"]
        y = perception["y"]
        food_here = any(f["x"] == x and f["y"] == y for f in food_sources)

        F_pred = {}
        eps_2_sq = self._dot(eps_2, eps_2)
        level2_term = 0.5 * self.Pi_2 * eps_2_sq

        for act in ACTIONS:
            if act == "eat" and not food_here:
                F_pred[act] = 1e6  # strongly disfavour impossible eat
                continue
            s_pred = self._predict_sensory(act, perception, food_sources)
            eps_pred = self._vec_sub(s_pred, mu_1)
            F_pred[act] = 0.5 * self.Pi_1 * self._dot(eps_pred, eps_pred) + level2_term

        return F_pred

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: Select action based on current beliefs.
        Encodes sensory vector, runs inference loop, computes predicted
        free energies, selects action via softmax.
        """
        # Encode sensory vector
        s = self._encode_sensory(perception)

        # Run inference to get refined beliefs (but do NOT mutate self yet)
        mu_1, mu_2, eps_1, eps_2 = self._run_inference(s)

        # Compute predicted free energy per action (R7)
        F_pred = self._compute_action_free_energies(perception, mu_1, eps_2)

        # Softmax over negative predicted free energy (R8)
        acts = list(F_pred.keys())
        neg_F = [-F_pred[a] for a in acts]
        max_val = max(neg_F)
        exp_vals = [math.exp(self.beta * (v - max_val)) for v in neg_F]
        total = sum(exp_vals)
        probs = [e / total for e in exp_vals]

        # Sample from distribution
        r = random.random()
        cumulative = 0.0
        selected = acts[-1]
        for act, prob in zip(acts, probs):
            cumulative += prob
            if r <= cumulative:
                selected = act
                break

        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: Update all state variables after action execution.
        1. Apply reward-based precision modulation.
        2. Re-encode sensory from new_perception.
        3. Run N_iter inference iterations.
        4. Adapt precisions (R6).
        5. Compute free energy (R3).
        6. Cache q_values.
        """
        # Reward-based precision modulation
        if reward > 0:
            # Successful prediction → boost level-1 precision
            self.Pi_1 = self._clip_scalar(self.Pi_1 * 1.1, 0.01, 100.0)
        elif action.name == "eat" and reward == 0:
            # Failed eat → reduce precision
            self.Pi_1 = self._clip_scalar(self.Pi_1 * 0.9, 0.01, 100.0)

        # Re-encode sensory from new perception
        s = self._encode_sensory(new_perception)
        self.s = s

        # Run inference loop on new perception
        mu_1, mu_2, eps_1, eps_2 = self._run_inference(s)

        # Store updated beliefs and prediction errors
        self.mu_1 = mu_1
        self.mu_2 = mu_2
        self.eps_1 = eps_1
        self.eps_2 = eps_2

        # R6: Precision adaptation
        err_sq_1 = self._dot(eps_1, eps_1)
        self.Pi_1 = self._clip_scalar(
            self.Pi_1 + self.eta_Pi * (1.0 / (err_sq_1 + self.sigma2_init) - self.Pi_1),
            0.01, 100.0
        )
        err_sq_2 = self._dot(eps_2, eps_2)
        self.Pi_2 = self._clip_scalar(
            self.Pi_2 + self.eta_Pi * (1.0 / (err_sq_2 + self.sigma2_init) - self.Pi_2),
            0.01, 100.0
        )

        # R3: Variational free energy
        self.F = (
            0.5 * self.Pi_1 * err_sq_1
            + 0.5 * self.Pi_2 * err_sq_2
            - 0.5 * (math.log(max(self.Pi_1, 1e-9)) + math.log(max(self.Pi_2, 1e-9)))
        )

        # Store action
        self.a = action.name

        # Cache q_values: negative predicted free energy for each action
        F_pred = self._compute_action_free_energies(new_perception, self.mu_1, self.eps_2)
        self.q_values = {a: -F_pred[a] for a in ACTIONS}

    def get_state(self) -> dict:
        """Return full state snapshot including q_values."""
        return {
            "s": list(self.s),
            "mu_1": list(self.mu_1),
            "mu_2": self.mu_2,
            "eps_1": list(self.eps_1),
            "eps_2": list(self.eps_2),
            "Pi_1": self.Pi_1,
            "Pi_2": self.Pi_2,
            "F": self.F,
            "a": self.a,
            "q_values": dict(self.q_values),
        }
