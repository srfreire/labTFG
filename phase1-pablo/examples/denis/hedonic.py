"""Hedonic model — Q-Learning from Denis TFM (section 2.3).

Agent learns to maximize reward via Q-table updates.
Produces a hedonic signal W(t) = max_a Q(state, a).

References:
    - Watkins & Dayan (1992) — Q-Learning
    - Denis Yamunaque TFM (2025) — Section 2.3
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from decisionlab.models.protocol import Action, Perception

_ACTIONS = list(Action)
_ACTION_TO_IDX = {a: i for i, a in enumerate(_ACTIONS)}

_DELTAS: dict[Action, tuple[int, int]] = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
    Action.STAY: (0, 0),
}


@dataclass
class HedonicParams:
    grid_size: tuple[int, int] = (5, 5)
    learning_rate: float = 0.1       # alpha
    discount_factor: float = 0.9     # gamma
    epsilon: float = 1.0
    epsilon_decay: float = 0.9995
    epsilon_min: float = 0.01
    n_palatability_levels: int = 2   # discretized
    use_food_in_state: bool = True


@dataclass
class HedonicModel:
    params: HedonicParams = field(default_factory=HedonicParams)

    # Mutable state
    q_table: np.ndarray = field(init=False)
    epsilon: float = field(init=False)
    _last_state_idx: int | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.epsilon = self.params.epsilon
        gw, gh = self.params.grid_size
        n_pal = self.params.n_palatability_levels if self.params.use_food_in_state else 1
        food_flag = 2 if self.params.use_food_in_state else 1  # food present/absent
        n_states = gw * gh * food_flag * n_pal
        n_actions = len(_ACTIONS)
        self.q_table = np.zeros((n_states, n_actions), dtype=np.float64)

    def _state_index(self, position: tuple[int, int], food_sources: list[dict] | None = None) -> int:
        gw, gh = self.params.grid_size
        x, y = position

        if self.params.use_food_in_state and food_sources:
            food_here = any(f["x"] == x and f["y"] == y for f in food_sources)
            food_flag = 1 if food_here else 0
            pals = [f["palatability"] for f in food_sources if f["x"] == x and f["y"] == y]
            pal_level = min(int(max(pals) * self.params.n_palatability_levels), self.params.n_palatability_levels - 1) if pals else 0
            n_pal = self.params.n_palatability_levels
            return ((x * gh + y) * 2 + food_flag) * n_pal + pal_level
        else:
            return x * gh + y

    def _reverse_position(self, action: Action, new_position: tuple[int, int]) -> tuple[int, int]:
        """Infer previous position by reversing the action delta."""
        dx, dy = _DELTAS[action]
        return (new_position[0] - dx, new_position[1] - dy)

    def decide(self, perception: Perception) -> Action:
        state_idx = self._state_index(perception.position, perception.food_sources)
        self._last_state_idx = state_idx

        if random.random() < self.epsilon:
            return random.choice(_ACTIONS)
        else:
            best_idx = int(np.argmax(self.q_table[state_idx]))
            return _ACTIONS[best_idx]

    def update(self, action: Action, reward: float, new_perception: Perception) -> None:
        if self._last_state_idx is None:
            # Infer previous state from action and new position
            prev_pos = self._reverse_position(action, new_perception.position)
            gw, gh = self.params.grid_size
            prev_pos = (
                max(0, min(gw - 1, prev_pos[0])),
                max(0, min(gh - 1, prev_pos[1])),
            )
            self._last_state_idx = self._state_index(prev_pos)

        action_idx = _ACTION_TO_IDX[action]
        new_state_idx = self._state_index(new_perception.position, new_perception.food_sources)

        # Q(s,a) <- Q(s,a) + alpha * [R + gamma * max_a' Q(s',a') - Q(s,a)]
        old_q = self.q_table[self._last_state_idx, action_idx]
        max_future_q = np.max(self.q_table[new_state_idx])
        td_target = reward + self.params.discount_factor * max_future_q
        self.q_table[self._last_state_idx, action_idx] = old_q + self.params.learning_rate * (td_target - old_q)

        # Decay epsilon
        self.epsilon = max(self.params.epsilon_min, self.epsilon * self.params.epsilon_decay)

    def hedonic_signal(self, position: tuple[int, int], food_sources: list[dict] | None = None) -> float:
        """W(t) = max_a Q(state, a) for current position."""
        state_idx = self._state_index(position, food_sources)
        return float(np.max(self.q_table[state_idx]))

    def train(self, grid: "GridWorld", episodes: int = 100, steps_per_episode: int = 50) -> None:
        """Train the Q-table on a grid environment."""
        for _ in range(episodes):
            grid.reset()
            for step in range(steps_per_episode):
                perception = grid.get_perception(step=step)
                action = self.decide(perception)
                grid.apply_action(action)
                new_perception = grid.get_perception(step=step + 1)
                reward = 1.0 if new_perception.ate_food else -0.01
                self.update(action, reward, new_perception)

    def get_state(self) -> dict:
        return {
            "q_table": self.q_table.copy(),
            "epsilon": self.epsilon,
        }
