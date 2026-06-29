"""
Algebraic Precision-Weighted Bayesian Filtering (Single-Step Conjugate Update)

A closed-form single-step Bayesian filtering agent using precision-weighted averaging
(conjugate Gaussian inference). The precision ratio between sensory and prior channels
controls how much the agent trusts observations vs. its own predictions.

Paradigm: predictive-coding
Formulation: algebraic-precision-weighted-bayesian-filtering-single-step-conjugate-update
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _dot(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))


def _softmax_sample(actions: list, values: list, beta: float) -> str:
    """Sample an action from softmax distribution over values."""
    max_v = max(values)
    exp_vals = [math.exp(beta * (v - max_v)) for v in values]
    total = sum(exp_vals)
    probs = [e / total for e in exp_vals]
    r = random.random()
    cumulative = 0.0
    for action, prob in zip(actions, probs):
        cumulative += prob
        if r <= cumulative:
            return action
    return actions[-1]


def _build_sensory_vector(perception: dict, d_max: int) -> list:
    """
    Build 5-element sensory vector s from perception.
    s = [food_here, nearest_food_dx_norm, nearest_food_dy_norm, food_density_nearby, avg_palatability]
    """
    agent_x = perception['x']
    agent_y = perception['y']
    grid_w = max(perception['grid_width'], 1)
    grid_h = max(perception['grid_height'], 1)
    food_sources = perception['resources'].get('food', [])

    food_here = 0.0
    nearest_dx = 0.0
    nearest_dy = 0.0
    nearest_dist = d_max + 1
    food_count_nearby = 0
    total_palatability = 0.0

    for f in food_sources:
        dx = f['x'] - agent_x
        dy = f['y'] - agent_y
        dist = abs(dx) + abs(dy)
        if dist == 0:
            food_here = 1.0
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_dx = dx / grid_w
            nearest_dy = dy / grid_h
        if dist <= d_max:
            food_count_nearby += 1
            total_palatability += f.get('palatability', 0.5)

    food_density = food_count_nearby / max(len(food_sources), 1)
    avg_palat = total_palatability / max(food_count_nearby, 1) if food_count_nearby > 0 else 0.0

    return [food_here, nearest_dx, nearest_dy, food_density, avg_palat]


def _compute_action_values(
    perception: dict,
    mu_hat: list,
    pi_s: float,
    pi_0: float,
    d_max: int,
    r_food: float,
    r_empty: float,
) -> dict:
    """
    Evaluate all candidate actions using the cell-value function (R7) and eat logic.
    Returns dict mapping action name -> float value.
    """
    agent_x = perception['x']
    agent_y = perception['y']
    grid_w = perception['grid_width']
    grid_h = perception['grid_height']
    food_sources = perception['resources'].get('food', [])

    # food_here derived from current sensory reading
    food_here = any(f['x'] == agent_x and f['y'] == agent_y for f in food_sources)

    # Nearest food direction from posterior belief (mu_hat[1], mu_hat[2])
    nearest_dx_norm = mu_hat[1]
    nearest_dy_norm = mu_hat[2]
    nearest_dist_approx = abs(nearest_dx_norm * grid_w) + abs(nearest_dy_norm * grid_h)

    uncertainty_weight = 1.0 - pi_s / (pi_s + pi_0)

    action_values = {}

    # --- Eat action ---
    if food_here:
        action_values['eat'] = pi_s * r_food
    else:
        action_values['eat'] = r_empty

    # --- Stay action ---
    action_values['stay'] = 0.0

    # --- Movement actions ---
    move_deltas = {
        'move_up': (0, -1),
        'move_down': (0, 1),
        'move_left': (-1, 0),
        'move_right': (1, 0),
    }

    for action_name, (mdx, mdy) in move_deltas.items():
        dest_x = _clip(agent_x + mdx, 0, grid_w - 1)
        dest_y = _clip(agent_y + mdy, 0, grid_h - 1)

        # Direct food observation at destination
        R_hat = 0.0
        for f in food_sources:
            if f['x'] == dest_x and f['y'] == dest_y:
                R_hat = f.get('palatability', 0.5)
                break

        # Direction bonus: does this move reduce distance to believed nearest food?
        direction_bonus = 0.0
        if nearest_dist_approx > 0 and nearest_dist_approx <= d_max:
            new_dist = (
                abs((agent_x + mdx) - (agent_x + nearest_dx_norm * grid_w)) +
                abs((agent_y + mdy) - (agent_y + nearest_dy_norm * grid_h))
            )
            old_dist = nearest_dist_approx
            if new_dist < old_dist:
                direction_bonus = mu_hat[3] * 0.5  # food density belief as bonus

        # Cell value: R7
        V_c = pi_s * (R_hat + direction_bonus) - uncertainty_weight * 1.0
        action_values[action_name] = V_c

    return action_values


class AlgebraicPrecisionWeightedBayesianFilteringSingleStepConjugateUpdateModel:
    """
    Algebraic Precision-Weighted Bayesian Filtering — Single-Step Conjugate Update.

    Uses closed-form precision-weighted Gaussian conjugate updates.
    No iterative gradient descent — everything is one analytic step per tick.
    """

    def __init__(
        self,
        pi_s_init: float = 4.0,
        pi_0_init: float = 1.0,
        alpha_pi: float = 0.15,
        gamma: float = 0.9,
        beta: float = 5.0,
        r_food: float = 1.0,
        r_empty: float = -0.5,
        d_max: int = 5,
    ):
        # Parameters
        self.pi_s_init = pi_s_init
        self.pi_0_init = pi_0_init
        self.alpha_pi = alpha_pi
        self.gamma = gamma
        self.beta = beta
        self.r_food = r_food
        self.r_empty = r_empty
        self.d_max = d_max

        # State variables
        self.s: list = [0.0, 0.0, 0.0, 0.0, 0.0]          # sensory_observation
        self.mu_hat: list = [0.0, 0.0, 0.0, 0.0, 0.0]      # posterior_belief
        self.pi_s: float = pi_s_init                         # sensory_precision
        self.pi_0: float = pi_0_init                         # prior_precision
        self.mu_0: list = [0.0, 0.0, 0.0, 0.0, 0.0]        # prior_prediction
        self.eps: list = [0.0, 0.0, 0.0, 0.0, 0.0]         # prediction_error
        self.w: float = 0.0                                  # precision_weighted_surprise
        self.V: float = 0.0                                  # cell_value (scalar summary)

        # Cached action values (q_values)
        self._action_values: dict = {
            'eat': 0.0,
            'stay': 0.0,
            'move_up': 0.0,
            'move_down': 0.0,
            'move_left': 0.0,
            'move_right': 0.0,
        }

    # ------------------------------------------------------------------
    # decide: READ-ONLY — selects action from CURRENT state
    # ------------------------------------------------------------------
    def decide(self, perception: dict) -> Action:
        """
        Select action based on current beliefs (self.mu_hat, self.pi_s, self.pi_0).
        Does NOT modify any state — all updates happen in update().
        """
        # Compute action values from current posterior belief
        action_values = _compute_action_values(
            perception=perception,
            mu_hat=self.mu_hat,
            pi_s=self.pi_s,
            pi_0=self.pi_0,
            d_max=self.d_max,
            r_food=self.r_food,
            r_empty=self.r_empty,
        )

        # Softmax action selection (R8)
        actions = list(action_values.keys())
        vals = [action_values[a] for a in actions]
        selected = _softmax_sample(actions, vals, self.beta)

        return Action(name=selected)

    # ------------------------------------------------------------------
    # update: WRITE — applies all rules R1-R6, updates q_values
    # ------------------------------------------------------------------
    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all Bayesian filtering rules and precision adaptation.
        Must be called AFTER the environment applies the action.
        """
        # --- Encode sensory observation from new_perception ---
        s_new = _build_sensory_vector(new_perception, self.d_max)
        self.s = s_new

        # --- R1: Prior prediction via temporal transition ---
        s_default = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.mu_0 = [
            self.gamma * mh + (1.0 - self.gamma) * sd
            for mh, sd in zip(self.mu_hat, s_default)
        ]

        # --- R2: Prediction error ---
        self.eps = [s_i - mu0_i for s_i, mu0_i in zip(self.s, self.mu_0)]

        # --- R3: Posterior belief — one-shot conjugate update ---
        self.mu_hat = [
            (self.pi_s * s_i + self.pi_0 * mu0_i) / (self.pi_s + self.pi_0)
            for s_i, mu0_i in zip(self.s, self.mu_0)
        ]

        # --- R4: Posterior precision (pi_post = pi_s + pi_0) — informational ---
        # Used implicitly in R3/R5; not stored as separate state variable per spec

        # --- R5: Precision-weighted surprise ---
        eps_sq = _dot(self.eps, self.eps)
        self.w = self.pi_s * eps_sq / (self.pi_s + self.pi_0)

        # --- R6: Sensory precision adaptation ---
        self.pi_s = self.pi_s + self.alpha_pi * (1.0 / (eps_sq + 0.01) - self.pi_s)
        self.pi_s = _clip(self.pi_s, 0.01, 100.0)

        # --- Reward-based precision modulation (decision_logic update block) ---
        if reward > 0:
            self.pi_s = _clip(self.pi_s + self.alpha_pi, 0.01, 100.0)
        elif action.name == 'eat' and reward == 0:
            self.pi_s = _clip(self.pi_s - self.alpha_pi, 0.01, 100.0)

        # --- Cache action values for get_state() (q_values) ---
        self._action_values = _compute_action_values(
            perception=new_perception,
            mu_hat=self.mu_hat,
            pi_s=self.pi_s,
            pi_0=self.pi_0,
            d_max=self.d_max,
            r_food=self.r_food,
            r_empty=self.r_empty,
        )

        # Update scalar cell_value summary (max movement value)
        move_vals = [
            self._action_values[a]
            for a in ('move_up', 'move_down', 'move_left', 'move_right')
        ]
        self.V = max(move_vals) if move_vals else 0.0

    # ------------------------------------------------------------------
    # get_state: returns full snapshot including q_values
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        return {
            # State variables
            's': list(self.s),
            'mu_hat': list(self.mu_hat),
            'pi_s': self.pi_s,
            'pi_0': self.pi_0,
            'mu_0': list(self.mu_0),
            'eps': list(self.eps),
            'w': self.w,
            'V': self.V,
            # Parameters
            'pi_s_init': self.pi_s_init,
            'pi_0_init': self.pi_0_init,
            'alpha_pi': self.alpha_pi,
            'gamma': self.gamma,
            'beta': self.beta,
            'r_food': self.r_food,
            'r_empty': self.r_empty,
            'd_max': self.d_max,
            # Q-values for simulation infrastructure
            'q_values': dict(self._action_values),
        }
