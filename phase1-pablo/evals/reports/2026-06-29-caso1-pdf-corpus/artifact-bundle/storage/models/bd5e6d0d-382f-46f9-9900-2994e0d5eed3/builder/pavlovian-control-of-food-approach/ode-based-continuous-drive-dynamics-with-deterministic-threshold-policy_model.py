"""
ODE-Based Continuous Drive Dynamics with Deterministic Threshold Policy
Paradigm: pavlovian-control-of-food-approach

Continuous-time Pavlovian agent modeled via ODEs governing hunger drive
(logistic growth toward 1, sharp drop on eating) and associative strength V(s)
(Rescorla–Wagner learning with explicit extinction decay). Uses a deterministic
threshold policy on effective motivational drive E(t) = mu * H_t * V_perceived.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class OdeBasedContinuousDriveDynamicsWithDeterministicThresholdPolicyModel:
    """
    Pavlovian agent with ODE-based hunger dynamics and Rescorla–Wagner
    associative learning.  Action selection uses a deterministic threshold
    hierarchy on E(t) = mu * H_t * V_perceived.
    """

    # Movement deltas: action_name → (dx, dy)
    _MOVE_DELTAS: dict[str, tuple[int, int]] = {
        "move_up":    (0, -1),
        "move_down":  (0,  1),
        "move_left":  (-1, 0),
        "move_right": (1,  0),
    }

    def __init__(
        self,
        alpha_V: float = 0.10,
        c_H: float = 0.02,
        k_sat: float = 0.25,
        mu: float = 1.5,
        theta_approach: float = 0.3,
        theta_eat: float = 0.5,
        eta: float = 0.01,
        r_food: float = 1.0,
        V_max: float = 2.0,
        dt: float = 1.0,
        hunger_override: float = 0.8,
    ) -> None:
        # Parameters
        self.alpha_V = alpha_V
        self.c_H = c_H
        self.k_sat = k_sat
        self.mu = mu
        self.theta_approach = theta_approach
        self.theta_eat = theta_eat
        self.eta = eta
        self.r_food = r_food
        self.V_max = V_max
        self.dt = dt
        self.hunger_override = hunger_override

        # State variables
        self.H_t: float = 0.5                        # hunger drive
        self.V: dict[tuple[int, int], float] = {}    # associative strengths
        self.E_t: float = 0.0                        # effective drive
        self.V_perceived: float = 0.0                # max perceived value
        self.r_t: float = 0.0                        # reward received
        self.d_min: int | None = None                # nearest food distance

        # q_values: utility of each action (maintained in update)
        self.q_values: dict[str, float] = {
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

    def _compute_visible_cells(
        self,
        x: int,
        y: int,
        grid_w: int,
        grid_h: int,
        food_list: list[dict],
    ) -> set[tuple[int, int]]:
        """All cells visible to the agent: current + food + valid neighbors."""
        cells: set[tuple[int, int]] = set()
        cells.add((x, y))
        for f in food_list:
            cells.add((f["x"], f["y"]))
        for dx, dy in self._MOVE_DELTAS.values():
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                cells.add((nx, ny))
        return cells

    def _compute_V_perceived(
        self,
        visible_cells: set[tuple[int, int]],
    ) -> float:
        """R3: maximum associative strength among visible cells."""
        if not visible_cells:
            return 0.0
        return max(self.V.get(c, 0.0) for c in visible_cells)

    def _compute_approach_action(
        self,
        x: int,
        y: int,
        grid_w: int,
        grid_h: int,
    ) -> str:
        """R5: gradient ascent on V — move toward neighbor with highest V."""
        neighbor_vals: dict[str, float] = {}
        for action_name, (dx, dy) in self._MOVE_DELTAS.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                neighbor_vals[action_name] = self.V.get((nx, ny), 0.0)
        if not neighbor_vals:
            return "stay"
        best_val = max(neighbor_vals.values())
        best_actions = [a for a, v in neighbor_vals.items() if v == best_val]
        return random.choice(best_actions)

    def _compute_q_values(
        self,
        x: int,
        y: int,
        grid_w: int,
        grid_h: int,
        food_list: list[dict],
    ) -> dict[str, float]:
        """
        Compute per-action utility scores used by get_state() / q_values.

        eat       : E_t (motivational drive when food is present, else 0)
        move_*    : V of the target neighbor (approach value landscape)
        stay      : 0 (baseline / no-op)
        """
        food_pos = {(f["x"], f["y"]) for f in food_list}
        pos = (x, y)

        qv: dict[str, float] = {}

        # eat utility: effective drive if food present, else 0
        qv["eat"] = self.E_t if pos in food_pos else 0.0

        # movement utilities: V of target cell
        for action_name, (dx, dy) in self._MOVE_DELTAS.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                qv[action_name] = self.V.get((nx, ny), 0.0)
            else:
                qv[action_name] = -1.0  # invalid move

        qv["stay"] = 0.0
        return qv

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY.  Select an action based on the current internal state and
        perception.  No state mutation allowed here.
        """
        x = perception["x"]
        y = perception["y"]
        grid_w = perception["grid_width"]
        grid_h = perception["grid_height"]
        food_list = perception["resources"].get("food", [])

        pos = (x, y)
        food_positions = {(f["x"], f["y"]) for f in food_list}
        food_at_position = pos in food_positions

        # --- R3: V_perceived ---
        visible_cells = self._compute_visible_cells(x, y, grid_w, grid_h, food_list)
        V_perceived = self._compute_V_perceived(visible_cells)

        # --- R4: effective drive ---
        E_t = self.mu * self.H_t * V_perceived

        # --- R5: approach direction ---
        approach_action = self._compute_approach_action(x, y, grid_w, grid_h)

        # --- Threshold hierarchy ---

        # Rule D: hunger override — high hunger triggers eating unconditionally
        if food_at_position and self.H_t > self.hunger_override:
            return Action("eat")

        # Rule A: eat if food present and drive exceeds eat threshold
        if food_at_position and E_t >= self.theta_eat:
            return Action("eat")

        # Rule B: approach if drive exceeds approach threshold
        if E_t >= self.theta_approach:
            return Action(approach_action)

        # Rule C: stay — insufficient motivational drive
        return Action("stay")

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE.  Apply all ODE/learning rules and update state variables.
        Called after the environment has executed the action.
        """
        x = new_perception["x"]
        y = new_perception["y"]
        grid_w = new_perception["grid_width"]
        grid_h = new_perception["grid_height"]
        food_list = new_perception["resources"].get("food", [])
        last_result = new_perception.get("last_action_result", {})

        pos = (x, y)

        # Determine whether eating succeeded
        ate = 0.0
        if action.name == "eat":
            # The env sets consumed=True (or similar) on success
            consumed = last_result.get("consumed", False)
            if consumed or reward > 0.0:
                ate = 1.0

        # --- R1: Hunger ODE (Euler) ---
        self.H_t = self.H_t + self.dt * (
            self.c_H * (1.0 - self.H_t) - self.k_sat * ate
        )
        self.H_t = max(0.0, min(1.0, self.H_t))

        # --- R2: Associative strength update (Rescorla–Wagner + extinction) ---
        self.r_t = reward
        if self.r_t > 0.0:
            # Reinforcement
            old_v = self.V.get(pos, 0.0)
            new_v = old_v + self.alpha_V * (self.r_t - old_v)
            self.V[pos] = max(0.0, min(self.V_max, new_v))
        else:
            # Extinction decay at visited cell
            old_v = self.V.get(pos, 0.0)
            new_v = old_v - self.eta * old_v
            self.V[pos] = max(0.0, min(self.V_max, new_v))

        # --- R3: update V_perceived ---
        visible_cells = self._compute_visible_cells(x, y, grid_w, grid_h, food_list)
        self.V_perceived = self._compute_V_perceived(visible_cells)

        # --- R4: update effective drive ---
        self.E_t = self.mu * self.H_t * self.V_perceived

        # --- Update d_min ---
        if food_list:
            self.d_min = min(
                abs(f["x"] - x) + abs(f["y"] - y) for f in food_list
            )
        else:
            self.d_min = None

        # --- Update q_values ---
        self.q_values = self._compute_q_values(x, y, grid_w, grid_h, food_list)

    def get_state(self) -> dict:
        return {
            "H_t": self.H_t,
            "V": dict(self.V),           # shallow copy
            "E_t": self.E_t,
            "V_perceived": self.V_perceived,
            "r_t": self.r_t,
            "d_min": self.d_min,
            "q_values": dict(self.q_values),
        }
