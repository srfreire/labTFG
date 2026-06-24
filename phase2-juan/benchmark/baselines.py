"""Reference baseline decision models for the golden-scenario benchmark.

These are *known-truth* anchors, not Phase 1 artefacts:

- ``GreedyForagerOracle``  — always walks to the nearest food and eats it.
  Defines the upper bound (ceiling) of foraging efficiency on a given grid.
- ``RandomModel``          — picks a uniformly random action every step.
  Defines the lower bound (floor); any competent forager must beat it.

Both honour the shared ``DecisionModel`` contract by duck typing:
``decide`` is read-only, ``update`` is the only mutator, and ``get_state``
exposes a ``q_values`` key so the lab's observation layer can render them like
any Phase 1 model. They are instantiated directly by the benchmark harness
(not through the Phase 1 loader), so they take an explicit ``seed`` for
reproducibility instead of relying on the loader's seeded RNG.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

ACTIONS = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

# Movement deltas. Grid convention matches the environment: y grows downward,
# so ``move_up`` decreases y and ``move_down`` increases it.
_DELTAS: dict[str, tuple[int, int]] = {
    "move_up": (0, -1),
    "move_down": (0, 1),
    "move_left": (-1, 0),
    "move_right": (1, 0),
    "stay": (0, 0),
    "eat": (0, 0),
}


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


def _food(perception: dict) -> list[dict]:
    return perception.get("resources", {}).get("food", [])


def _manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


class GreedyForagerOracle:
    """Optimal-ish forager: step greedily toward the nearest food and eat it.

    This is the performance *ceiling*. It is deliberately simple and
    deterministic (ties broken by a fixed action order), so its trajectory is
    reproducible and its food-collection rate is the practical maximum a
    well-behaved model can approach on the same grid.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.food_eaten: int = 0
        self.steps: int = 0
        self.q_values: dict[str, float] = {a: 0.0 for a in ACTIONS}

    def decide(self, perception: dict) -> Action:
        """READ-ONLY: choose the action that most reduces distance to food."""
        x, y = perception["x"], perception["y"]
        gw, gh = perception["grid_width"], perception["grid_height"]
        food = _food(perception)
        if not food:
            return Action("stay")

        nearest = min(food, key=lambda f: _manhattan(x, y, f["x"], f["y"]))
        if nearest["x"] == x and nearest["y"] == y:
            return Action("eat")

        # Pick the legal move that minimises Manhattan distance to the target.
        best_name, best_dist = "stay", _manhattan(x, y, nearest["x"], nearest["y"])
        for name in ("move_up", "move_down", "move_left", "move_right"):
            dx, dy = _DELTAS[name]
            nx, ny = x + dx, y + dy
            if 0 <= nx < gw and 0 <= ny < gh:
                d = _manhattan(nx, ny, nearest["x"], nearest["y"])
                if d < best_dist:
                    best_name, best_dist = name, d
        return Action(best_name)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        """Only mutator: track foraging counters and refresh action scores."""
        self.steps += 1
        if action.name == "eat" and reward > 0:
            self.food_eaten += 1

        x, y = new_perception["x"], new_perception["y"]
        gw, gh = new_perception["grid_width"], new_perception["grid_height"]
        food = _food(new_perception)
        scores = {a: 0.0 for a in ACTIONS}
        if food:
            nearest = min(food, key=lambda f: _manhattan(x, y, f["x"], f["y"]))
            scores["eat"] = 1.0 if (nearest["x"] == x and nearest["y"] == y) else 0.0
            for name in ("move_up", "move_down", "move_left", "move_right"):
                dx, dy = _DELTAS[name]
                nx, ny = x + dx, y + dy
                if 0 <= nx < gw and 0 <= ny < gh:
                    # Higher score = closer to food.
                    scores[name] = -float(
                        _manhattan(nx, ny, nearest["x"], nearest["y"])
                    )
                else:
                    scores[name] = float("-inf")
        self.q_values = scores

    def get_state(self) -> dict:
        return {
            "food_eaten": self.food_eaten,
            "steps": self.steps,
            "foraging_rate": self.food_eaten / self.steps if self.steps else 0.0,
            "q_values": dict(self.q_values),
        }


class RandomModel:
    """Uniformly random agent — the performance *floor*.

    Any model that genuinely forages, regulates, or learns must beat this
    baseline; if it does not, the observed behaviour is indistinguishable from
    chance and the golden scenario has failed to detect a real pattern.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.food_eaten: int = 0
        self.steps: int = 0
        self.q_values: dict[str, float] = {a: 0.0 for a in ACTIONS}

    def decide(self, perception: dict) -> Action:
        """READ-ONLY: pick a uniformly random action."""
        return Action(self._rng.choice(ACTIONS))

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        self.steps += 1
        if action.name == "eat" and reward > 0:
            self.food_eaten += 1
        # Flat scores: the random policy has no preference over actions.
        self.q_values = {a: 0.0 for a in ACTIONS}

    def get_state(self) -> dict:
        return {
            "food_eaten": self.food_eaten,
            "steps": self.steps,
            "foraging_rate": self.food_eaten / self.steps if self.steps else 0.0,
            "q_values": dict(self.q_values),
        }
