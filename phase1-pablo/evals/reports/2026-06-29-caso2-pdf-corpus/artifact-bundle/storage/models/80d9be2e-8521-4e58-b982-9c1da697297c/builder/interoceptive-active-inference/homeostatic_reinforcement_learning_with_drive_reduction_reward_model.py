"""
Homeostatic Reinforcement Learning with Drive-Reduction Reward
Formulation: homeostatic-reinforcement-learning-with-drive-reduction-reward
Paradigm: interoceptive-active-inference

Implements Keramati & Gutkin (2014): drive-reduction as intrinsic reward signal,
TD(0) Q-learning over discretized (distance-to-food × energy) state space,
with urgency-modulated softmax action selection.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class HomeostaticReinforcementLearningWithDriveReductionRewardModel:
    """
    Value-based TD RL agent with drive-reduction reward.

    State space: 5 distance bins × 5 energy bins = 25 discrete states
    Actions: move_up, move_down, move_left, move_right, stay, eat
    Reward: r(t) = D(h_old) - D(h_new), where D(h) = m * |h* - h|^n
    """

    ALL_ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
    MOVE_ACTIONS = {"move_up", "move_down", "move_left", "move_right"}

    def __init__(
        self,
        homeostatic_setpoint: float = 0.8,
        drive_sensitivity: float = 4.0,
        drive_exponent: float = 2.0,
        temporal_discount_factor: float = 0.9,
        learning_rate_td: float = 0.1,
        action_inverse_temperature: float = 8.0,
        urgency_inverse_temperature: float = 15.0,
        critical_energy_threshold: float = 0.2,
        metabolic_cost_move: float = 0.05,
        metabolic_cost_stay: float = 0.02,
        energy_gain_from_eating: float = 0.3,
        distance_discretization_bins: int = 5,
        energy_discretization_bins: int = 5,
        seed: int = None,
    ):
        # Parameters
        self.h_star = homeostatic_setpoint
        self.m = drive_sensitivity
        self.n = drive_exponent
        self.gamma = temporal_discount_factor
        self.alpha = learning_rate_td
        self.beta = action_inverse_temperature
        self.beta_urgent = urgency_inverse_temperature
        self.h_critical = critical_energy_threshold
        self.c_move = metabolic_cost_move
        self.c_stay = metabolic_cost_stay
        self.k_eat = energy_gain_from_eating
        self.n_dist_bins = distance_discretization_bins
        self.n_energy_bins = energy_discretization_bins

        # State variables
        self.h_t: float = 0.5                # physiological_state (energy)
        self.D_t: float = self._drive(0.5)   # current drive
        self.r_t: float = 0.0                # last reward
        self.Q: dict = {}                    # Q-table: {(state_tuple, action_str): float}
        self.s_t: tuple = None               # current discretized state

        # Internal bookkeeping for update()
        self._s_old: tuple = None
        self._h_old: float = 0.5
        self._last_action_name: str = None

        # q_values cache for get_state() — flat dict[action_str → float]
        self._q_values: dict = {a: 0.0 for a in self.ALL_ACTIONS}

        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _drive(self, h: float) -> float:
        """D(h) = m * |h* - h|^n  (R2)"""
        return self.m * (abs(self.h_star - h) ** self.n)

    def _digitize_dist(self, dist: float) -> int:
        """
        Bin boundaries: 0 (at resource), 1-2 (near), 3-4 (med), 5-7 (far), 8+ (very far)
        Returns bin index in [0, n_dist_bins-1]
        """
        if dist == 0:
            return 0
        elif dist <= 2:
            return 1
        elif dist <= 4:
            return 2
        elif dist <= 7:
            return 3
        else:
            return 4

    def _digitize_energy(self, h: float) -> int:
        """Energy bins: [0,0.2), [0.2,0.4), [0.4,0.6), [0.6,0.8), [0.8,1.0]"""
        bin_idx = int(h * self.n_energy_bins)
        return max(0, min(self.n_energy_bins - 1, bin_idx))

    def _discretize_state(self, perception: dict, h: float) -> tuple:
        """R4: Compute (dist_bin, energy_bin) from perception and current energy."""
        x = perception["x"]
        y = perception["y"]
        food_list = perception.get("resources", {}).get("food", [])

        if food_list:
            dist_to_nearest = min(
                abs(f["x"] - x) + abs(f["y"] - y) for f in food_list
            )
        else:
            dist_to_nearest = perception.get("grid_width", 10) + perception.get("grid_height", 10)

        dist_bin = self._digitize_dist(dist_to_nearest)
        energy_bin = self._digitize_energy(h)
        return (dist_bin, energy_bin)

    def _q_get(self, state: tuple, action: str) -> float:
        return self.Q.get((state, action), 0.0)

    def _softmax(self, logits: list) -> list:
        """Numerically stable softmax."""
        max_l = max(logits)
        exps = [math.exp(l - max_l) for l in logits]
        total = sum(exps)
        return [e / total for e in exps]

    def _update_q_values_cache(self, state: tuple) -> None:
        """Refresh self._q_values for get_state()."""
        self._q_values = {a: self._q_get(state, a) for a in self.ALL_ACTIONS}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: Discretize state, compute softmax over Q-values, sample action.
        Does NOT modify any internal state.
        """
        x = perception["x"]
        y = perception["y"]
        food_list = perception.get("resources", {}).get("food", [])

        # Check if food is at current position
        food_at_pos = any(
            f["x"] == x and f["y"] == y for f in food_list
        )

        # R4: Discretize state
        s_t = self._discretize_state(perception, self.h_t)

        # R6: Urgency-modulated inverse temperature
        effective_beta = self.beta_urgent if self.h_t < self.h_critical else self.beta

        # Build logits for each action
        logits = []
        for a in self.ALL_ACTIONS:
            q_val = self._q_get(s_t, a)
            logit = effective_beta * q_val
            if a == "eat" and not food_at_pos:
                logit = -1e9  # mask eat when no food present
            logits.append(logit)

        probs = self._softmax(logits)

        # Sample action
        r = random.random()
        cumulative = 0.0
        chosen_idx = len(self.ALL_ACTIONS) - 1
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                chosen_idx = i
                break

        chosen_action = self.ALL_ACTIONS[chosen_idx]

        # Snapshot old state for update() — bookkeeping, not a state variable mutation
        self._s_old = s_t
        self._h_old = self.h_t

        return Action(name=chosen_action)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply all rules: energy update (R1), drive & reward (R2, R3),
        new state (R4), TD Q-update (R5). Cache q_values.
        """
        action_name = action.name
        last_result = new_perception.get("last_action_result", {})

        # R1: Physiological state dynamics
        h_old = self._h_old
        h_new = h_old  # start from old value

        if action_name == "eat":
            # Check if food was consumed via various possible result keys
            consumed = (
                bool(last_result.get("consumed", False))
                or bool(last_result.get("food_eaten", False))
                or bool(last_result.get("success", False))
            )
            if consumed:
                food_pal = float(last_result.get("palatability", 1.0))
                h_new = min(1.0, max(0.0, h_old + self.k_eat * food_pal))
            else:
                # Eat failed — apply stay cost
                h_new = min(1.0, max(0.0, h_old - self.c_stay))
        elif action_name in self.MOVE_ACTIONS:
            h_new = min(1.0, max(0.0, h_old - self.c_move))
        else:
            # stay or unknown
            h_new = min(1.0, max(0.0, h_old - self.c_stay))

        # R2, R3: Drive and drive-reduction reward
        D_old = self._drive(h_old)
        D_new = self._drive(h_new)
        r_t = D_old - D_new  # positive = moved toward setpoint

        # R4: New discretized state
        s_new = self._discretize_state(new_perception, h_new)

        # R5: TD(0) Q-value update
        s_old = self._s_old if self._s_old is not None else s_new

        max_q_new = max(self._q_get(s_new, a) for a in self.ALL_ACTIONS)
        td_target = r_t + self.gamma * max_q_new
        td_error = td_target - self._q_get(s_old, action_name)
        self.Q[(s_old, action_name)] = self._q_get(s_old, action_name) + self.alpha * td_error

        # Commit state updates
        self.h_t = h_new
        self.D_t = D_new
        self.r_t = r_t
        self.s_t = s_new

        # Update q_values cache for new state
        self._update_q_values_cache(s_new)

    def get_state(self) -> dict:
        return {
            "physiological_state": self.h_t,
            "homeostatic_setpoint": self.h_star,
            "drive": self.D_t,
            "primary_reward": self.r_t,
            "state_representation": self.s_t,
            "q_table_size": len(self.Q),
            "q_values": dict(self._q_values),
        }
