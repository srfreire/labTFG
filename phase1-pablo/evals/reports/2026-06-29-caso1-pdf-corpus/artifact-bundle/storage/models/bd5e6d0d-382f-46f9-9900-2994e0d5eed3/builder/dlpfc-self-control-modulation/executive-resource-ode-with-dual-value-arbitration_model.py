"""
Executive Resource ODE with Dual-Value Arbitration Model

Implements a continuous-time ODE governing depletable executive (dlPFC) resource
dynamics, combined with a dual-system architecture where an impulsive controller
(taste-driven) competes with a goal-directed controller (health-integrated).
An arbitration weight derived from executive capacity determines the mixture.

Based on Rangel et al. (2008) and Rangel (2013).
"""

import math
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


class ExecutiveResourceOdeWithDualValueArbitrationModel:
    """
    Dual-value arbitration model with ODE-based executive resource dynamics.

    Variables:
        E      - executive capacity (depletable dlPFC resource)
        V_I    - impulsive value (taste-driven, Pavlovian/habitual)
        V_G    - goal-directed value (taste + health weighted)
        V      - integrated arbitrated value
        omega  - arbitration weight (E^2)
        ctrl   - control exertion flag (conflict indicator)

    Parameters:
        alpha_E  - depletion rate
        beta_E   - recovery rate
        theta    - override threshold (min E for conflict override)
        epsilon  - stochastic lapse rate
        alpha_Q  - habit learning rate
        gamma    - distance discount factor
        w_h_G    - health weight for goal-directed system
        w_tau_G  - taste weight for goal-directed system
    """

    # All candidate movement/stay actions (eat added dynamically)
    BASE_ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay']
    ALL_ACTIONS = ['move_up', 'move_down', 'move_left', 'move_right', 'stay', 'eat']

    def __init__(
        self,
        depletion_rate: float = 0.08,
        recovery_rate: float = 0.04,
        override_threshold: float = 0.3,
        stochastic_lapse_rate: float = 0.1,
        habit_learning_rate: float = 0.1,
        distance_discount_factor: float = 0.9,
        health_weight_goal_directed: float = 0.6,
        taste_weight_goal_directed: float = 0.4,
        seed: int = None,
    ):
        # Parameters
        self.alpha_E = depletion_rate
        self.beta_E = recovery_rate
        self.theta = override_threshold
        self.epsilon = stochastic_lapse_rate
        self.alpha_Q = habit_learning_rate
        self.gamma = distance_discount_factor
        self.w_h_G = health_weight_goal_directed
        self.w_tau_G = taste_weight_goal_directed

        # Core state variables
        self.E: float = 1.0        # executive capacity
        self.V_I: float = 0.0      # impulsive value (scalar for chosen action)
        self.V_G: float = 0.0      # goal-directed value (scalar for chosen action)
        self.V: float = 0.0        # integrated value (scalar for chosen action)
        self.omega: float = 1.0    # arbitration weight
        self.ctrl: int = 0         # control exertion flag

        # Habit Q-values: keyed by (state_hash, action_name) -> float
        self.Q_habit: dict = defaultdict(float)

        # Memory for update step
        self._last_action_name: str = None
        self._last_position: tuple = None
        self._last_food_config_key: tuple = None

        # Cached per-action value dicts for q_values reporting
        self._vi_dict: dict = {a: 0.0 for a in self.ALL_ACTIONS}
        self._vg_dict: dict = {a: 0.0 for a in self.ALL_ACTIONS}
        self._v_dict: dict = {a: 0.0 for a in self.ALL_ACTIONS}

        # RNG
        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
        return abs(x1 - x2) + abs(y1 - y2)

    @staticmethod
    def _next_position(action_name: str, x: int, y: int) -> tuple:
        """Returns (nx, ny) after executing the given movement action."""
        if action_name == 'move_up':
            return (x, y - 1)
        elif action_name == 'move_down':
            return (x, y + 1)
        elif action_name == 'move_left':
            return (x - 1, y)
        elif action_name == 'move_right':
            return (x + 1, y)
        elif action_name in ('stay', 'eat'):
            return (x, y)
        return (x, y)

    def _compute_impulsive_values(
        self, candidate_actions: list, x: int, y: int, visible_foods: list
    ) -> dict:
        """
        R2: V_I[a] = best reachable food palatability * gamma^distance.
        For eat: food must be at current position (dist=0).
        For moves: find best food toward that direction.
        """
        vi = {}
        for action in candidate_actions:
            nx, ny = self._next_position(action, x, y)

            if action == 'eat':
                # Only foods at current position
                foods_here = [
                    f for f in visible_foods
                    if f.get('x', -1) == x and f.get('y', -1) == y
                ]
                if foods_here:
                    best_pal = max(f.get('palatability', 0.0) for f in foods_here)
                    vi[action] = best_pal  # dist=0, gamma^0=1
                else:
                    vi[action] = 0.0
            elif action == 'stay':
                # Staying: no approach, any food at current pos
                foods_here = [
                    f for f in visible_foods
                    if f.get('x', -1) == x and f.get('y', -1) == y
                ]
                if foods_here:
                    best_pal = max(f.get('palatability', 0.0) for f in foods_here)
                    vi[action] = best_pal  # dist=0
                else:
                    # No food here: find nearest food overall
                    if visible_foods:
                        # Value of staying = 0 (no closer to food)
                        vi[action] = 0.0
                    else:
                        vi[action] = 0.0
            else:
                # Movement: find the best food considering distance after the step
                if not visible_foods:
                    vi[action] = 0.0
                else:
                    best_score = 0.0
                    for f in visible_foods:
                        fx, fy = f.get('x', 0), f.get('y', 0)
                        dist = self._manhattan_distance(nx, ny, fx, fy)
                        score = f.get('palatability', 0.0) * (self.gamma ** dist)
                        if score > best_score:
                            best_score = score
                    vi[action] = best_score

            # Blend with cached habit Q-value if available
            state_key = self._make_state_key(x, y, visible_foods)
            habit_val = self.Q_habit.get((state_key, action), 0.0)
            vi[action] = max(vi[action], habit_val)

        return vi

    def _compute_goal_directed_values(
        self, candidate_actions: list, x: int, y: int, visible_foods: list
    ) -> dict:
        """
        R3: V_G[a] = (w_tau_G * taste + w_h_G * health) * gamma^dist.
        health = 1 - palatability.
        """
        vg = {}
        for action in candidate_actions:
            nx, ny = self._next_position(action, x, y)

            if action == 'eat':
                foods_here = [
                    f for f in visible_foods
                    if f.get('x', -1) == x and f.get('y', -1) == y
                ]
                if foods_here:
                    best_score = max(
                        self.w_tau_G * f.get('palatability', 0.0)
                        + self.w_h_G * (1.0 - f.get('palatability', 0.0))
                        for f in foods_here
                    )
                    vg[action] = best_score
                else:
                    vg[action] = 0.0
            elif action == 'stay':
                foods_here = [
                    f for f in visible_foods
                    if f.get('x', -1) == x and f.get('y', -1) == y
                ]
                if foods_here:
                    best_score = max(
                        self.w_tau_G * f.get('palatability', 0.0)
                        + self.w_h_G * (1.0 - f.get('palatability', 0.0))
                        for f in foods_here
                    )
                    vg[action] = best_score
                else:
                    vg[action] = 0.0
            else:
                if not visible_foods:
                    vg[action] = 0.0
                else:
                    best_score = 0.0
                    for f in visible_foods:
                        fx, fy = f.get('x', 0), f.get('y', 0)
                        dist = self._manhattan_distance(nx, ny, fx, fy)
                        taste = f.get('palatability', 0.0)
                        health = 1.0 - taste
                        composite = self.w_tau_G * taste + self.w_h_G * health
                        score = composite * (self.gamma ** dist)
                        if score > best_score:
                            best_score = score
                    vg[action] = best_score

        return vg

    @staticmethod
    def _argmax(value_dict: dict) -> str:
        """Return action with highest value."""
        return max(value_dict, key=lambda k: value_dict[k])

    @staticmethod
    def _make_state_key(x: int, y: int, visible_foods: list) -> tuple:
        """
        Discretize state for habit learning: position + sorted food config.
        """
        food_sig = tuple(sorted(
            (f.get('x', 0), f.get('y', 0), round(f.get('palatability', 0.0), 1))
            for f in visible_foods
        ))
        return (x, y, food_sig)

    # ------------------------------------------------------------------
    # DecisionModel interface
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> Action:
        """
        READ-ONLY: select an action based on current state variables.
        Uses pre-computed value dicts from last update (or initial zeros).
        On the first step, computes values on-the-fly from perception.
        """
        x = perception.get('x', 0)
        y = perception.get('y', 0)
        visible_foods = perception.get('resources', {}).get('food', [])

        # Build candidate actions
        food_at_pos = [
            f for f in visible_foods
            if f.get('x', -1) == x and f.get('y', -1) == y
        ]
        candidate_actions = list(self.BASE_ACTIONS)
        if food_at_pos:
            candidate_actions.append('eat')

        # Compute current action values from perception (read-only, no state change)
        vi = self._compute_impulsive_values(candidate_actions, x, y, visible_foods)
        vg = self._compute_goal_directed_values(candidate_actions, x, y, visible_foods)

        # Compute integrated values using current E and omega
        omega = self.E ** 2
        v = {a: omega * vg[a] + (1.0 - omega) * vi[a] for a in candidate_actions}

        # Detect conflict
        best_impulsive = self._argmax(vi)
        best_gd = self._argmax(vg)
        conflict = (best_impulsive != best_gd)

        # Check forced impulsive failure (P3): E below threshold during conflict
        if conflict and self.E < self.theta:
            chosen = best_impulsive
        elif random.random() < self.epsilon:
            chosen = random.choice(candidate_actions)
        else:
            chosen = self._argmax(v)

        # Cache perception info for update()
        self._last_action_name = chosen
        self._last_position = (x, y)
        self._last_food_config_key = self._make_state_key(x, y, visible_foods)
        self._last_candidate_actions = candidate_actions
        self._last_vi = vi
        self._last_vg = vg
        self._last_v = v
        self._last_conflict = conflict

        return Action(name=chosen)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """
        Apply ALL rules and state updates:
          - R7: habit TD update if we ate successfully
          - R6: ctrl flag from conflict detection
          - R1: executive capacity ODE step
          - R4: omega = E^2
          - R2, R3, R5: recompute value dicts for new perception (for get_state)
        """
        new_x = new_perception.get('x', 0)
        new_y = new_perception.get('y', 0)
        new_foods = new_perception.get('resources', {}).get('food', [])
        last_result = new_perception.get('last_action_result', {})

        # R7: Habit TD update
        if action.name == 'eat':
            consumed = last_result.get('consumed', False)
            if consumed:
                # Find palatability of what was eaten
                eaten_pal = last_result.get('palatability', None)
                if eaten_pal is None:
                    # Infer from foods at last position
                    if self._last_position is not None:
                        lx, ly = self._last_position
                        old_foods = new_perception.get('resources', {}).get('food', [])
                        # Use new_perception foods as fallback, or last known
                        eaten_pal = reward  # use reward as taste proxy if unknown
                if eaten_pal is None:
                    eaten_pal = reward

                state_key = self._last_food_config_key
                if state_key is not None:
                    q_key = (state_key, 'eat')
                    old_q = self.Q_habit[q_key]
                    # TD update: Q += alpha_Q * (taste_reward - Q)
                    self.Q_habit[q_key] = old_q + self.alpha_Q * (eaten_pal - old_q)

        # R6: control exertion flag from conflict detection cached in decide()
        if hasattr(self, '_last_conflict'):
            self.ctrl = 1 if self._last_conflict else 0
        else:
            self.ctrl = 0

        # R1: Euler-discretized ODE for executive capacity
        E_new = self.E + self.beta_E * (1.0 - self.E) - self.alpha_E * self.ctrl
        self.E = max(0.0, min(1.0, E_new))

        # R4: arbitration weight
        self.omega = self.E ** 2

        # Recompute value dicts for the new perception state
        new_food_at_pos = [
            f for f in new_foods
            if f.get('x', -1) == new_x and f.get('y', -1) == new_y
        ]
        new_candidates = list(self.BASE_ACTIONS)
        if new_food_at_pos:
            new_candidates.append('eat')

        new_vi = self._compute_impulsive_values(new_candidates, new_x, new_y, new_foods)
        new_vg = self._compute_goal_directed_values(new_candidates, new_x, new_y, new_foods)
        new_v = {
            a: self.omega * new_vg[a] + (1.0 - self.omega) * new_vi[a]
            for a in new_candidates
        }

        # Update scalar summaries for the action taken
        self.V_I = new_vi.get(action.name, 0.0)
        self.V_G = new_vg.get(action.name, 0.0)
        self.V = new_v.get(action.name, 0.0)

        # Update full value dicts (fill missing actions with 0)
        for a in self.ALL_ACTIONS:
            self._vi_dict[a] = new_vi.get(a, 0.0)
            self._vg_dict[a] = new_vg.get(a, 0.0)
            self._v_dict[a] = new_v.get(a, 0.0)

    def get_state(self) -> dict:
        """Return full state snapshot including q_values for simulation infra."""
        return {
            'E': self.E,
            'V_I': self.V_I,
            'V_G': self.V_G,
            'V': self.V,
            'omega': self.omega,
            'ctrl': self.ctrl,
            'alpha_E': self.alpha_E,
            'beta_E': self.beta_E,
            'theta': self.theta,
            'epsilon': self.epsilon,
            'alpha_Q': self.alpha_Q,
            'gamma': self.gamma,
            'w_h_G': self.w_h_G,
            'w_tau_G': self.w_tau_G,
            'Q_habit_size': len(self.Q_habit),
            # q_values: integrated value per action (simulation visualization)
            'q_values': dict(self._v_dict),
        }
