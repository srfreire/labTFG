"""
Classical Wiener Process with Per-Action Accumulators
Implements the canonical drift-diffusion model (Ratcliff, 1978) as a discrete-time
Wiener process with independent parallel accumulators, one per candidate action.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

DIRECTION_DELTAS = {
    "move_up":    (0, -1),
    "move_down":  (0,  1),
    "move_left":  (-1, 0),
    "move_right": (1,  0),
}


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


class ClassicalWienerProcessWithPerActionAccumulatorsModel:
    """
    Drift-diffusion model with per-action evidence accumulators.

    Each of the 6 candidate actions has an independent accumulator that starts
    at z0 and integrates drift + Gaussian noise. The first to reach boundary `a`
    wins; if none does within T_max steps the highest accumulator wins.

    Reward history (r_bar) for the chosen action is updated via EMA after each
    environment step; non-chosen action histories decay toward zero.
    """

    def __init__(
        self,
        a: float = 1.5,
        sigma: float = 0.1,
        z0: float = 0.75,
        dt: float = 0.01,
        T_max: int = 100,
        k_res: float = 2.0,
        k_eat: float = 1.0,
        gamma: float = 0.9,
    ):
        # Parameters
        self.a = a
        self.sigma = sigma
        self.z0 = z0
        self.dt = dt
        self.T_max = T_max
        self.k_res = k_res
        self.k_eat = k_eat
        self.gamma = gamma

        # Variables – one per action
        self.evidence_accumulator: dict = {i: z0 for i in ACTIONS}   # X_i
        self.drift_rate: dict = {i: 0.0 for i in ACTIONS}             # v_i
        self.noise_sample: dict = {i: 0.0 for i in ACTIONS}           # xi_i
        self.reward_history: dict = {i: 0.0 for i in ACTIONS}         # r_bar_i

        # Last decision metadata
        self.chosen_action: str = "stay"      # R
        self.decision_time: int = 0           # T_d

        # Transient caches set during decide(), read in update()
        self._last_chosen: str = "stay"
        self._last_t_d: int = 0

        # q_values for simulation infrastructure (drift rate as utility proxy)
        self.q_values: dict = {i: 0.0 for i in ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_drift_rates(self, perception: dict) -> dict:
        """Rule R1: compute per-action drift rates from perception."""
        x = perception["x"]
        y = perception["y"]
        food_list = perception.get("resources", {}).get("food", [])

        food_on_cell = any(
            f["x"] == x and f["y"] == y for f in food_list
        )

        drift = {}
        for action in ACTIONS:
            if action in DIRECTION_DELTAS:
                dx, dy = DIRECTION_DELTAS[action]
                tx, ty = x + dx, y + dy
                if food_list:
                    d_i = min(_manhattan(tx, ty, f["x"], f["y"]) for f in food_list)
                else:
                    d_i = 1e6
                prox_i = 1.0 / (1.0 + d_i)
                eat_bonus = 0.0
            elif action == "eat":
                prox_i = 0.0
                eat_bonus = self.k_eat if food_on_cell else 0.0
            else:  # stay
                prox_i = 0.0
                eat_bonus = 0.0

            drift[action] = self.k_res * prox_i + eat_bonus + self.reward_history[action]

        return drift

    def _run_race(self, drift: dict) -> tuple:
        """
        Rules R2, R3, R4: run the stochastic accumulator race.
        Returns (chosen_action, decision_time).
        Also updates self.evidence_accumulator with final accumulator values.
        """
        X = {i: self.z0 for i in ACTIONS}
        sqrt_dt = math.sqrt(self.dt)

        chosen = None
        t_d = self.T_max

        for t in range(1, self.T_max + 1):
            # R2: update each accumulator
            for action in ACTIONS:
                xi = random.gauss(0.0, 1.0)
                self.noise_sample[action] = xi
                X[action] = (
                    X[action]
                    + drift[action] * self.dt
                    + self.sigma * sqrt_dt * xi
                )
                # reflecting lower boundary at 0, absorbing upper at a
                X[action] = max(0.0, min(X[action], self.a))

            # R3: check for boundary crossings
            winners = [i for i in ACTIONS if X[i] >= self.a]
            if winners:
                chosen = random.choice(winners)
                t_d = t
                break

        # R4: timeout fallback
        if chosen is None:
            chosen = max(ACTIONS, key=lambda i: X[i])

        # Cache final accumulator values
        self.evidence_accumulator = dict(X)

        return chosen, t_d

    # ------------------------------------------------------------------
    # DecisionModel contract
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY selection: compute drift rates from current perception,
        run the stochastic race, and return the winning action.
        Caches transient outputs (_last_chosen, _last_t_d) for use in update().
        """
        drift = self._compute_drift_rates(perception)

        # Cache drift rates for inspection (will be refreshed in update too)
        for act in ACTIONS:
            self.drift_rate[act] = drift[act]

        chosen, t_d = self._run_race(drift)

        # Store transient decision outputs
        self._last_chosen = chosen
        self._last_t_d = t_d

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply rule R5 (reward history EMA update) and refresh q_values.
        Records decision metadata from the most recent decide() call.
        """
        chosen = action.name

        # Record last decision outcomes
        self.chosen_action = chosen
        self.decision_time = self._last_t_d

        # R5: update reward history for chosen action
        self.reward_history[chosen] = (
            self.gamma * self.reward_history[chosen]
            + (1.0 - self.gamma) * reward
        )
        # R5: decay non-chosen actions toward 0
        for act in ACTIONS:
            if act != chosen:
                self.reward_history[act] = self.gamma * self.reward_history[act]

        # Recompute drift rates on new perception for q_values
        drift = self._compute_drift_rates(new_perception)
        for act in ACTIONS:
            self.drift_rate[act] = drift[act]
            # q_value = drift rate captures stimulus quality (P2) + reward history
            self.q_values[act] = drift[act]

    def get_state(self) -> dict:
        return {
            "evidence_accumulator": dict(self.evidence_accumulator),
            "drift_rate": dict(self.drift_rate),
            "noise_sample": dict(self.noise_sample),
            "reward_history": dict(self.reward_history),
            "chosen_action": self.chosen_action,
            "decision_time": self.decision_time,
            # Required by simulation infrastructure
            "q_values": dict(self.q_values),
        }
