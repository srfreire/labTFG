"""Environment base — generic simulation framework for decision-making paradigms.

This module defines the core abstractions for running simulations:
- Generic types (Position, Action, Event, Resource)
- DecisionModel Protocol (the contract Phase 1 models implement)
- Agent wrapper (position + model + alive)
- Environment (grid 2D + simulation loop)
- ModelAdapter (translates Phase 1 concrete types to generic types)

The Environment is pure Python — no LLM, no Agent SDK dependency.
Phase 1 imports only happen inside ModelAdapter methods (lazy),
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


# --- Effect types ---

@dataclass
class MoveEffect:
    dx: int
    dy: int
    reward: float = 0.0

@dataclass
class ConsumeEffect:
    resource_type: str
    reward: float

@dataclass
class NoopEffect:
    reward: float = 0.0

Effect = MoveEffect | ConsumeEffect | NoopEffect

# --- Configuration ---

@dataclass
class ActionRule:
    name: str
    effect: Effect

@dataclass
class ResourceRule:
    type: str
    properties: dict = field(default_factory=dict)
    count: int = 0
    regenerate: bool = True


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


# --- Environment ---

class Environment:
    def __init__(
        self,
        width: int,
        height: int,
        actions: list[ActionRule],
        resources: list[ResourceRule],
        seed: int | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self._action_registry: dict[str, ActionRule] = {a.name: a for a in actions}
        self._resource_rules: dict[str, ResourceRule] = {r.type: r for r in resources}
        self._rng = random.Random(seed)
        self._agents: list[Agent] = []
        self._resources: list[Resource] = []
        self._step: int = 0
        self._events: list[Event] = []
        self._resource_counter: int = 0
        self._spawn_initial_resources()

    def _spawn_initial_resources(self) -> None:
        for rule in self._resource_rules.values():
            for _ in range(rule.count):
                self._spawn_resource(rule)

    def _spawn_resource(self, rule: ResourceRule) -> None:
        self._resource_counter += 1
        properties: dict = {"type": rule.type}
        for key, value in rule.properties.items():
            if isinstance(value, tuple) and len(value) == 2:
                properties[key] = self._rng.uniform(value[0], value[1])
            else:
                properties[key] = value
        self._resources.append(Resource(
            id=f"{rule.type}_{self._resource_counter}",
            position=Position(self._rng.randint(0, self.width - 1), self._rng.randint(0, self.height - 1)),
            properties=properties,
        ))

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
            "step": self._step,
            "resources": {
                rtype: [
                    {"x": r.position.x, "y": r.position.y, **r.properties}
                    for r in self._resources
                    if r.properties.get("type") == rtype
                ]
                for rtype in self._resource_rules
            },
            "last_action_result": {},
        }

    def _apply_action(self, agent: Agent, action: Action) -> tuple[float, dict]:
        rule = self._action_registry.get(action.name)
        if rule is None:
            return 0.0, {"error": "unknown_action"}
        effect = rule.effect
        if isinstance(effect, MoveEffect):
            return self._apply_move(agent, effect)
        elif isinstance(effect, ConsumeEffect):
            return self._apply_consume(agent, effect)
        elif isinstance(effect, NoopEffect):
            return effect.reward, {}
        else:
            return 0.0, {"error": f"unhandled_effect: {type(effect).__name__}"}

    def _apply_move(self, agent: Agent, effect: MoveEffect) -> tuple[float, dict]:
        agent.position.x = max(0, min(self.width - 1, agent.position.x + effect.dx))
        agent.position.y = max(0, min(self.height - 1, agent.position.y + effect.dy))
        return effect.reward, {}

    def _apply_consume(self, agent: Agent, effect: ConsumeEffect) -> tuple[float, dict]:
        idx = next(
            (i for i, r in enumerate(self._resources)
             if r.properties.get("type") == effect.resource_type
             and r.position.x == agent.position.x
             and r.position.y == agent.position.y),
            None,
        )
        if idx is None:
            return 0.0, {"consumed": False}
        self._resources.pop(idx)
        rule = self._resource_rules.get(effect.resource_type)
        if rule and rule.regenerate:
            self._spawn_resource(rule)
        return effect.reward, {"consumed": True, "resource_type": effect.resource_type}

    def step(self) -> list[Event]:
        step_events: list[Event] = []
        for agent in self._agents:
            if not agent.alive or agent.decision_model is None:
                continue
            perception = self._build_perception(agent)
            action = agent.decision_model.decide(perception)
            reward, action_result = self._apply_action(agent, action)
            new_perception = self._build_perception(agent)
            new_perception["last_action_result"] = action_result
            agent.decision_model.update(action, reward, new_perception)
            snapshot = {
                k: v.tolist() if hasattr(v, "tolist") else v
                for k, v in agent.decision_model.get_state().items()
            }
            event = Event(
                step=self._step, agent_id=agent.id, action=action,
                outcome={"action_result": action_result, "reward": reward, "model_state": snapshot},
            )
            step_events.append(event)
            self._events.append(event)
        self._step += 1
        return step_events

    def get_spec(self) -> dict:
        return {
            "available_actions": list(self._action_registry.keys()),
            "resource_types": {
                rtype: {"properties": rule.properties, "count": rule.count, "regenerate": rule.regenerate}
                for rtype, rule in self._resource_rules.items()
            },
            "grid": {"width": self.width, "height": self.height},
        }

    def run(self, steps: int) -> list[Event]:
        all_events: list[Event] = []
        for _ in range(steps):
            if self.is_finished():
                break
            all_events.extend(self.step())
        return all_events


# --- Adapter for Phase 1 (Denis) models ---

class ModelAdapter:
    """Translates between Phase 1 concrete types and Phase 2 generic types.

    Phase 1 imports are lazy (inside methods) so this module works
    without Phase 1 installed — only adapter calls require it.
    """

    def __init__(self, phase1_model) -> None:
        self._model = phase1_model

    def _to_typed_perception(self, perception: dict):
        from decisionlab.models.protocol import Perception as P1Perception
        # Support both new grouped format (resources dict) and legacy flat list (nearby_resources)
        resources_dict = perception.get("resources", {})
        food_list = resources_dict.get("food", []) if isinstance(resources_dict, dict) else []
        nearby = perception.get("nearby_resources", food_list)
        action_result = perception.get("last_action_result", {})
        ate_food = perception.get("ate_food", action_result.get("consumed", False))
        return P1Perception(
            position=(perception["x"], perception["y"]),
            grid_size=(perception["grid_width"], perception["grid_height"]),
            food_sources=tuple(nearby),
            ate_food=ate_food,
            step=perception.get("step", 0),
        )

    def decide(self, perception: dict) -> Action:
        p1_perception = self._to_typed_perception(perception)
        p1_action = self._model.decide(p1_perception)
        return Action(name=p1_action.name, params=p1_action.params)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        from decisionlab.models.protocol import Action as P1Action
        p1_action = P1Action(action.name, action.params)
        p1_perception = self._to_typed_perception(new_perception)
        self._model.update(p1_action, reward, p1_perception)

    def get_state(self) -> dict:
        return self._model.get_state()
