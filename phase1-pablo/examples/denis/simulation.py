"""Simulation runner — perceive/decide/act/update loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from decisionlab.models.protocol import DecisionModel
from denis.grid import GridWorld


@dataclass
class SimulationResult:
    history: list[dict] = field(default_factory=list)
    total_food_eaten: int = 0


@dataclass
class Simulation:
    grid: GridWorld
    model: DecisionModel

    def run(self, steps: int, agent_start: tuple[int, int] | None = None) -> SimulationResult:
        if agent_start:
            self.grid.place_agent(*agent_start)
        else:
            self.grid.reset()

        result = SimulationResult()

        for step in range(steps):
            # 1. Perceive
            perception = self.grid.get_perception(step=step)

            # 2. Decide
            action = self.model.decide(perception)

            # 3. Act
            self.grid.apply_action(action)

            # 4. Observe result
            new_perception = self.grid.get_perception(step=step)
            ate = new_perception.ate_food
            reward = 1.0 if ate else -0.01

            # 5. Update model
            self.model.update(action, reward, new_perception)

            # 6. Record
            model_state = self.model.get_state()
            result.history.append({
                "step": step,
                "position": new_perception.position,
                "action": action.value,
                "ate_food": ate,
                "hunger": model_state.get("homeostatic", {}).get("hunger", 0),
                "hedonic_signal": model_state.get("hedonic_signal", 0),
                "reward": reward,
            })
            if ate:
                result.total_food_eaten += 1

        return result
