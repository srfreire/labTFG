"""
Executive Resource ODE with Dual-Value Arbitration Model

Implements a continuous-time ODE governing depletable executive (dlPFC) resource
dynamics, combined with a dual-system architecture where an impulsive controller
(taste-driven) competes with a goal-directed controller (health-integrated).
An arbitration weight derived from executive capacity determines the mixture.

Based on Rangel et al. (2008) and Rangel (2013).
"""

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
        self.E: float = 1.0
        self.V_I: float = 0.0
        self.V_G: float = 0.0
        self.V: float = 0.0
        self.omega: float = 1.0
        self.ctrl: int = 0

        # Habit Q-values: (state_hash, action_name) -> float
        self.Q_habit: dict = defaultdict(float)

        # Cached state for update() — set by decide(), never mutating E/ctrl
        self._last_action_name: str = None
        self._last_position: tuple = None
        self._last_food_config_key: tuple = None
        self._last_candidate_actions: list = list(self.BASE_ACTIONS)
        self._last_vi: dict = {a: 0.0 for a in self.ALL_ACTIONS}
        self._last_vg: dict = {a: 0.0 for a in self.ALL_ACTIONS}
        self._last_v: dict = {a: 0.0 for a in self.ALL_ACTIONS}
        self._last_conflict: bool = False

        # Per-action value caches for get_state() / q_values
        self._v_dict: dict = {a: 0.0 for a in self.ALL_ACTIONS}

        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
        return abs(x1 - x2) + abs(y1 - y2)

    @staticmethod
    def _next_position(action_name: str, x: int, y: int) -> tuple:
        if action_name == 'move_up':
            return (x, y - 1)
        elif action_name == 'move_down':
            return (x, y + 1)
        elif action_name == 'move_left':
            return (x - 1, y)
        elif action_name == 'move_right':
            return (x + 1, y)
        else:  # stay, eat
            return (x, y)

    def _compute_impulsive_values(
        self,
        candidate_actions: list,
        x: int,
        y: int,
        visible_foods: list,
        eat_in_candidates: bool,
    ) -> dict:
        """
        R2: V_I[a] = palatability * gamma^distance (taste-driven).

        Key design decisions:
        - 'eat':  V_I = max palatability of foods at current position (dist=0).
        - 'stay': V_I = 0 when 'eat' is also available (eating is the explicit
                  consumption action; staying without eating has no taste value).
                  If 'eat' is NOT in candidates (no food here), 'stay' gets 0 too.
        - movement: V_I = best palatability * gamma^dist to any food after step.
        - Blended with habit Q-value: V_I[a] = max(computed, Q_habit[s,a]).
        """
        vi = {}
        state_key = self._make_state_key(x, y, visible_foods)

        for action in candidate_actions:
            nx, ny = self._next_position(action, x, y)

            if action == 'eat':
                # dist = 0, gamma^0 = 1 → pure palatability
                foods_here = [
                    f for f in visible_foods
                    if f.get('x', -1) == x and f.get('y', -1) == y
                ]
                base_val = (
                    max(f.get('palatability', 0.0) for f in foods_here)
                    if foods_here else 0.0
                )

            elif action == 'stay':
                # 'stay' has no consumption value; defer to 'eat' when available
                base_val = 0.0

            else:
                # Movement: find best food reachable from the next cell
                if not visible_foods:
                    base_val = 0.0
                else:
                    best = 0.0
                    for f in visible_foods:
                        dist = self._manhattan_distance(nx, ny, f.get('x', 0), f.get('y', 0))
                        score = f.get('palatability', 0.0) * (self.gamma ** dist)
                        if score > best:
                            best = score
                    base_val = best

            # Blend with cached habit Q-value (R2)
            habit_val = self.Q_habit.get((state_key, action), 0.0)
            vi[action] = max(base_val, habit_val)

        return vi

    def _compute_goal_directed_values(
        self,
        candidate_actions: list,
        x: int,
        y: int,
        visible_foods: list,
    ) -> dict:
        """
        R3: V_G[a] = (w_tau_G * taste + w_h_G * health) * gamma^dist.
        health = 1 - palatability.

        Same stay/eat logic as impulsive: 'stay' has V_G=0 when 'eat' is available.
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
                    best = max(
                        self.w_tau_G * f.get('palatability', 0.0)
                        + self.w_h_G * (1.0 - f.get('palatability', 0.0))
                        for f in foods_here
                    )
                    vg[action] = best
                else:
                    vg[action] = 0.0

            elif action == 'stay':
                # No nutritional benefit from merely staying (eating is explicit)
                vg[action] = 0.0

            else:
                if not visible_foods:
                    vg[action] = 0.0
                else:
                    best = 0.0
                    for f in visible_foods:
                        dist = self._manhattan_distance(
                            nx, ny, f.get('x', 0), f.get('y', 0)
                        )
                        taste = f.get('palatability', 0.0)
                        health = 1.0 - taste
                        composite = self.w_tau_G * taste + self.w_h_G * health
                        score = composite * (self.gamma ** dist)
                        if score > best:
                            best = score
                    vg[action] = best

        return vg

    @staticmethod
    def _argmax(value_dict: dict) -> str:
        """Return action key with highest value (stable: first max wins)."""
        return max(value_dict, key=lambda k: value_dict[k])

    @staticmethod
    def _make_state_key(x: int, y: int, visible_foods: list) -> tuple:
        """Discretize state for habit Q-table."""
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
        READ-ONLY action selection.
        Reads current E/omega to compute integrated values, then picks an action.
        Does NOT mutate E, ctrl, omega, V_I, V_G, or V.
        """
        x = perception.get('x', 0)
        y = perception.get('y', 0)
        visible_foods = perception.get('resources', {}).get('food', [])

        # Build candidate actions
        food_at_pos = [
            f for f in visible_foods
            if f.get('x', -1) == x and f.get('y', -1) == y
        ]
        eat_available = len(food_at_pos) > 0
        candidate_actions = list(self.BASE_ACTIONS)
        if eat_available:
            candidate_actions.append('eat')

        # R2: impulsive values
        vi = self._compute_impulsive_values(
            candidate_actions, x, y, visible_foods, eat_available
        )
        # R3: goal-directed values
        vg = self._compute_goal_directed_values(
            candidate_actions, x, y, visible_foods
        )

        # R4 (read-only): current omega from current E
        omega_now = self.E ** 2

        # R5: integrated values
        v = {a: omega_now * vg[a] + (1.0 - omega_now) * vi[a] for a in candidate_actions}

        # R6: conflict detection
        best_impulsive = self._argmax(vi)
        best_gd = self._argmax(vg)
        conflict = (best_impulsive != best_gd)

        # Action selection: P3 forced failure, epsilon-greedy, or greedy
        if conflict and self.E < self.theta:
            # Complete self-control failure: forced to impulsive system
            chosen = best_impulsive
        elif random.random() < self.epsilon:
            chosen = random.choice(candidate_actions)
        else:
            chosen = self._argmax(v)

        # Cache for update() — these are private tracking attributes, not state vars
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
        Apply all rules and mutate state variables.

        R7 → habit TD update (eat success)
        R6 → ctrl flag
        R1 → executive capacity ODE step
        R4 → omega = E^2
        R2/R3/R5 → recompute value dicts for new perception (q_values)
        """
        new_x = new_perception.get('x', 0)
        new_y = new_perception.get('y', 0)
        new_foods = new_perception.get('resources', {}).get('food', [])
        last_result = new_perception.get('last_action_result', {})

        # R7: Habit TD update on successful eat
        if action.name == 'eat':
            consumed = last_result.get('consumed', False)
            if consumed:
                eaten_pal = last_result.get('palatability', None)
                if eaten_pal is None:
                    eaten_pal = reward
                state_key = self._last_food_config_key
                if state_key is not None:
                    q_key = (state_key, 'eat')
                    old_q = self.Q_habit[q_key]
                    self.Q_habit[q_key] = old_q + self.alpha_Q * (eaten_pal - old_q)

        # R6: set ctrl from conflict detected in last decide()
        self.ctrl = 1 if self._last_conflict else 0

        # R1: Euler-discretized ODE
        # dE/dt = beta_E*(1 - E) - alpha_E*ctrl
        E_new = self.E + self.beta_E * (1.0 - self.E) - self.alpha_E * self.ctrl
        self.E = max(0.0, min(1.0, E_new))

        # R4: arbitration weight
        self.omega = self.E ** 2

        # Recompute value dicts for new perception (for get_state / q_values)
        new_food_at_pos = [
            f for f in new_foods
            if f.get('x', -1) == new_x and f.get('y', -1) == new_y
        ]
        new_eat_available = len(new_food_at_pos) > 0
        new_candidates = list(self.BASE_ACTIONS)
        if new_eat_available:
            new_candidates.append('eat')

        new_vi = self._compute_impulsive_values(
            new_candidates, new_x, new_y, new_foods, new_eat_available
        )
        new_vg = self._compute_goal_directed_values(
            new_candidates, new_x, new_y, new_foods
        )
        new_v = {
            a: self.omega * new_vg[a] + (1.0 - self.omega) * new_vi[a]
            for a in new_candidates
        }

        # Update scalar summaries for the action taken
        self.V_I = new_vi.get(action.name, 0.0)
        self.V_G = new_vg.get(action.name, 0.0)
        self.V = new_v.get(action.name, 0.0)

        # Update q_values cache (fill missing actions with 0.0)
        for a in self.ALL_ACTIONS:
            self._v_dict[a] = float(new_v.get(a, 0.0))

    def get_state(self) -> dict:
        """Return full state snapshot; q_values required by simulation infra."""
        return {
            # State variables
            'E': self.E,
            'V_I': self.V_I,
            'V_G': self.V_G,
            'V': self.V,
            'omega': self.omega,
            'ctrl': self.ctrl,
            # Parameters
            'alpha_E': self.alpha_E,
            'beta_E': self.beta_E,
            'theta': self.theta,
            'epsilon': self.epsilon,
            'alpha_Q': self.alpha_Q,
            'gamma': self.gamma,
            'w_h_G': self.w_h_G,
            'w_tau_G': self.w_tau_G,
            'Q_habit_size': len(self.Q_habit),
            # q_values: integrated value per action (required by simulation infra)
            'q_values': {a: self._v_dict[a] for a in self.ALL_ACTIONS},
        }
