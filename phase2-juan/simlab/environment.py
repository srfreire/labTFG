"""Environment base — generic simulation framework for decision-making paradigms.

This module defines the core abstractions for running simulations:
- Generic types (Position, Action, Event, Resource)
- DecisionModel Protocol (the contract Phase 1 models implement)
- Agent wrapper (position + model + alive)
- Environment (grid 2D + simulation loop)
- DenisModelAdapter (translates Phase 1 concrete types to generic types)

The Environment is pure Python — no LLM, no Agent SDK dependency.
Phase 1 imports only happen inside DenisModelAdapter methods (lazy),
so this module works without Phase 1 installed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# --- Basic types ---

@dataclass
class Position:
    x: int
    y: int


@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)


@dataclass
class Event:
    step: int
    agent_id: str
    action: Action
    outcome: dict = field(default_factory=dict)


@dataclass
class Resource:
    id: str
    position: Position
    properties: dict = field(default_factory=dict)


# --- Protocol for decision paradigms (Phase 1 implements this) ---

@runtime_checkable
class DecisionModel(Protocol):
    def decide(self, perception: dict) -> Action: ...
    def update(self, action: Action, reward: float, new_perception: dict) -> None: ...
    def get_state(self) -> dict: ...


# --- Agent (minimal wrapper) ---

@dataclass
class Agent:
    id: str
    position: Position
    decision_model: DecisionModel | None = None
    alive: bool = True


# --- Movement deltas ---

_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "stay": (0, 0),
}


# --- Environment ---

class Environment:
    def __init__(
        self,
        width: int,
        height: int,
        seed: int | None = None,
        food_regenerate: bool = True,
        food_palatability_range: tuple[float, float] = (0.1, 1.0),
    ) -> None:
        self.width = width
        self.height = height
        self.food_regenerate = food_regenerate
        self.food_palatability_range = food_palatability_range
        self._rng = random.Random(seed)
        self._agents: list[Agent] = []
        self._resources: list[Resource] = []
        self._step: int = 0
        self._events: list[Event] = []
        self._resource_counter: int = 0

    def add_agent(self, agent: Agent) -> None:
        self._agents.append(agent)

    def add_resource(self, resource: Resource) -> None:
        self._resources.append(resource)

    def is_finished(self) -> bool:
        return not any(a.alive for a in self._agents)

    def get_state(self) -> dict:
        return {
            "step": self._step,
            "agents": [
                {"id": a.id, "x": a.position.x, "y": a.position.y, "alive": a.alive}
                for a in self._agents
            ],
            "resources": [
                {"id": r.id, "x": r.position.x, "y": r.position.y, **r.properties}
                for r in self._resources
            ],
        }

    def _build_perception(self, agent: Agent) -> dict:
        return {
            "x": agent.position.x,
            "y": agent.position.y,
            "grid_width": self.width,
            "grid_height": self.height,
            "nearby_resources": [
                {"x": r.position.x, "y": r.position.y, **r.properties}
                for r in self._resources
            ],
            "ate_food": False,
            "step": self._step,
        }

    def _apply_action(self, agent: Agent, action: Action) -> tuple[float, dict]:
        dx, dy = _DELTAS.get(action.name, (0, 0))
        agent.position.x = max(0, min(self.width - 1, agent.position.x + dx))
        agent.position.y = max(0, min(self.height - 1, agent.position.y + dy))

        ate_food = False
        eaten_idx = None
        for i, r in enumerate(self._resources):
            if (
                r.properties.get("type") == "food"
                and r.position.x == agent.position.x
                and r.position.y == agent.position.y
            ):
                eaten_idx = i
                break

        if eaten_idx is not None:
            self._resources.pop(eaten_idx)
            ate_food = True
            if self.food_regenerate:
                lo, hi = self.food_palatability_range
                self._resource_counter += 1
                self._resources.append(Resource(
                    id=f"food_{self._resource_counter}",
                    position=Position(
                        self._rng.randint(0, self.width - 1),
                        self._rng.randint(0, self.height - 1),
                    ),
                    properties={"type": "food", "palatability": self._rng.uniform(lo, hi)},
                ))

        reward = 1.0 if ate_food else -0.01
        outcome = {"ate_food": ate_food}
        return reward, outcome

    def step(self) -> list[Event]:
        step_events: list[Event] = []
        for agent in self._agents:
            if not agent.alive or agent.decision_model is None:
                continue

            perception = self._build_perception(agent)
            action = agent.decision_model.decide(perception)
            reward, outcome = self._apply_action(agent, action)

            new_perception = self._build_perception(agent)
            new_perception["ate_food"] = outcome.get("ate_food", False)
            agent.decision_model.update(action, reward, new_perception)

            snapshot = agent.decision_model.get_state()
            snapshot = {
                k: v.tolist() if hasattr(v, "tolist") else v
                for k, v in snapshot.items()
            }

            event = Event(
                step=self._step,
                agent_id=agent.id,
                action=action,
                outcome={**outcome, "reward": reward, "model_state": snapshot},
            )
            step_events.append(event)
            self._events.append(event)

        self._step += 1
        return step_events

    def run(self, steps: int) -> list[Event]:
        all_events: list[Event] = []
        for _ in range(steps):
            if self.is_finished():
                break
            all_events.extend(self.step())
        return all_events


# --- Adapter for Phase 1 (Denis) models ---

class DenisModelAdapter:
    """Translates between Phase 1 concrete types and Phase 2 generic types.

    Phase 1 imports are lazy (inside methods) so this module works
    without Phase 1 installed — only adapter calls require it.
    """

    def __init__(self, phase1_model) -> None:
        self._model = phase1_model

    def _to_p1_perception(self, perception: dict):
        from decisionlab.models.protocol import Perception as P1Perception
        return P1Perception(
            position=(perception["x"], perception["y"]),
            grid_size=(perception["grid_width"], perception["grid_height"]),
            food_sources=tuple(perception.get("nearby_resources", [])),
            ate_food=perception.get("ate_food", False),
            step=perception.get("step", 0),
        )

    def decide(self, perception: dict) -> Action:
        p1_perception = self._to_p1_perception(perception)
        p1_action = self._model.decide(p1_perception)
        return Action(name=p1_action.name)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        from decisionlab.models.protocol import Action as P1Action
        p1_action = P1Action(action.name)
        p1_perception = self._to_p1_perception(new_perception)
        self._model.update(p1_action, reward, p1_perception)

    def get_state(self) -> dict:
        return self._model.get_state()
