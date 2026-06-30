"""
Collapsing-Boundary ODE Accumulators with Lateral Inhibition
Leaky Competing Accumulator (LCA) model with coupled ODEs, lateral inhibition,
and a time-dependent urgency signal that collapses the effective decision threshold.

Based on Usher & McClelland (2001) and the collapsing-boundary extension
described by Bogacz et al. (2006) and Gold & Shadlen (2007).
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# Canonical action set
ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']

DIRECTION_DELTAS = {
    'move_up':    (0, -1),
    'move_down':  (0,  1),
    'move_left':  (-1, 0),
    'move_right': (1,  0),
}


class CollapsingBoundaryOdeAccumulatorsWithLateralInhibitionModel:
    """
    Leaky Competing Accumulator (LCA) model with collapsing decision boundary.

    Per-step decision:
      1. Compute perceptual signals s_i from environment perception.
      2. Compute input drives v_i = k_v * s_i + r_bar_i (R1).
      3. Run coupled ODE accumulators with leak, lateral inhibition, Gaussian noise (R2).
      4. Apply collapsing threshold: theta_t = max(a - mu*t, theta_min) (R3, R4).
      5. First accumulator to cross theta_t wins (R5); tie → random choice.
      6. Timeout fallback: argmax activations at T_max (R6).

    update():
      - Reward trace TD update for chosen action: r_bar_R += alpha*(reward - r_bar_R) (R7).
      - Recompute q_values (utilities) for get_state().
    """

    def __init__(
        self,
        a: float = 1.5,
        kappa: float = 0.15,
        w: float = 0.05,
        sigma: float = 0.1,
        dt: float = 0.01,
        T_max: int = 100,
        mu: float = 0.01,
        theta_min: float = 0.3,
        k_v: float = 1.5,
        alpha: float = 0.1,
        seed: Optional[int] = None,
    ):
        # Parameters
        self.a = a
        self.kappa = kappa
        self.w = w
        self.sigma = sigma
        self.dt = dt
        self.T_max = T_max
        self.mu = mu
        self.theta_min = theta_min
        self.k_v = k_v
        self.alpha = alpha

        # RNG
        self._rng = random.Random(seed)

        # State variables — one per action
        self.accumulator_activation: Dict[str, float] = {a: 0.0 for a in ACTIONS}
        self.input_drive: Dict[str, float] = {a: 0.0 for a in ACTIONS}
        self.perceptual_signal: Dict[str, float] = {a: 0.0 for a in ACTIONS}
        self.reward_trace: Dict[str, float] = {a: 0.0 for a in ACTIONS}

        # Threshold / urgency state
        self.effective_threshold: float = a
        self.urgency_signal: float = 0.0

        # Chosen action
        self.chosen_action: str = 'stay'

        # Q-values (utility proxy: input drives, updated in update())
        self.q_values: Dict[str, float] = {a: 0.0 for a in ACTIONS}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _manhattan_distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        return float(abs(x1 - x2) + abs(y1 - y2))

    def _compute_perceptual_signals(self, perception: dict) -> Dict[str, float]:
        """Compute s_i for each action given current perception."""
        px = perception['x']
        py = perception['y']
        resources = perception.get('resources', {})
        food_list: List[dict] = resources.get('food', [])

        food_on_cell = any(
            f.get('x') == px and f.get('y') == py for f in food_list
        )

        signals: Dict[str, float] = {}

        for action in ACTIONS:
            if action in DIRECTION_DELTAS:
                dx, dy = DIRECTION_DELTAS[action]
                nx, ny = px + dx, py + dy
                if food_list:
                    d_i = min(
                        self._manhattan_distance(nx, ny, f.get('x', 0), f.get('y', 0))
                        for f in food_list
                    )
                else:
                    d_i = 1e6  # no food → large distance
                signals[action] = 1.0 / (1.0 + d_i)

            elif action == 'eat':
                signals[action] = 1.0 if food_on_cell else -0.5

            elif action == 'stay':
                signals[action] = 0.0

            else:
                signals[action] = 0.0

        return signals

    def _compute_input_drives(
        self, signals: Dict[str, float]
    ) -> Dict[str, float]:
        """R1: v_i = k_v * s_i + r_bar_i"""
        return {
            action: self.k_v * signals[action] + self.reward_trace[action]
            for action in ACTIONS
        }

    def _run_ode_race(
        self, drives: Dict[str, float]
    ) -> str:
        """
        Run coupled ODE accumulators under collapsing boundary (R2–R6).
        Returns the chosen action name.
        """
        x: Dict[str, float] = {a: 0.0 for a in ACTIONS}
        sqrt_dt = math.sqrt(self.dt)
        chosen: Optional[str] = None

        for t in range(1, self.T_max + 1):
            # R3: urgency signal
            u_t = self.mu * t
            # R4: collapsing threshold
            theta_t = max(self.a - u_t, self.theta_min)

            # R2: Euler-discretized LCA ODE for all accumulators simultaneously
            x_new: Dict[str, float] = {}
            for action in ACTIONS:
                sum_others = sum(x[j] for j in ACTIONS if j != action)
                noise = self._rng.gauss(0.0, 1.0)
                delta = (
                    self.dt * (drives[action] - self.kappa * x[action] - self.w * sum_others)
                    + self.sigma * sqrt_dt * noise
                )
                x_new[action] = max(0.0, x[action] + delta)

            x = x_new

            # R5: boundary crossing check
            winners = [a for a in ACTIONS if x[a] >= theta_t]
            if winners:
                chosen = self._rng.choice(winners)
                break

        # R6: timeout fallback
        if chosen is None:
            chosen = max(ACTIONS, key=lambda a: x[a])

        # Store final accumulator state and threshold for get_state()
        self.accumulator_activation = dict(x)
        self.urgency_signal = self.mu * self.T_max
        self.effective_threshold = max(self.a - self.urgency_signal, self.theta_min)

        return chosen

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: compute perceptual signals, input drives, run ODE race,
        return chosen action. No state mutation.
        """
        signals = self._compute_perceptual_signals(perception)
        drives = self._compute_input_drives(signals)
        chosen = self._run_ode_race(drives)

        # Cache last perceptual state for get_state() inspection (non-variable mutation)
        self.perceptual_signal = signals
        self.input_drive = drives
        self.chosen_action = chosen

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: apply R7 (reward trace TD update) and refresh q_values.
        """
        chosen = action.name

        # R7: temporal-difference update for chosen action's reward trace
        self.reward_trace[chosen] = (
            self.reward_trace[chosen]
            + self.alpha * (reward - self.reward_trace[chosen])
        )

        # Recompute input drives from new perception for q_values snapshot
        signals = self._compute_perceptual_signals(new_perception)
        drives = self._compute_input_drives(signals)

        # q_values = input drives (utility proxy for each action)
        self.q_values = {a: drives[a] for a in ACTIONS}

        # Update perceptual/drive state
        self.perceptual_signal = signals
        self.input_drive = drives

    def get_state(self) -> dict:
        """Return a snapshot of all internal state variables."""
        return {
            'accumulator_activation': dict(self.accumulator_activation),
            'input_drive': dict(self.input_drive),
            'perceptual_signal': dict(self.perceptual_signal),
            'reward_trace': dict(self.reward_trace),
            'effective_threshold': self.effective_threshold,
            'urgency_signal': self.urgency_signal,
            'chosen_action': self.chosen_action,
            'q_values': dict(self.q_values),
            # Parameters
            'a': self.a,
            'kappa': self.kappa,
            'w': self.w,
            'sigma': self.sigma,
            'dt': self.dt,
            'T_max': self.T_max,
            'mu': self.mu,
            'theta_min': self.theta_min,
            'k_v': self.k_v,
            'alpha': self.alpha,
        }
