"""Grid world environment — adapted from Denis's script.

A 2D grid where an agent moves to find and consume food sources.
Food sources have palatability values and can regenerate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from decisionlab.models.protocol import Action, Perception

_DELTAS: dict[Action, tuple[int, int]] = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
    Action.STAY: (0, 0),
}


@dataclass
class GridConfig:
    width: int = 5
    height: int = 5
    food_count: int = 3
    food_palatability_range: tuple[float, float] = (0.1, 1.0)
    food_regenerate: bool = True
    seed: int | None = None


@dataclass
class GridWorld:
    config: GridConfig
    food_sources: list[dict] = field(init=False, default_factory=list)
    agent_position: tuple[int, int] = field(init=False, default=(0, 0))
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.seed)
        self._spawn_food(self.config.food_count)

    @property
    def width(self) -> int:
        return self.config.width

    @property
    def height(self) -> int:
        return self.config.height

    def _spawn_food(self, count: int) -> None:
        lo, hi = self.config.food_palatability_range
        for _ in range(count):
            self.food_sources.append({
                "x": self._rng.randint(0, self.width - 1),
                "y": self._rng.randint(0, self.height - 1),
                "palatability": self._rng.uniform(lo, hi),
            })

    def place_agent(self, x: int, y: int) -> None:
        self.agent_position = (x, y)

    def apply_action(self, action: Action) -> None:
        dx, dy = _DELTAS[action]
        nx = max(0, min(self.width - 1, self.agent_position[0] + dx))
        ny = max(0, min(self.height - 1, self.agent_position[1] + dy))
        self.agent_position = (nx, ny)

    def get_perception(self, step: int) -> Perception:
        ax, ay = self.agent_position

        ate = False
        eaten_idx = None
        for i, f in enumerate(self.food_sources):
            if f["x"] == ax and f["y"] == ay:
                ate = True
                eaten_idx = i
                break

        if eaten_idx is not None:
            self.food_sources.pop(eaten_idx)
            if self.config.food_regenerate:
                self._spawn_food(1)

        return Perception(
            position=self.agent_position,
            grid_size=(self.width, self.height),
            food_sources=list(self.food_sources),
            ate_food=ate,
            step=step,
        )

    def reset(self, agent_x: int | None = None, agent_y: int | None = None) -> None:
        self.food_sources.clear()
        self._spawn_food(self.config.food_count)
        x = agent_x if agent_x is not None else self._rng.randint(0, self.width - 1)
        y = agent_y if agent_y is not None else self._rng.randint(0, self.height - 1)
        self.place_agent(x, y)
