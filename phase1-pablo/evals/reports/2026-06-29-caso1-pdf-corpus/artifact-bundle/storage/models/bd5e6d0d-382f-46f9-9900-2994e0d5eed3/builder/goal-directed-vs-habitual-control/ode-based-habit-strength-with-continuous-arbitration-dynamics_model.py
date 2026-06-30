"""
ODE-Based Habit Strength with Continuous Arbitration Dynamics
=============================================================
Continuous-time ODE-inspired dual-system agent where habit strength,
goal-directed value, and a depletable cognitive control capacity co-evolve
over discrete Euler time steps.

References:
  Rangel, Camerer & Montague (2008) Nature Reviews Neuroscience, 9, 545-556.
  Rangel (2013) Nature Neuroscience, 16(12), 1717-1724.
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


class OdeBasedHabitStrengthWithContinuousArbitrationDynamicsModel:
    """
    Dual-system (goal-directed vs habitual) agent with:
      - Habit strength H(s, a)  updated via discrete Euler ODE steps.
      - Goal-directed value V_GD(s, a) recomputed each step from a learned
        transition model p_hat and hunger-modulated desirability r_D.
      - Cognitive control capacity C  that depletes on GD use and recovers
        on habitual use, gating system selection stochastically.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        tau_H: float = 0.03,
        tau_D: float = 0.005,
        alpha_T: float = 0.20,
        C_max: float = 1.0,
        rho: float = 0.05,
        xi: float = 0.10,
        theta: float = 0.15,
        gamma: float = 0.95,
        eta: float = 0.02,
        phi: float = 0.30,
        r_food: float = 1.0,
        c_step: float = -0.01,
        beta: float = 5.0,
    ):
        # Parameters
        self.tau_H = tau_H
        self.tau_D = tau_D
        self.alpha_T = alpha_T
        self.C_max = C_max
        self.rho = rho
        self.xi = xi
        self.theta = theta
        self.gamma = gamma
        self.eta = eta
        self.phi = phi
        self.r_food = r_food
        self.c_step = c_step
        self.beta = beta

        # State variables
        self.h: float = 0.5                  # hunger drive
        self.C: float = 1.0                  # cognitive control capacity
        self.H: dict = {}                    # habit strengths H[(s, a)]
        self.p_hat: dict = {}                # transition model p_hat[(s, a, o)]
        self.V_GD: dict = {}                 # goal-directed values V_GD[(s, a)] – cached

        # Composite action urgency for the last decide() call (used in get_state)
        self._U: dict = {a: 0.0 for a in ACTIONS}
        # q_values for get_state (updated after update())
        self._q_values: dict = {a: 0.0 for a in ACTIONS}

        # Flags set during decide(), consumed by update()
        self._use_gd: bool = True            # which system was chosen last step
        self._last_s: tuple = (0, 0)         # state at last decide()
        self._p_GD: float = 1.0              # cached p_GD

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def _apply_move(self, s: tuple, action: str) -> tuple:
        x, y = s
        if action == "move_up":
            return (x, y + 1)
        if action == "move_down":
            return (x, y - 1)
        if action == "move_left":
            return (x - 1, y)
        if action == "move_right":
            return (x + 1, y)
        return (x, y)

    def _clamp_to_grid(self, s: tuple, gw: int, gh: int) -> tuple:
        return (self._clamp(s[0], 0, gw - 1), self._clamp(s[1], 0, gh - 1))

    def _softmax(self, values: list) -> list:
        """Numerically stable softmax."""
        m = max(values)
        exps = [math.exp(v - m) for v in values]
        s = sum(exps)
        return [e / s for e in exps]

    def _p_hat_get(self, s: tuple, a: str, o: str) -> float:
        return self.p_hat.get((s, a, o), 0.5)

    def _H_get(self, s: tuple, a: str) -> float:
        return self.H.get((s, a), 0.0)

    def _compute_p_GD(self) -> float:
        """R6: system-selection probability."""
        if self.C >= self.theta:
            return self.C
        return 0.0

    def _compute_V_GD(
        self, s: tuple, food_here: bool, gw: int, gh: int
    ) -> dict:
        """R3: recompute goal-directed values for all actions."""
        r_D_food = self.h * self.r_food
        r_D_nofood = self.c_step
        V = {}
        for a in ACTIONS:
            if a == "eat" and food_here:
                p_f = self._p_hat_get(s, a, "food")
                V[a] = p_f * r_D_food + (1.0 - p_f) * r_D_nofood
            elif a in ("move_up", "move_down", "move_left", "move_right"):
                s_next = self._clamp_to_grid(self._apply_move(s, a), gw, gh)
                best_future_H = max(self._H_get(s_next, a2) for a2 in ACTIONS)
                if best_future_H > 0:
                    V[a] = self.c_step + self.gamma * best_future_H * r_D_food
                else:
                    V[a] = self.c_step
            else:
                # eat with no food here, or stay
                V[a] = self.c_step
        return V

    # ------------------------------------------------------------------
    # decide  (READ-ONLY)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        Select an action based on current state.
        Reads self.* variables but NEVER modifies them.
        """
        x = perception.get("x", 0)
        y = perception.get("y", 0)
        gw = perception.get("grid_width", 10)
        gh = perception.get("grid_height", 10)

        s = (x, y)
        self._last_s = s  # store for update() — read-only w.r.t. model state

        resources = perception.get("resources", {})
        food_list = resources.get("food", [])
        food_here = any(f.get("x") == x and f.get("y") == y for f in food_list)

        # R6: gate
        p_GD = self._compute_p_GD()
        self._p_GD = p_GD  # cache for get_state

        # R7: stochastic system selection
        u = random.random()
        if u < p_GD:
            use_gd = True
            V = self._compute_V_GD(s, food_here, gw, gh)
            U = {a: V[a] for a in ACTIONS}
        else:
            use_gd = False
            U = {a: self._H_get(s, a) for a in ACTIONS}

        self._use_gd = use_gd   # store flag for update()
        self._U = dict(U)

        # R8: softmax selection
        scores = [self.beta * U[a] for a in ACTIONS]
        probs = self._softmax(scores)
        chosen = random.choices(ACTIONS, weights=probs, k=1)[0]

        return Action(name=chosen)

    # ------------------------------------------------------------------
    # update  (ALL state mutations happen here)
    # ------------------------------------------------------------------

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all rules R1–R9 and refresh q_values.
        """
        s = self._last_s
        a_exec = action.name
        last_result = new_perception.get("last_action_result", {})

        # Determine whether food was consumed
        ate_food = (a_exec == "eat") and bool(last_result.get("consumed", False))

        # Actual received reward
        r_received = self.r_food if ate_food else self.c_step

        # R1: Hunger dynamics
        self.h = self._clamp(
            self.h + self.eta - self.phi * (1.0 if ate_food else 0.0), 0.0, 1.0
        )

        # R4: Habit strength ODE (Euler step)
        r_pos = max(r_received, 0.0)
        old_H_exec = self._H_get(s, a_exec)
        new_H_exec = max(
            old_H_exec + self.tau_H * r_pos - self.tau_D * old_H_exec, 0.0
        )
        self.H[(s, a_exec)] = new_H_exec

        # Passive decay for all other (s_i, a_i) pairs
        keys_to_decay = [k for k in self.H if k != (s, a_exec)]
        for k in keys_to_decay:
            self.H[k] = max(self.H[k] - self.tau_D * self.H[k], 0.0)

        # R9: Transition model update
        o_obs = "food" if ate_food else "nofood"
        # Update toward 1 for observed outcome
        old_p_obs = self._p_hat_get(s, a_exec, o_obs)
        self.p_hat[(s, a_exec, o_obs)] = old_p_obs + self.alpha_T * (1.0 - old_p_obs)
        # Update toward 0 for other outcomes
        for o in OUTCOMES:
            if o != o_obs:
                old_p_other = self._p_hat_get(s, a_exec, o)
                self.p_hat[(s, a_exec, o)] = old_p_other + self.alpha_T * (0.0 - old_p_other)

        # R5: Cognitive control capacity dynamics
        if self._use_gd:
            self.C = self._clamp(
                self.C + self.rho * (self.C_max - self.C) - self.xi, 0.0, self.C_max
            )
        else:
            self.C = self._clamp(
                self.C + self.rho * (self.C_max - self.C), 0.0, self.C_max
            )

        # Refresh q_values from the urgency signals used in the last decide()
        # This gives inspectable action scores aligned with the actual decision
        self._q_values = dict(self._U)

    # ------------------------------------------------------------------
    # get_state
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "h": self.h,
            "C": self.C,
            "p_GD": self._p_GD,
            "H": dict(self.H),
            "p_hat": dict(self.p_hat),
            "V_GD": dict(self.V_GD),
            "use_gd": self._use_gd,
            "q_values": dict(self._q_values),
        }
