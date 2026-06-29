"""
Weighted Linear Summation with State-Dependent Attribute Weights (Algebraic)

Grounded in Rangel (2013) postulates P1, P3, P5:
- P1: weighted linear summation of attributes
- P3: attentional modulation of weights
- P5: immediate vs. abstract attribute distinction
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# Direction deltas for movement actions: (dx, dy)
# Grid convention: y increases downward
_DIRECTION_DELTAS = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
}

_ALL_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]


def _manhattan(x1, y1, x2, y2):
    return abs(x1 - x2) + abs(y1 - y2)


def _find_nearest_food(nx, ny, food_list):
    """Return the food dict with minimum Manhattan distance to (nx, ny)."""
    best = None
    best_dist = float("inf")
    for f in food_list:
        d = _manhattan(nx, ny, f["x"], f["y"])
        if d < best_dist:
            best_dist = d
            best = f
    return best


def _palatability_to_abs(palatability):
    """Normalize palatability in [0.1, 1.0] → a_abs in [-1, 1]."""
    return 2.0 * (palatability - 0.1) / 0.9 - 1.0


class WeightedLinearSummationWithStateDependentAttributeWeightsAlgebraicModel:
    """
    Multi-attribute utility model where action values are weighted linear sums
    of an immediate attribute (proximity-based) and an abstract attribute
    (palatability-based). Weights are state-dependent (hunger + attention).
    Action selection uses softmax. Attention updates via reward prediction error.
    """

    def __init__(self):
        # --- State variables ---
        self.V_o = 0.0            # option value (last computed)
        self.a_imm = 0.0          # immediate attribute value (last computed)
        self.a_abs = 0.0          # abstract attribute value (last computed)
        self.w_imm = 0.5          # effective weight for immediate attribute
        self.w_abs = 0.5          # effective weight for abstract attribute
        self.H_t = 0.5            # hunger state [0, 1]
        self.alpha_imm = 0.5      # attentional allocation to immediate attribute
        self.alpha_abs = 0.5      # attentional allocation to abstract attribute
        self.V_a = 0.0            # action value of selected action

        # --- Parameters ---
        self.beta = 5.0           # softmax inverse temperature
        self.gamma_H = 0.6        # hunger influence on immediate weight
        self.delta = 0.7          # temporal discount for abstract attributes
        self.eta = 0.01           # hunger rise rate per step
        self.R_food = 0.3         # hunger reduction from eating
        self.lam = 0.05           # attention learning rate
        self.epsilon = 0.05       # minimum attention (floor)

        # --- Cached values for update phase ---
        # Per-action caches computed during decide()
        self._last_action_values = {a: 0.0 for a in _ALL_ACTIONS}
        self._last_action_imm = {a: 0.0 for a in _ALL_ACTIONS}
        self._last_action_abs = {a: 0.0 for a in _ALL_ACTIONS}
        self._last_selected_V = 0.0
        self._last_selected_a_imm = 0.0
        self._last_selected_a_abs = 0.0

        # --- q_values for get_state() ---
        self.q_values = {a: 0.0 for a in _ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_weights(self):
        """R1: Compute effective attribute weights from hunger and attention."""
        unnorm_imm = self.alpha_imm * (1.0 + self.gamma_H * self.H_t)
        unnorm_abs = self.alpha_abs * self.delta
        Z = unnorm_imm + unnorm_abs
        if Z == 0.0:
            w_imm = 0.5
            w_abs = 0.5
        else:
            w_imm = unnorm_imm / Z
            w_abs = unnorm_abs / Z
        return w_imm, w_abs

    def _compute_action_attributes(self, action_name, pos, food_list, grid_w, grid_h):
        """R2: Compute (a_imm, a_abs) for a given action."""
        max_dist = max(grid_w + grid_h - 2, 1)  # prevent division by zero on tiny grids
        px, py = pos

        if action_name == "eat":
            food_at_pos = [f for f in food_list if f["x"] == px and f["y"] == py]
            if food_at_pos:
                a_imm = 1.0
                a_abs = _palatability_to_abs(food_at_pos[0]["palatability"])
            else:
                a_imm = 0.0
                a_abs = 0.0

        elif action_name == "stay":
            a_imm = 0.0
            a_abs = 0.0

        else:  # movement action
            dx, dy = _DIRECTION_DELTAS[action_name]
            nx = max(0, min(grid_w - 1, px + dx))
            ny = max(0, min(grid_h - 1, py + dy))
            nearest = _find_nearest_food(nx, ny, food_list)
            if nearest is not None:
                dist = _manhattan(nx, ny, nearest["x"], nearest["y"])
                a_imm = 1.0 - dist / max_dist
                a_abs = _palatability_to_abs(nearest["palatability"])
            else:
                a_imm = 0.0
                a_abs = 0.0

        return a_imm, a_abs

    def _softmax_sample(self, action_values):
        """R4: Softmax sampling over action values dict."""
        actions = list(action_values.keys())
        logits = [self.beta * action_values[a] for a in actions]
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        total = sum(exp_logits)
        probs = [e / total for e in exp_logits]
        return random.choices(actions, weights=probs, k=1)[0]

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """READ-ONLY: select action based on current state and perception."""
        food_list = perception.get("resources", {}).get("food", [])
        pos = (perception["x"], perception["y"])
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]

        # R1: Compute effective weights (read-only, don't store to self yet)
        w_imm, w_abs = self._compute_weights()

        # R2 + R3: For each action compute attribute values and action value
        action_values = {}
        action_imm = {}
        action_abs = {}

        for action_name in _ALL_ACTIONS:
            a_imm, a_abs = self._compute_action_attributes(
                action_name, pos, food_list, grid_w, grid_h
            )
            V_a = w_imm * a_imm + w_abs * a_abs  # R3
            action_values[action_name] = V_a
            action_imm[action_name] = a_imm
            action_abs[action_name] = a_abs

        # Cache per-action data for update phase
        self._last_action_values = action_values
        self._last_action_imm = action_imm
        self._last_action_abs = action_abs

        # R4: Softmax action selection
        selected = self._softmax_sample(action_values)

        # Cache selected-action attributes for update phase
        self._last_selected_V = action_values[selected]
        self._last_selected_a_imm = action_imm[selected]
        self._last_selected_a_abs = action_abs[selected]

        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """WRITE: apply all rules and update all state variables."""
        last_result = new_perception.get("last_action_result", {})

        # R1: Update effective weights (store to self)
        self.w_imm, self.w_abs = self._compute_weights()

        # R5: Hunger state update
        consumed = last_result.get("consumed", False)
        ate = 1 if (action.name == "eat" and (consumed or reward > 0)) else 0
        self.H_t = max(0.0, min(1.0, self.H_t + self.eta - self.R_food * ate))

        # R6: Attention allocation update via RPE
        V_selected = self._last_selected_V
        a_imm_selected = self._last_selected_a_imm
        a_abs_selected = self._last_selected_a_abs

        RPE = reward - V_selected
        self.alpha_imm = self.alpha_imm + self.lam * RPE * a_imm_selected
        self.alpha_abs = self.alpha_abs + self.lam * RPE * a_abs_selected

        # Floor at epsilon
        self.alpha_imm = max(self.epsilon, self.alpha_imm)
        self.alpha_abs = max(self.epsilon, self.alpha_abs)

        # Renormalize to sum to 1
        total = self.alpha_imm + self.alpha_abs
        self.alpha_imm = self.alpha_imm / total
        self.alpha_abs = self.alpha_abs / total

        # Update stored attribute values for the executed action
        self.a_imm = a_imm_selected
        self.a_abs = a_abs_selected
        self.V_a = V_selected
        self.V_o = V_selected

        # Recompute weights after hunger/attention update for accurate get_state()
        self.w_imm, self.w_abs = self._compute_weights()

        # Update q_values from last cached action_values
        self.q_values = dict(self._last_action_values)

    def get_state(self) -> dict:
        return {
            "V_o": self.V_o,
            "a_imm": self.a_imm,
            "a_abs": self.a_abs,
            "w_imm": self.w_imm,
            "w_abs": self.w_abs,
            "H_t": self.H_t,
            "alpha_imm": self.alpha_imm,
            "alpha_abs": self.alpha_abs,
            "V_a": self.V_a,
            "q_values": dict(self.q_values),
        }
