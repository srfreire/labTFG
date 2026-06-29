"""
Algebraic Closed-Form DDM with Softmax Action Selection
Paradigm: drift-diffusion-model
Formulation: algebraic-closed-form-ddm-with-softmax-action-selection

Uses exact closed-form solutions for first-passage time statistics of the Wiener
process (Bogacz et al., 2006) to analytically compute per-action choice probability
and expected decision time. Actions are selected via softmax over composite values
that combine DDM-predicted accuracy, time cost, and learned Q-values.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']
DIRECTION_DELTAS = {
    'move_up':    (0, -1),
    'move_down':  (0,  1),
    'move_left':  (-1, 0),
    'move_right': (1,  0),
}


class AlgebraicClosedFormDdmWithSoftmaxActionSelectionModel:
    """
    Algebraic Closed-Form DDM with Softmax Action Selection.

    Per-step decision:
      1. Compute perceptual signals s_i from resource proximity.
      2. Derive drift rates v_i = k_v * s_i  (R1).
      3. Compute closed-form DDM accuracy P_i  (R2).
      4. Compute expected decision time T_bar_i  (R3).
      5. Form composite action value V_i = w_P*P_i - lambda_t*T_bar_i + w_Q*Q_i  (R4).
      6. Softmax sample over V_i with inverse temperature beta  (R5).
      7. In update(): TD update Q_chosen via reward  (R6).
    """

    def __init__(
        self,
        boundary_separation: float = 1.5,
        relative_starting_point: float = 0.5,
        diffusion_coefficient: float = 0.1,
        softmax_inverse_temperature: float = 5.0,
        learning_rate: float = 0.1,
        drift_rate_scaling: float = 1.0,
        time_cost_penalty: float = 0.1,
        accuracy_weight: float = 1.0,
        utility_weight: float = 0.5,
        zero_drift_guard: float = 0.0001,
    ):
        # Parameters
        self.a = boundary_separation
        self.z_rel = relative_starting_point
        self.sigma = diffusion_coefficient
        self.beta = softmax_inverse_temperature
        self.alpha = learning_rate
        self.k_v = drift_rate_scaling
        self.lambda_t = time_cost_penalty
        self.w_P = accuracy_weight
        self.w_Q = utility_weight
        self.epsilon = zero_drift_guard

        # State variables — per-action dicts
        self.s: Dict[str, float] = {a: 0.0 for a in ACTIONS}          # perceptual_signal
        self.v: Dict[str, float] = {a: 0.0 for a in ACTIONS}          # drift_rate
        self.P: Dict[str, float] = {a: 0.5 for a in ACTIONS}          # choice_probability
        self.T_bar: Dict[str, float] = {a: 0.0 for a in ACTIONS}      # expected_decision_time
        self.V: Dict[str, float] = {a: 0.0 for a in ACTIONS}          # composite_action_value
        self.pi: Dict[str, float] = {a: 1.0/len(ACTIONS) for a in ACTIONS}  # action_selection_prob
        self.Q: Dict[str, float] = {a: 0.0 for a in ACTIONS}          # learned_action_utility

        # q_values cache for get_state() — maps action name -> composite value V_i
        self.q_values: Dict[str, float] = {a: 0.0 for a in ACTIONS}

        # Track last chosen action for update()
        self._last_chosen: Optional[str] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _manhattan_distance(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    def _compute_perceptual_signals(
        self,
        pos: Tuple[int, int],
        food_list: List[dict],
        food_on_cell: bool,
    ) -> Dict[str, float]:
        """Compute s_i for each action from resource proximity."""
        signals = {}
        for action in ACTIONS:
            if action in DIRECTION_DELTAS:
                dx, dy = DIRECTION_DELTAS[action]
                neighbor = (pos[0] + dx, pos[1] + dy)
                if food_list:
                    d_i = min(
                        self._manhattan_distance(neighbor, (f['x'], f['y']))
                        for f in food_list
                    )
                else:
                    d_i = 1e9  # no food → large distance
                signals[action] = 1.0 / (1.0 + d_i)
            elif action == 'eat':
                signals[action] = 1.0 if food_on_cell else -0.5
            elif action == 'stay':
                signals[action] = 0.0
            else:
                signals[action] = 0.0
        return signals

    def _compute_ddm_stats(
        self, s_dict: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """
        Given perceptual signals, compute:
          v_i  (R1): drift rate
          P_i  (R2): closed-form choice probability
          T_bar_i (R3): expected decision time
        """
        v = {}
        P = {}
        T_bar = {}
        a = self.a
        sigma = self.sigma
        k_v = self.k_v
        epsilon = self.epsilon

        for action in ACTIONS:
            # R1
            vi = k_v * s_dict[action]
            v[action] = vi

            # R2: closed-form Wiener first-passage accuracy
            # P_i = 1 / (1 + exp(-2*v_i*a / sigma^2))
            exponent = -2.0 * vi * a / (sigma ** 2)
            # Clamp to avoid overflow
            exponent = max(-500.0, min(500.0, exponent))
            P[action] = 1.0 / (1.0 + math.exp(exponent))

            # R3: closed-form mean first-passage time
            if abs(vi) < epsilon:
                T_bar[action] = (a ** 2) / (2.0 * sigma ** 2)
            else:
                ratio = vi * a / (sigma ** 2)
                # Clamp tanh argument to avoid overflow (tanh saturates anyway)
                ratio = max(-500.0, min(500.0, ratio))
                T_bar[action] = (a / (2.0 * vi)) * math.tanh(ratio)

        return v, P, T_bar

    def _compute_composite_values(
        self,
        P: Dict[str, float],
        T_bar: Dict[str, float],
    ) -> Dict[str, float]:
        """R4: V_i = w_P * P_i - lambda_t * T_bar_i + w_Q * Q_i"""
        return {
            action: self.w_P * P[action] - self.lambda_t * T_bar[action] + self.w_Q * self.Q[action]
            for action in ACTIONS
        }

    def _softmax_probabilities(self, V: Dict[str, float]) -> Dict[str, float]:
        """R5: Numerically-stable softmax over composite values."""
        max_v = max(V.values())
        exps = {a: math.exp(self.beta * (V[a] - max_v)) for a in ACTIONS}
        total = sum(exps.values())
        return {a: exps[a] / total for a in ACTIONS}

    def _sample_categorical(self, probabilities: Dict[str, float]) -> str:
        """Sample an action from a categorical distribution."""
        r = random.random()
        cumulative = 0.0
        for action in ACTIONS:
            cumulative += probabilities[action]
            if r <= cumulative:
                return action
        return ACTIONS[-1]  # fallback

    # ------------------------------------------------------------------
    # DecisionModel contract
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: compute perceptual signals → DDM stats → composite values →
        softmax probabilities → sample action. No state mutation here.
        """
        # Step 1: Parse perception
        pos = (perception['x'], perception['y'])
        food_list = perception.get('resources', {}).get('food', [])
        food_on_cell = any(
            f['x'] == pos[0] and f['y'] == pos[1] for f in food_list
        )

        # Step 2: Compute perceptual signals
        s_dict = self._compute_perceptual_signals(pos, food_list, food_on_cell)

        # Steps 3–4: Drift rates and DDM stats
        v_dict, P_dict, T_bar_dict = self._compute_ddm_stats(s_dict)

        # Step 5: Composite values
        V_dict = self._compute_composite_values(P_dict, T_bar_dict)

        # Step 6: Softmax probabilities
        pi_dict = self._softmax_probabilities(V_dict)

        # Step 7: Sample action
        chosen = self._sample_categorical(pi_dict)

        # Cache chosen for update() traceability (not a state mutation — just bookkeeping)
        self._last_chosen = chosen

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        WRITE: apply all rules using new_perception.
          - Re-compute DDM stats, composite values, softmax probs from new_perception.
          - Update Q for the chosen action via TD rule (R6).
          - Refresh all cached state variables.
        """
        # Parse new perception
        pos = (new_perception['x'], new_perception['y'])
        food_list = new_perception.get('resources', {}).get('food', [])
        food_on_cell = any(
            f['x'] == pos[0] and f['y'] == pos[1] for f in food_list
        )

        # Recompute all quantities from new perception
        s_dict = self._compute_perceptual_signals(pos, food_list, food_on_cell)
        v_dict, P_dict, T_bar_dict = self._compute_ddm_stats(s_dict)
        V_dict = self._compute_composite_values(P_dict, T_bar_dict)
        pi_dict = self._softmax_probabilities(V_dict)

        # R6: TD update for chosen action
        chosen = action.name
        if chosen in self.Q:
            self.Q[chosen] = self.Q[chosen] + self.alpha * (reward - self.Q[chosen])

        # Recompute V after Q update (so q_values reflects updated Q)
        V_dict_updated = self._compute_composite_values(P_dict, T_bar_dict)
        pi_dict_updated = self._softmax_probabilities(V_dict_updated)

        # Persist state variables
        self.s = s_dict
        self.v = v_dict
        self.P = P_dict
        self.T_bar = T_bar_dict
        self.V = V_dict_updated
        self.pi = pi_dict_updated

        # Update q_values cache (V_i is the natural "action score" here)
        self.q_values = dict(V_dict_updated)

    def get_state(self) -> dict:
        """Return snapshot of all model state variables."""
        return {
            # Per-action dicts
            'perceptual_signal': dict(self.s),
            'drift_rate': dict(self.v),
            'choice_probability': dict(self.P),
            'expected_decision_time': dict(self.T_bar),
            'composite_action_value': dict(self.V),
            'action_selection_probability': dict(self.pi),
            'learned_action_utility': dict(self.Q),
            # Required by simulation infrastructure
            'q_values': dict(self.q_values),
            # Parameters (for diagnostics)
            'boundary_separation': self.a,
            'relative_starting_point': self.z_rel,
            'diffusion_coefficient': self.sigma,
            'softmax_inverse_temperature': self.beta,
            'learning_rate': self.alpha,
            'drift_rate_scaling': self.k_v,
            'time_cost_penalty': self.lambda_t,
            'accuracy_weight': self.w_P,
            'utility_weight': self.w_Q,
            'zero_drift_guard': self.epsilon,
        }
