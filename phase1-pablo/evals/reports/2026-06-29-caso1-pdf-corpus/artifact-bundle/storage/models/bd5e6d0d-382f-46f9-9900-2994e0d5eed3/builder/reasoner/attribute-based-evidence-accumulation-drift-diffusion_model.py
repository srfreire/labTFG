"""
Attribute-Based Evidence Accumulation (Drift-Diffusion) Decision Model
=======================================================================
Paradigm  : attribute-based-value-computation
Formulation: attribute-based-evidence-accumulation-drift-diffusion

Dynamic stochastic decision process where value evidence for each candidate
action accumulates over internal deliberation time steps. Drift rates are
determined by attribute-weighted option values (immediate proximity + abstract
palatability), and noise is scaled by attribute conflict. Based on Rangel (2013).
"""

import random
import math
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _find_nearest_food(nx: int, ny: int, food_list: list):
    """Return the food item with the smallest Manhattan distance from (nx, ny)."""
    best = None
    best_dist = float("inf")
    for f in food_list:
        d = abs(nx - f["x"]) + abs(ny - f["y"])
        if d < best_dist:
            best_dist = d
            best = f
    return best


_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
_DELTAS = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class AttributeBasedEvidenceAccumulationDriftDiffusionModel:
    """
    Attribute-weighted DDM with hunger-driven weight modulation and
    competitive stochastic evidence accumulation race.

    All accumulators run in parallel: at each deliberation step every
    accumulator is updated simultaneously, then the one that first reached the
    threshold (or has the highest evidence at timeout) is selected.
    """

    def __init__(
        self,
        decision_threshold: float = 1.0,
        base_noise: float = 0.3,
        conflict_noise_scaling: float = 0.5,
        max_deliberation_steps: int = 10,
        weight_learning_rate: float = 0.05,
        hunger_rise_rate: float = 0.01,
        hunger_restoration_from_eating: float = 0.3,
    ):
        # Parameters
        self.theta = decision_threshold
        self.sigma_0 = base_noise
        self.kappa = conflict_noise_scaling
        self.T_max = max_deliberation_steps
        self.beta_w = weight_learning_rate
        self.eta = hunger_rise_rate
        self.R_food = hunger_restoration_from_eating

        # State variables
        self.H_t: float = 0.5          # hunger
        self.w_imm: float = 0.5        # immediate attribute weight
        self.w_abs: float = 0.5        # abstract attribute weight

        # Per-action running state (refreshed each update)
        self.evidence_accumulator: dict = {a: 0.0 for a in _ACTIONS}
        self.drift_rate: dict = {a: 0.0 for a in _ACTIONS}
        self.immediate_attribute_value: dict = {a: 0.0 for a in _ACTIONS}
        self.abstract_attribute_value: dict = {a: 0.0 for a in _ACTIONS}
        self.noise_magnitude: dict = {a: self.sigma_0 for a in _ACTIONS}
        self.attribute_conflict: dict = {a: 0.0 for a in _ACTIONS}

        # q_values: drift rates used as action scores (updated in update())
        self.q_values: dict = {a: 0.0 for a in _ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_attr_weights(self) -> tuple:
        """R1: Hunger-driven attribute weights. w_imm + w_abs = 1 always."""
        w_imm = (1.0 + self.H_t) / (2.0 + self.H_t)
        w_abs = 1.0 / (2.0 + self.H_t)
        return w_imm, w_abs

    def _compute_attr_values(
        self, perception: dict, w_imm: float, w_abs: float
    ) -> tuple:
        """
        R2–R5: Compute per-action (a_imm, a_abs), drift, conflict, noise.
        Returns: attr_values, drift, conflict, noise dicts.
        """
        x = perception["x"]
        y = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception.get("resources", {}).get("food", [])
        max_dist = grid_w + grid_h - 2

        food_at_pos = [f for f in food_list if f["x"] == x and f["y"] == y]

        attr_values = {}  # action -> (a_imm, a_abs)

        for a in _ACTIONS:
            if a == "eat":
                if food_at_pos:
                    pal = food_at_pos[0]["palatability"]
                    a_imm = 1.0
                    a_abs = 2.0 * (pal - 0.1) / 0.9 - 1.0
                else:
                    a_imm = 0.0
                    a_abs = 0.0

            elif a == "stay":
                a_imm = 0.0
                a_abs = 0.0

            else:  # movement action
                dx, dy = _DELTAS[a]
                nx = _clip(x + dx, 0, grid_w - 1)
                ny = _clip(y + dy, 0, grid_h - 1)
                nearest = _find_nearest_food(nx, ny, food_list)
                if nearest and max_dist > 0:
                    dist = abs(nx - nearest["x"]) + abs(ny - nearest["y"])
                    a_imm = 1.0 - dist / max_dist
                    pal = nearest["palatability"]
                    a_abs = 2.0 * (pal - 0.1) / 0.9 - 1.0
                else:
                    a_imm = 0.0
                    a_abs = 0.0

            attr_values[a] = (a_imm, a_abs)

        # R3: Drift rates
        drift = {
            a: w_imm * attr_values[a][0] + w_abs * attr_values[a][1]
            for a in _ACTIONS
        }
        # R4: Conflict
        conflict = {
            a: abs(attr_values[a][0] - attr_values[a][1]) for a in _ACTIONS
        }
        # R5: Noise magnitude
        noise = {
            a: self.sigma_0 * (1.0 + self.kappa * conflict[a]) for a in _ACTIONS
        }

        return attr_values, drift, conflict, noise

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY decision via evidence accumulation race (R6).
        All accumulators are updated simultaneously each step (parallel race),
        then the first to cross threshold is selected.
        No state mutation occurs here.
        """
        # R1
        w_imm, w_abs = self._compute_attr_weights()
        # R2–R5
        attr_values, drift, conflict, noise = self._compute_attr_values(
            perception, w_imm, w_abs
        )

        # R6: Parallel evidence accumulation race.
        # All accumulators are updated simultaneously at each deliberation step.
        # After each step we check which (if any) crossed the threshold.
        # If multiple crossed in the same step, the one with the highest
        # accumulated evidence wins (ties broken by order).
        E = {a: 0.0 for a in _ACTIONS}
        selected = None

        for _t in range(1, self.T_max + 1):
            # Update ALL accumulators simultaneously
            for a in _ACTIONS:
                xi = random.gauss(0.0, 1.0)
                E[a] = E[a] + drift[a] + noise[a] * xi

            # Check threshold crossing after the full step
            crossed = [a for a in _ACTIONS if E[a] >= self.theta]
            if crossed:
                # If multiple crossed, select the one with highest evidence
                selected = max(crossed, key=lambda a: E[a])
                break

        if selected is None:
            selected = max(E, key=lambda a: E[a])

        # Cache for update (read in update())
        self._pending_drift = drift
        self._pending_attr_values = attr_values
        self._pending_E = E

        return Action(name=selected)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: Apply R7 (weight update), R8 (hunger update), refresh q_values.
        """
        selected = action.name

        # Retrieve cached values from decide()
        drift = getattr(self, "_pending_drift", {a: 0.0 for a in _ACTIONS})
        attr_values = getattr(
            self, "_pending_attr_values", {a: (0.0, 0.0) for a in _ACTIONS}
        )

        mu_selected = drift.get(selected, 0.0)
        a_imm_sel, a_abs_sel = attr_values.get(selected, (0.0, 0.0))

        # Recompute weights (consistent with decide phase using current H_t)
        w_imm, w_abs = self._compute_attr_weights()

        # R8: Hunger update
        last_result = new_perception.get("last_action_result", {})
        consumed = last_result.get("consumed", False)
        ate = 1 if (selected == "eat" and (consumed or reward > 0)) else 0
        self.H_t = _clip(self.H_t + self.eta - self.R_food * ate, 0.0, 1.0)

        # R7: Attribute weight update via RPE
        RPE = reward - mu_selected
        w_imm = w_imm + self.beta_w * RPE * a_imm_sel
        w_abs = w_abs + self.beta_w * RPE * a_abs_sel
        w_imm = max(0.05, w_imm)
        w_abs = max(0.05, w_abs)
        total = w_imm + w_abs
        self.w_imm = w_imm / total
        self.w_abs = w_abs / total

        # Refresh per-action state using updated weights + new perception
        w_imm_new, w_abs_new = self._compute_attr_weights()
        attr_new, drift_new, conflict_new, noise_new = self._compute_attr_values(
            new_perception, w_imm_new, w_abs_new
        )

        for a in _ACTIONS:
            self.immediate_attribute_value[a] = attr_new[a][0]
            self.abstract_attribute_value[a] = attr_new[a][1]
            self.drift_rate[a] = drift_new[a]
            self.attribute_conflict[a] = conflict_new[a]
            self.noise_magnitude[a] = noise_new[a]

        # Store final accumulator states from last deliberation
        pending_E = getattr(self, "_pending_E", {a: 0.0 for a in _ACTIONS})
        for a in _ACTIONS:
            self.evidence_accumulator[a] = pending_E.get(a, 0.0)

        # Update q_values = drift rates from freshly computed state
        self.q_values = dict(drift_new)

    def get_state(self) -> dict:
        return {
            "hunger": self.H_t,
            "immediate_weight": self.w_imm,
            "abstract_weight": self.w_abs,
            "evidence_accumulator": dict(self.evidence_accumulator),
            "drift_rate": dict(self.drift_rate),
            "immediate_attribute_value": dict(self.immediate_attribute_value),
            "abstract_attribute_value": dict(self.abstract_attribute_value),
            "noise_magnitude": dict(self.noise_magnitude),
            "attribute_conflict": dict(self.attribute_conflict),
            "q_values": dict(self.q_values),
        }
