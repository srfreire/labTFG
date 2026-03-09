from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Action(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    STAY = "stay"


@dataclass(frozen=True)
class Perception:
    position: tuple[int, int]
    grid_size: tuple[int, int]
    food_sources: list[dict] = field(default_factory=list)
    ate_food: bool = False
    step: int = 0


@runtime_checkable
class DecisionModel(Protocol):
    def decide(self, perception: Perception) -> Action: ...
    def update(self, action: Action, reward: float, new_perception: Perception) -> None: ...
    def get_state(self) -> dict: ...
