from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


# Convenience constants
UP = Action("up")
DOWN = Action("down")
LEFT = Action("left")
RIGHT = Action("right")
STAY = Action("stay")


@dataclass(frozen=True)
class Perception:
    position: tuple[int, int]
    grid_size: tuple[int, int]
    food_sources: tuple[dict, ...] = ()
    ate_food: bool = False
    step: int = 0


@runtime_checkable
class DecisionModel(Protocol):
    def decide(self, perception: Perception) -> Action: ...
    def update(
        self, action: Action, reward: float, new_perception: Perception
    ) -> None: ...
    def get_state(self) -> dict: ...
