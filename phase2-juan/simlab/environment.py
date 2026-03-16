"""
Environment — the simulation engine.

This module defines all the core types and the simulation loop:
  - Data types: Position, Action, Event, Resource
  - Effects: MoveEffect, ConsumeEffect, NoopEffect
  - Configuration: ActionRule, ResourceRule
  - DecisionModel protocol (the contract Phase 1 models implement)
  - Agent wrapper (position + model + alive)
  - Environment (2D grid + step-by-step simulation)

The Environment is pure Python — no LLM, no external dependencies.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Effect types — what happens when an action is executed
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Configuration — how the environment is set up
# ---------------------------------------------------------------------------

@dataclass
class ActionRule:
    """Maps an action name to its effect."""
    name: str
    effect: Effect

@dataclass
class ResourceRule:
    """Defines a type of resource and how it spawns."""
    type: str
    properties: dict = field(default_factory=dict)
    count: int = 0
    regenerate: bool = True


# ---------------------------------------------------------------------------
# DecisionModel protocol — Phase 1 models implement this interface
# ---------------------------------------------------------------------------

@runtime_checkable
class DecisionModel(Protocol):
    def decide(self, perception: dict) -> Action: ...
    def update(self, action: Action, reward: float, new_perception: dict) -> None: ...
    def get_state(self) -> dict: ...


# ---------------------------------------------------------------------------
# Agent — wraps a decision model with position and alive state
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    id: str
    position: Position
    decision_model: DecisionModel | None = None
    alive: bool = True


# ---------------------------------------------------------------------------
# Environment — the 2D grid simulation
# ---------------------------------------------------------------------------

class Environment:
    """A 2D grid world where agents make decisions and interact with resources.

    Lifecycle:
      1. Create with grid size, actions, and resources
      2. Add agents with add_agent()
      3. Call step() repeatedly or run(steps) for batch execution
      4. Read events and state as needed
    """

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

        # Validate uniqueness
        action_names = [a.name for a in actions]
        if len(action_names) != len(set(action_names)):
            duped = {n for n in action_names if action_names.count(n) > 1}
            raise ValueError(f"Duplicate action names: {duped}")
        resource_types = [r.type for r in resources]
        if len(resource_types) != len(set(resource_types)):
            duped = {t for t in resource_types if resource_types.count(t) > 1}
            raise ValueError(f"Duplicate resource types: {duped}")

        self._action_registry: dict[str, ActionRule] = {a.name: a for a in actions}
        self._resource_rules: dict[str, ResourceRule] = {r.type: r for r in resources}
        self._rng = random.Random(seed)

        # Mutable state
        self._agents: list[Agent] = []
        self._resources: list[Resource] = []
        self._step: int = 0
        self._events: list[Event] = []
        self._resource_counter: int = 0

        self._spawn_initial_resources()

    # --- Resource spawning ---

    def _spawn_initial_resources(self) -> None:
        """Place initial resources according to the resource rules."""
        for rule in self._resource_rules.values():
            for _ in range(rule.count):
                self._spawn_resource(rule)

    def _spawn_resource(self, rule: ResourceRule) -> None:
        """Spawn a single resource at a random position."""
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

    # --- Public API ---

    def add_agent(self, agent: Agent) -> None:
        self._agents.append(agent)

    def add_resource(self, resource: Resource) -> None:
        self._resources.append(resource)

    def is_finished(self) -> bool:
        """True if no agents are alive."""
        return not any(a.alive for a in self._agents)

    def get_state(self) -> dict:
        """Snapshot of the current simulation state."""
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

    def get_spec(self) -> dict:
        """Return the environment configuration as a dict."""
        return {
            "available_actions": list(self._action_registry.keys()),
            "resource_types": {
                rtype: {"properties": rule.properties, "count": rule.count, "regenerate": rule.regenerate}
                for rtype, rule in self._resource_rules.items()
            },
            "grid": {"width": self.width, "height": self.height},
        }

    # --- Simulation step ---

    def _build_perception(self, agent: Agent) -> dict:
        """Build what an agent can see: its position, resources, and grid info."""
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
                for rtype in {r.properties.get("type") for r in self._resources if "type" in r.properties} | set(self._resource_rules)
            },
            "last_action_result": {},
        }

    def _apply_action(self, agent: Agent, action: Action) -> tuple[float, dict]:
        """Apply an action and return (reward, result_dict)."""
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
        """Move the agent, clamping to grid bounds."""
        agent.position.x = max(0, min(self.width - 1, agent.position.x + effect.dx))
        agent.position.y = max(0, min(self.height - 1, agent.position.y + effect.dy))
        return effect.reward, {}

    def _apply_consume(self, agent: Agent, effect: ConsumeEffect) -> tuple[float, dict]:
        """Try to consume a resource at the agent's position."""
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
        # Regenerate if the rule says so
        rule = self._resource_rules.get(effect.resource_type)
        if rule and rule.regenerate:
            self._spawn_resource(rule)
        return effect.reward, {"consumed": True, "resource_type": effect.resource_type}

    def step(self) -> list[Event]:
        """Advance one simulation step.

        For each alive agent:
          1. Build perception (what the agent sees)
          2. Ask the decision model to choose an action
          3. Apply the action to the environment
          4. Update the decision model with the result
          5. Record the event
        """
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

            # Snapshot model state (convert numpy arrays to lists)
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

    def run(self, steps: int) -> list[Event]:
        """Run multiple steps. Stops early if all agents are dead."""
        all_events: list[Event] = []
        for _ in range(steps):
            if self.is_finished():
                break
            all_events.extend(self.step())
        return all_events
