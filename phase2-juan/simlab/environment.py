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
    perception: dict = field(default_factory=dict)
    pre_state: dict = field(default_factory=dict)
    available_actions: list[str] = field(default_factory=list)


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
        self._resources.append(
            Resource(
                id=f"{rule.type}_{self._resource_counter}",
                position=Position(
                    self._rng.randint(0, self.width - 1),
                    self._rng.randint(0, self.height - 1),
                ),
                properties=properties,
            )
        )

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
                rtype: {
                    "properties": rule.properties,
                    "count": rule.count,
                    "regenerate": rule.regenerate,
                }
                for rtype, rule in self._resource_rules.items()
            },
            "grid": {"width": self.width, "height": self.height},
        }

    # --- Perception: what an agent can see ---

    def _get_all_resource_types(self) -> set[str]:
        """Get all resource types (both currently placed and defined in rules)."""
        placed = {
            r.properties.get("type") for r in self._resources if "type" in r.properties
        }
        defined = set(self._resource_rules)
        return placed | defined

    def _resources_by_type(self, rtype: str) -> list[dict]:
        """Get all resources of a given type as dicts with x, y, and properties."""
        return [
            {"x": r.position.x, "y": r.position.y, **r.properties}
            for r in self._resources
            if r.properties.get("type") == rtype
        ]

    def _build_perception(self, agent: Agent) -> dict:
        """Build the perception dict that gets passed to a DecisionModel.

        Contains: agent position, grid size, current step,
        all resources grouped by type, and last action result.
        """
        return {
            "x": agent.position.x,
            "y": agent.position.y,
            "grid_width": self.width,
            "grid_height": self.height,
            "step": self._step,
            "resources": {
                rtype: self._resources_by_type(rtype)
                for rtype in self._get_all_resource_types()
            },
            "last_action_result": {},
        }

    # --- Action execution ---

    def _apply_action(self, agent: Agent, action: Action) -> tuple[float, dict]:
        """Execute an action and return (reward, result_dict)."""
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
        """Move the agent by (dx, dy), clamping to grid bounds."""
        new_x = agent.position.x + effect.dx
        new_y = agent.position.y + effect.dy
        agent.position.x = max(0, min(self.width - 1, new_x))
        agent.position.y = max(0, min(self.height - 1, new_y))
        return effect.reward, {}

    def _find_resource_at(self, resource_type: str, x: int, y: int) -> int | None:
        """Find the index of a resource of the given type at position (x, y)."""
        for i, r in enumerate(self._resources):
            if (
                r.properties.get("type") == resource_type
                and r.position.x == x
                and r.position.y == y
            ):
                return i
        return None

    def _apply_consume(self, agent: Agent, effect: ConsumeEffect) -> tuple[float, dict]:
        """Try to consume a resource at the agent's current position."""
        idx = self._find_resource_at(
            effect.resource_type, agent.position.x, agent.position.y
        )

        if idx is None:
            return 0.0, {"consumed": False}

        # Remove the resource
        self._resources.pop(idx)

        # Regenerate it elsewhere if the rule says so
        rule = self._resource_rules.get(effect.resource_type)
        if rule and rule.regenerate:
            self._spawn_resource(rule)

        return effect.reward, {"consumed": True, "resource_type": effect.resource_type}

    # --- Simulation loop ---

    def _snapshot_model_state(self, model: DecisionModel) -> dict:
        """Capture the model's internal state, converting numpy arrays to lists."""
        return {
            k: v.tolist() if hasattr(v, "tolist") else v
            for k, v in model.get_state().items()
        }

    def step(self) -> list[Event]:
        """Advance one simulation step.

        For each alive agent:
          1. Build perception (what the agent sees)
          2. Ask the decision model to choose an action
          3. Apply the action to the environment
          4. Tell the model what happened (so it can learn)
          5. Record the event
        """
        step_events: list[Event] = []

        for agent in self._agents:
            if not agent.alive or agent.decision_model is None:
                continue

            # 1. What does the agent see?
            perception = self._build_perception(agent)

            # 1b. Snapshot internal state BEFORE deciding (for decision traces)
            pre_state = self._snapshot_model_state(agent.decision_model)

            # 2. What does the agent decide to do?
            action = agent.decision_model.decide(perception)

            # 3. Execute the action
            reward, action_result = self._apply_action(agent, action)

            # 4. Tell the model what happened
            new_perception = self._build_perception(agent)
            new_perception["last_action_result"] = action_result
            agent.decision_model.update(action, reward, new_perception)

            # 5. Record the event (with full decision trace)
            event = Event(
                step=self._step,
                agent_id=agent.id,
                action=action,
                outcome={
                    "action_result": action_result,
                    "reward": reward,
                    "model_state": self._snapshot_model_state(agent.decision_model),
                },
                perception=perception,
                pre_state=pre_state,
                available_actions=list(self._action_registry.keys()),
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
