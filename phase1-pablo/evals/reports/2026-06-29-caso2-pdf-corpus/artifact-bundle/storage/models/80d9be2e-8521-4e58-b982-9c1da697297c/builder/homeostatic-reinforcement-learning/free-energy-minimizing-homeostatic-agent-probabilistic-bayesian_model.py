"""
Free-Energy Minimizing Homeostatic Agent (Probabilistic/Bayesian)

Active inference formulation: the agent maintains a Gaussian posterior over
hunger (mu_h, sigma_h_sq) and a grid-wide resource belief map. Actions are
chosen by maximising expected free energy G(a) = G_prag(a) + w_e * G_epist(a).

References:
  Friston (2010) Free Energy Principle; Keramati & Gutkin (2014); Petzschner et al. (2021)
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class FreeEnergyMinimizingHomeostaticAgentProbabilisticBayesianModel:
    """DecisionModel that selects actions by minimising expected free energy."""

    # Candidate actions and their (dx, dy) for movement
    _ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
    _DELTA = {
        "move_up":    (0, -1),
        "move_down":  (0,  1),
        "move_left":  (-1, 0),
        "move_right": (1,  0),
    }

    def __init__(
        self,
        grid_width: int = 10,
        grid_height: int = 10,
        h_star: float = 0.0,
        sigma_p: float = 1.0,
        sigma_obs: float = 0.5,
        sigma_process_sq: float = 0.01,
        K: float = 3.0,
        lambda_drift: float = 0.1,
        h_max: float = 10.0,
        beta_G: float = 5.0,
        w_e: float = 0.3,
        kappa: float = 0.05,
        initial_resource_prior: float = 0.05,
    ):
        # --- Parameters ---
        self.h_star = h_star
        self.sigma_p = sigma_p
        self.sigma_obs = sigma_obs
        self.sigma_process_sq = sigma_process_sq
        self.K = K
        self.lambda_drift = lambda_drift
        self.h_max = h_max
        self.beta_G = beta_G
        self.w_e = w_e
        self.kappa = kappa
        self.initial_resource_prior = initial_resource_prior

        self.grid_width = grid_width
        self.grid_height = grid_height

        # --- State variables ---
        self.h_t: float = 0.0                  # true internal hunger
        self.mu_h: float = 0.0                 # believed hunger mean
        self.sigma_h_sq: float = 1.0           # believed hunger variance
        self.o_h: float = 0.0                  # last interoceptive observation
        self.s_t: tuple = (0, 0)               # current position
        self.ate_food_flag: int = 0            # ate this step?

        # Resource belief map: R_beliefs[x][y] = P(food at (x,y))
        self.R_beliefs: list = [
            [initial_resource_prior] * grid_height
            for _ in range(grid_width)
        ]

        # Per-action free energy components (cached for get_state / q_values)
        self.G_prag_a: float = 0.0
        self.G_epist_a: float = 0.0
        self.G_a: float = 0.0

        # q_values: G(a) for each action (used by simulation infrastructure)
        self.q_values: dict = {a: 0.0 for a in self._ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clip(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _binary_entropy(p: float) -> float:
        p = max(1e-9, min(1 - 1e-9, p))
        return -p * math.log(p) - (1 - p) * math.log(1 - p)

    def _compute_G_values(
        self,
        mu_h: float,
        sigma_h_sq: float,
        food_at_position: bool,
        s_t: tuple,
        grid_w: int,
        grid_h: int,
    ) -> dict:
        """Compute expected free energy G(a) for all candidate actions.

        This is a read-only computation used by both decide() and update().
        """
        G_vals = {}
        for action_name in self._ACTIONS:
            if action_name == "eat":
                if food_at_position:
                    mu_after = mu_h + self.lambda_drift - self.K
                    G_prag = -(
                        (mu_after - self.h_star) ** 2 + sigma_h_sq
                    ) / (self.sigma_p ** 2)
                    G_epist = 0.0
                else:
                    # Eat is not available — suppress it heavily
                    G_prag = -1e9
                    G_epist = 0.0

            elif action_name == "stay":
                mu_after = mu_h + self.lambda_drift
                G_prag = -(
                    (mu_after - self.h_star) ** 2 + sigma_h_sq
                ) / (self.sigma_p ** 2)
                G_epist = 0.0

            else:  # movement actions
                dx, dy = self._DELTA[action_name]
                new_x = int(self._clip(s_t[0] + dx, 0, grid_w - 1))
                new_y = int(self._clip(s_t[1] + dy, 0, grid_h - 1))
                mu_after = mu_h + self.lambda_drift
                G_prag = -(
                    (mu_after - self.h_star) ** 2 + sigma_h_sq
                ) / (self.sigma_p ** 2)
                p_resource = self.R_beliefs[new_x][new_y]
                G_epist = self._binary_entropy(p_resource)

            G_vals[action_name] = G_prag + self.w_e * G_epist

        return G_vals

    @staticmethod
    def _softmax_sample(G_vals: dict, beta: float) -> str:
        """Sample an action from softmax distribution over G values."""
        actions = list(G_vals.keys())
        g_list = [G_vals[a] for a in actions]
        max_g = max(g_list)
        exp_vals = [math.exp(beta * (g - max_g)) for g in g_list]
        total = sum(exp_vals)
        probs = [e / total for e in exp_vals]
        r = random.random()
        cumulative = 0.0
        for a, p in zip(actions, probs):
            cumulative += p
            if r <= cumulative:
                return a
        return actions[-1]

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """Read-only: select action from current internal state.

        Uses the cached mu_h / sigma_h_sq (not yet updated for this step).
        All state mutation happens in update().
        """
        x = perception["x"]
        y = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception.get("resources", {}).get("food", [])
        food_positions = set((f["x"], f["y"]) for f in food_list)
        food_at_position = (x, y) in food_positions

        G_vals = self._compute_G_values(
            self.mu_h,
            self.sigma_h_sq,
            food_at_position,
            (x, y),
            grid_w,
            grid_h,
        )

        chosen = self._softmax_sample(G_vals, self.beta_G)
        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Apply all rules: Bayesian hunger update, true hunger update, belief map update."""
        x = new_perception["x"]
        y = new_perception["y"]
        grid_w = new_perception["grid_width"]
        grid_h = new_perception["grid_height"]
        food_list = new_perception.get("resources", {}).get("food", [])
        food_positions = set((f["x"], f["y"]) for f in food_list)
        food_at_position = (x, y) in food_positions
        last_result = new_perception.get("last_action_result", {})

        # R8: True hunger update
        ate_t = 1 if (
            action.name == "eat" and last_result.get("consumed", False)
        ) else 0
        self.ate_food_flag = ate_t
        self.h_t = self._clip(
            self.h_t + self.lambda_drift - self.K * ate_t,
            0.0,
            self.h_max,
        )

        # R1: Prediction step — propagate belief forward
        mu_h_prior = self.mu_h + self.lambda_drift
        sigma_h_sq_prior = self.sigma_h_sq + self.sigma_process_sq

        # R2: Noisy interoceptive observation
        self.o_h = self.h_t + random.gauss(0.0, self.sigma_obs)

        # R3: Bayesian (Kalman) update
        K_gain = sigma_h_sq_prior / (sigma_h_sq_prior + self.sigma_obs ** 2)
        self.mu_h = mu_h_prior + K_gain * (self.o_h - mu_h_prior)
        self.sigma_h_sq = max((1.0 - K_gain) * sigma_h_sq_prior, 0.001)

        # R9: Resource belief map update at current position
        if food_at_position:
            self.R_beliefs[x][y] = 1.0
        else:
            self.R_beliefs[x][y] *= (1.0 - self.kappa)

        # Update position
        self.s_t = (x, y)

        # Recompute and cache q_values for get_state()
        G_vals = self._compute_G_values(
            self.mu_h,
            self.sigma_h_sq,
            food_at_position,
            (x, y),
            grid_w,
            grid_h,
        )
        self.q_values = G_vals

        # Cache most recent action's components for get_state
        self.G_a = G_vals.get(action.name, 0.0)
        # For pragmatic/epistemic components, recompute for the taken action
        if action.name == "eat":
            if food_at_position:
                mu_after = self.mu_h + self.lambda_drift - self.K
                self.G_prag_a = -(
                    (mu_after - self.h_star) ** 2 + self.sigma_h_sq
                ) / (self.sigma_p ** 2)
                self.G_epist_a = 0.0
            else:
                self.G_prag_a = -1e9
                self.G_epist_a = 0.0
        elif action.name == "stay":
            mu_after = self.mu_h + self.lambda_drift
            self.G_prag_a = -(
                (mu_after - self.h_star) ** 2 + self.sigma_h_sq
            ) / (self.sigma_p ** 2)
            self.G_epist_a = 0.0
        else:
            dx, dy = self._DELTA.get(action.name, (0, 0))
            new_x = int(self._clip(x + dx, 0, grid_w - 1))
            new_y = int(self._clip(y + dy, 0, grid_h - 1))
            mu_after = self.mu_h + self.lambda_drift
            self.G_prag_a = -(
                (mu_after - self.h_star) ** 2 + self.sigma_h_sq
            ) / (self.sigma_p ** 2)
            self.G_epist_a = self._binary_entropy(self.R_beliefs[new_x][new_y])

    def get_state(self) -> dict:
        return {
            "true_hunger": self.h_t,
            "believed_hunger_mean": self.mu_h,
            "believed_hunger_variance": self.sigma_h_sq,
            "hunger_observation": self.o_h,
            "position": self.s_t,
            "ate_food_flag": self.ate_food_flag,
            "pragmatic_value": self.G_prag_a,
            "epistemic_value": self.G_epist_a,
            "expected_free_energy": self.G_a,
            "q_values": dict(self.q_values),
        }
