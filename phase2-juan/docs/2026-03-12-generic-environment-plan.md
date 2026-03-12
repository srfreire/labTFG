# Generic Environment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Environment so actions and resources are configurable via dataclasses instead of hardcoded.

**Architecture:** Add effect types (MoveEffect, ConsumeEffect, NoopEffect), ActionRule, and ResourceRule dataclasses. Refactor Environment to dispatch actions by effect type and spawn resources from rules. Generalize ModelAdapter with a perception_mapper callback.

**Tech Stack:** Python 3.12, pytest, dataclasses

**Spec:** `phase2-juan/docs/2026-03-12-generic-environment-design.md`

---

## File Map

- **Modify:** `phase2-juan/simlab/environment.py` — add config dataclasses, refactor Environment + ModelAdapter
- **Rewrite:** `phase2-juan/tests/test_environment.py` — update all tests for new constructor/config
- **Rewrite:** `phase2-juan/tests/test_adapter.py` — update for perception_mapper + new perception format

---

## Task 1: Add effect types and config dataclasses

**Files:**
- Modify: `phase2-juan/simlab/environment.py:20-77` (replace `_DELTAS`, add new types after existing basic types)
- Test: `phase2-juan/tests/test_environment.py`

- [ ] **Step 1: Write tests for new dataclasses**

Add to `tests/test_environment.py`:

```python
from simlab.environment import (
    MoveEffect, ConsumeEffect, NoopEffect, ActionRule, ResourceRule,
)

def test_move_effect_dataclass():
    e = MoveEffect(dx=1, dy=0)
    assert e.dx == 1
    assert e.reward == 0.0

def test_move_effect_custom_reward():
    e = MoveEffect(dx=0, dy=-1, reward=-0.01)
    assert e.reward == -0.01

def test_consume_effect_dataclass():
    e = ConsumeEffect(resource_type="food", reward=1.0)
    assert e.resource_type == "food"

def test_noop_effect_dataclass():
    e = NoopEffect()
    assert e.reward == 0.0

def test_action_rule_dataclass():
    rule = ActionRule(name="move_up", effect=MoveEffect(dx=0, dy=-1))
    assert rule.name == "move_up"
    assert isinstance(rule.effect, MoveEffect)

def test_resource_rule_dataclass():
    rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=5)
    assert rule.type == "food"
    assert rule.regenerate is True

def test_resource_rule_defaults():
    rule = ResourceRule(type="water", count=3)
    assert rule.properties == {}
    assert rule.regenerate is True
```

**Note:** Existing basic dataclass tests (`test_position_dataclass`, `test_action_dataclass`, `test_action_default_params`, `test_event_dataclass`, `test_resource_dataclass`) and `test_decision_model_protocol_satisfied` must be preserved as-is throughout all tasks.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py::test_move_effect_dataclass -v`
Expected: FAIL — `ImportError: cannot import name 'MoveEffect'`

- [ ] **Step 3: Implement effect types and config dataclasses**

In `environment.py`, after the `Resource` dataclass (line 47) and before the `DecisionModel` Protocol (line 50), add:

```python
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
```

Remove the `_DELTAS` dict (lines 69-77).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py -k "effect or action_rule or resource_rule" -v`
Expected: all 6 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_environment.py
git commit -m "feat[phase2]: add effect types, ActionRule, and ResourceRule dataclasses"
```

---

## Task 2: Refactor Environment constructor and resource spawning

**Files:**
- Modify: `phase2-juan/simlab/environment.py:82-100` (Environment.__init__)
- Test: `phase2-juan/tests/test_environment.py`

- [ ] **Step 1: Write tests for new constructor and spawn**

Replace `test_environment_init`, `test_add_agent`, `test_add_resource` in `tests/test_environment.py`. Also add helper at top of file:

```python
# --- Helpers ---

def _basic_actions():
    return [
        ActionRule("right", MoveEffect(dx=1, dy=0)),
        ActionRule("left", MoveEffect(dx=-1, dy=0)),
        ActionRule("up", MoveEffect(dx=0, dy=-1)),
        ActionRule("down", MoveEffect(dx=0, dy=1)),
        ActionRule("stay", NoopEffect()),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]

def _food_rule():
    return [ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=2, regenerate=True)]


# --- Environment init tests ---

def test_environment_init():
    env = Environment(10, 10, actions=_basic_actions(), resources=[])
    assert env.width == 10
    assert env.height == 10

def test_spawn_initial_resources():
    env = Environment(5, 5, actions=[], resources=_food_rule(), seed=42)
    state = env.get_state()
    assert len(state["resources"]) == 2
    assert all(r.get("type") == "food" for r in state["resources"])

def test_add_agent():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    state = env.get_state()
    assert len(state["agents"]) == 1

def test_add_resource_manual():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_resource(Resource(id="f1", position=Position(2, 3), properties={"type": "food", "palatability": 0.8}))
    state = env.get_state()
    assert len(state["resources"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py::test_spawn_initial_resources -v`
Expected: FAIL — `TypeError` because Environment constructor doesn't accept `actions`/`resources` yet

- [ ] **Step 3: Implement new constructor + spawn methods**

Replace the Environment `__init__` and add `_spawn_initial_resources` and `_spawn_resource`:

```python
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
            position=Position(
                self._rng.randint(0, self.width - 1),
                self._rng.randint(0, self.height - 1),
            ),
            properties=properties,
        ))
```

- [ ] **Step 4: Run the new tests**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py -k "init or spawn or add_agent or add_resource" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_environment.py
git commit -m "feat[phase2]: refactor Environment constructor with ActionRule/ResourceRule"
```

---

## Task 3: Refactor _apply_action, _apply_move, _apply_consume

**Files:**
- Modify: `phase2-juan/simlab/environment.py:138-166` (replace old _apply_action)
- Test: `phase2-juan/tests/test_environment.py`

- [ ] **Step 1: Write tests for generic action dispatch**

Replace the movement and food collection tests in `tests/test_environment.py`:

```python
# --- Movement tests ---

def test_agent_moves_on_action():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 1
    assert state["agents"][0]["y"] == 0

def test_agent_clamps_at_wall():
    actions = [ActionRule("left", MoveEffect(dx=-1, dy=0))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysLeft:
        def decide(self, perception: dict) -> Action:
            return Action("left")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysLeft()))
    env.step()
    state = env.get_state()
    assert state["agents"][0]["x"] == 0

def test_unknown_action_returns_zero_reward():
    env = Environment(5, 5, actions=[], resources=[])

    class _BadAction:
        def decide(self, perception: dict) -> Action:
            return Action("fly")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_BadAction()))
    events = env.step()
    assert events[0].outcome["action_result"] == {"error": "unknown_action"}

# --- Resource consumption tests ---

def test_consume_resource():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food", "palatability": 0.5}))

    class _AlwaysEat:
        def decide(self, perception: dict) -> Action:
            return Action("eat")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is True
    assert events[0].outcome["reward"] == 1.0

def test_consume_nothing_returns_zero():
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysEat:
        def decide(self, perception: dict) -> Action:
            return Action("eat")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    events = env.step()
    assert events[0].outcome["action_result"]["consumed"] is False
    assert events[0].outcome["reward"] == 0.0

def test_resource_regenerates():
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=0, regenerate=True)
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food", "palatability": 0.5}))

    class _AlwaysEat:
        def decide(self, perception: dict) -> Action:
            return Action("eat")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    state = env.get_state()
    assert len(state["resources"]) == 1  # original consumed, new one spawned

def test_consume_no_regenerate():
    food_rule = ResourceRule(type="food", properties={}, count=0, regenerate=False)
    actions = [ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0))]
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_resource(Resource(id="f1", position=Position(0, 0), properties={"type": "food"}))

    class _AlwaysEat:
        def decide(self, perception: dict) -> Action:
            return Action("eat")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysEat()))
    env.step()
    state = env.get_state()
    assert len(state["resources"]) == 0  # consumed, not regenerated

def test_noop_action():
    actions = [ActionRule("rest", NoopEffect(reward=0.1))]
    env = Environment(5, 5, actions=actions, resources=[])

    class _AlwaysRest:
        def decide(self, perception: dict) -> Action:
            return Action("rest")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self) -> dict:
            return {}

    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRest()))
    events = env.step()
    assert events[0].outcome["reward"] == 0.1
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py::test_consume_resource -v`
Expected: FAIL

- [ ] **Step 3: Implement _apply_action, _apply_move, _apply_consume**

Replace old `_apply_action` in `environment.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py -k "move or clamp or unknown or consume or regenerate or noop" -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_environment.py
git commit -m "feat[phase2]: generic _apply_action dispatching by effect type"
```

---

## Task 4: Refactor _build_perception and step()

**Files:**
- Modify: `phase2-juan/simlab/environment.py:124-197` (perception + step)
- Test: `phase2-juan/tests/test_environment.py`

- [ ] **Step 1: Write tests for new perception and step**

Replace/update relevant tests in `tests/test_environment.py`:

```python
def test_perception_keys():
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=1)
    env = Environment(5, 5, actions=_basic_actions(), resources=[food_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    expected = {"x", "y", "grid_width", "grid_height", "step", "resources", "last_action_result"}
    assert set(perception.keys()) == expected

def test_perception_resources_grouped_by_type():
    food_rule = ResourceRule(type="food", properties={}, count=2)
    water_rule = ResourceRule(type="water", properties={}, count=1)
    env = Environment(5, 5, actions=[], resources=[food_rule, water_rule], seed=42)
    agent = Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay())
    env.add_agent(agent)
    perception = env._build_perception(agent)
    assert "food" in perception["resources"]
    assert "water" in perception["resources"]
    assert len(perception["resources"]["food"]) == 2
    assert len(perception["resources"]["water"]) == 1

def test_step_outcome_has_action_result():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert "action_result" in events[0].outcome
    assert "reward" in events[0].outcome
    assert "model_state" in events[0].outcome

def test_step_injects_last_action_result():
    """Verify that step() sets last_action_result in the new_perception passed to update()."""
    results = []

    class _CaptureUpdate:
        def decide(self, perception: dict) -> Action:
            return Action("stay")
        def update(self, action, reward, new_perception):
            results.append(new_perception.get("last_action_result"))
        def get_state(self) -> dict:
            return {}

    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_CaptureUpdate()))
    env.step()
    assert results[0] == {}  # NoopEffect returns {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py::test_perception_keys -v`
Expected: FAIL — perception still has old keys

- [ ] **Step 3: Implement new _build_perception and step**

Replace `_build_perception` and `step` in `environment.py`:

```python
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
            step=self._step,
            agent_id=agent.id,
            action=action,
            outcome={"action_result": action_result, "reward": reward, "model_state": snapshot},
        )
        step_events.append(event)
        self._events.append(event)

    self._step += 1
    return step_events
```

- [ ] **Step 4: Run tests**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py -k "perception or step_outcome or step_injects" -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_environment.py
git commit -m "feat[phase2]: generic _build_perception and step() with action_result"
```

---

## Task 5: Add get_spec() and update remaining tests

**Files:**
- Modify: `phase2-juan/simlab/environment.py`
- Rewrite: `phase2-juan/tests/test_environment.py` (remaining tests: step_returns_events, step_increments, run_n_steps, is_finished, determinism, serialization, model_state)

- [ ] **Step 1: Write test for get_spec**

```python
def test_get_spec():
    actions = [
        ActionRule("move_up", MoveEffect(dx=0, dy=-1)),
        ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
    ]
    resources = [ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=5)]
    env = Environment(5, 5, actions=actions, resources=resources)
    spec = env.get_spec()
    assert set(spec["available_actions"]) == {"move_up", "eat"}
    assert "food" in spec["resource_types"]
    assert spec["resource_types"]["food"]["count"] == 5
    assert spec["grid"] == {"width": 5, "height": 5}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py::test_get_spec -v`
Expected: FAIL — `get_spec` not defined

- [ ] **Step 3: Implement get_spec**

Add to Environment class in `environment.py`:

```python
def get_spec(self) -> dict:
    return {
        "available_actions": list(self._action_registry.keys()),
        "resource_types": {
            rtype: {"properties": rule.properties, "count": rule.count, "regenerate": rule.regenerate}
            for rtype, rule in self._resource_rules.items()
        },
        "grid": {"width": self.width, "height": self.height},
    }
```

- [ ] **Step 4: Update remaining tests**

Update all remaining tests to use new constructor. Replace:

```python
def test_step_returns_events():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert len(events) == 1
    assert isinstance(events[0], Event)

def test_step_increments_counter():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.step()
    assert env.get_state()["step"] == 1

def test_run_n_steps():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.run(10)
    assert len(events) == 10

def test_is_finished_when_all_dead():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay(), alive=False))
    assert env.is_finished()

def test_is_finished_false_when_alive():
    env = Environment(5, 5, actions=[], resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    assert not env.is_finished()

def test_seed_determinism():
    def run_sim(seed):
        food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=0, regenerate=True)
        actions = [
            ActionRule("right", MoveEffect(dx=1, dy=0)),
            ActionRule("eat", ConsumeEffect(resource_type="food", reward=1.0)),
        ]
        env = Environment(5, 5, actions=actions, resources=[food_rule], seed=seed)
        env.add_resource(Resource(id="f1", position=Position(1, 0), properties={"type": "food", "palatability": 0.5}))
        env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysRight()))
        return env.run(10)

    events_a = run_sim(42)
    events_b = run_sim(42)
    for a, b in zip(events_a, events_b):
        assert a.outcome == b.outcome

def test_get_state_is_serializable():
    import json
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    env.add_resource(Resource(id="f1", position=Position(2, 2), properties={"type": "food"}))
    env.step()
    state = env.get_state()
    json.dumps(state)

def test_step_records_model_state():
    env = Environment(5, 5, actions=_basic_actions(), resources=[])
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=_AlwaysStay()))
    events = env.step()
    assert events[0].outcome["model_state"] == {"dummy": True}
```

- [ ] **Step 5: Run full test_environment.py**

Run: `cd phase2-juan && uv run pytest tests/test_environment.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_environment.py
git commit -m "feat[phase2]: add get_spec() and migrate all environment tests"
```

---

## Task 6: Refactor ModelAdapter with perception_mapper

**Files:**
- Modify: `phase2-juan/simlab/environment.py:210-242` (ModelAdapter)
- Rewrite: `phase2-juan/tests/test_adapter.py`

- [ ] **Step 1: Write tests for new ModelAdapter**

Replace `tests/test_adapter.py`:

```python
"""Tests for ModelAdapter — imports Phase 1 classes."""
from __future__ import annotations

from simlab.environment import (
    Action,
    ActionRule,
    Agent,
    ConsumeEffect,
    DecisionModel,
    Environment,
    MoveEffect,
    ModelAdapter,
    NoopEffect,
    Position,
    Resource,
    ResourceRule,
    homeostatic_perception_mapper,
)
from denis.homeostatic import HomeostaticModel, HomeostaticParams
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode


def _make_perception_dict(x=2, y=2, grid_w=5, grid_h=5, step=0, ate=False, food=None):
    """Build a perception dict in the NEW generic format."""
    if food is None:
        food = [{"x": 3, "y": 2, "palatability": 0.8, "type": "food"}]
    return {
        "x": x, "y": y,
        "grid_width": grid_w, "grid_height": grid_h,
        "resources": {"food": food},
        "last_action_result": {"consumed": ate} if ate else {},
        "step": step,
    }


# --- Adapter pass-through (no mapper) ---

def test_adapter_passthrough_no_mapper():
    """Without a mapper, perception dict passes through as-is."""
    calls = []

    class _Spy:
        def decide(self, perception):
            calls.append(perception)
            return Action("stay")
        def update(self, action, reward, new_perception):
            pass
        def get_state(self):
            return {}

    adapter = ModelAdapter(_Spy())
    p = {"x": 1, "y": 2}
    adapter.decide(p)
    assert calls[0] is p  # same dict object, no transformation


# --- Adapter with mapper + HomeostaticModel ---

def test_adapter_with_mapper_decide():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    action = adapter.decide(_make_perception_dict())
    assert isinstance(action, Action)
    assert action.name in {"up", "down", "left", "right", "stay"}

def test_adapter_with_mapper_update():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    action = adapter.decide(_make_perception_dict())
    adapter.update(action, -0.01, _make_perception_dict(step=1))

def test_adapter_get_state_returns_homeostatic_keys():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    state = adapter.get_state()
    assert "fat" in state
    assert "glycogen" in state
    assert "hunger" in state

def test_adapter_satisfies_decision_model_protocol():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    assert isinstance(adapter, DecisionModel)


# --- Adapter with HedonicModel ---

def test_adapter_with_hedonic_model():
    params = HedonicParams(grid_size=(5, 5))
    model = HedonicModel(params)
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    initial_epsilon = adapter.get_state()["epsilon"]
    for i in range(5):
        action = adapter.decide(_make_perception_dict(step=i))
        adapter.update(action, -0.01, _make_perception_dict(step=i + 1))
    assert adapter.get_state()["epsilon"] < initial_epsilon


# --- Adapter with IntegratedModel ---

def test_adapter_with_integrated_model():
    model = IntegratedModel(
        homeostatic=HomeostaticModel(HomeostaticParams()),
        hedonic=HedonicModel(HedonicParams(grid_size=(5, 5))),
        mode=IntegrationMode.INDEPENDENT,
    )
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    for i in range(10):
        action = adapter.decide(_make_perception_dict(step=i))
        adapter.update(action, -0.01, _make_perception_dict(step=i + 1))
    state = adapter.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state


# --- Full integration: adapter inside Environment ---

def test_environment_run_with_homeostatic_adapter():
    model = HomeostaticModel(HomeostaticParams())
    adapter = ModelAdapter(model, perception_mapper=homeostatic_perception_mapper)
    actions = [
        ActionRule("up", MoveEffect(dx=0, dy=-1)),
        ActionRule("down", MoveEffect(dx=0, dy=1)),
        ActionRule("left", MoveEffect(dx=-1, dy=0)),
        ActionRule("right", MoveEffect(dx=1, dy=0)),
        ActionRule("stay", NoopEffect()),
    ]
    food_rule = ResourceRule(type="food", properties={"palatability": (0.1, 1.0)}, count=2, regenerate=True)
    env = Environment(5, 5, actions=actions, resources=[food_rule], seed=42)
    env.add_agent(Agent(id="a1", position=Position(0, 0), decision_model=adapter))
    events = env.run(20)
    assert len(events) == 20
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd phase2-juan && uv run pytest tests/test_adapter.py::test_adapter_passthrough_no_mapper -v`
Expected: FAIL — ModelAdapter doesn't accept `perception_mapper`

- [ ] **Step 3: Implement new ModelAdapter + homeostatic_perception_mapper**

Replace ModelAdapter and add mapper function in `environment.py`:

```python
class ModelAdapter:
    """Translates between Phase 1 concrete types and Phase 2 generic types.

    Phase 1 imports are lazy (inside methods) so this module works
    without Phase 1 installed — only adapter calls require it.
    """

    def __init__(self, phase1_model, perception_mapper=None) -> None:
        self._model = phase1_model
        self._mapper = perception_mapper

    def decide(self, perception: dict) -> Action:
        if self._mapper:
            mapped = self._mapper(perception)
        else:
            mapped = perception
        p1_action = self._model.decide(mapped)
        return Action(name=p1_action.name, params=p1_action.params)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        from decisionlab.models.protocol import Action as P1Action
        p1_action = P1Action(action.name, action.params)
        if self._mapper:
            mapped = self._mapper(new_perception)
        else:
            mapped = new_perception
        self._model.update(p1_action, reward, mapped)

    def get_state(self) -> dict:
        return self._model.get_state()


def homeostatic_perception_mapper(perception: dict):
    """Mapper for the food/homeostatic paradigm from Phase 1."""
    from decisionlab.models.protocol import Perception as P1Perception
    food_sources = tuple(
        {k: v for k, v in r.items() if k != "type"}
        for r in perception.get("resources", {}).get("food", [])
    )
    return P1Perception(
        position=(perception["x"], perception["y"]),
        grid_size=(perception["grid_width"], perception["grid_height"]),
        food_sources=food_sources,
        ate_food=perception.get("last_action_result", {}).get("consumed", False),
        step=perception.get("step", 0),
    )
```

- [ ] **Step 4: Run all adapter tests**

Run: `cd phase2-juan && uv run pytest tests/test_adapter.py -v`
Expected: all PASS

- [ ] **Step 5: Run full test suite**

Run: `cd phase2-juan && uv run pytest -v`
Expected: all tests PASS (both test files)

- [ ] **Step 6: Commit**

```bash
git add phase2-juan/simlab/environment.py phase2-juan/tests/test_adapter.py
git commit -m "feat[phase2]: generalize ModelAdapter with perception_mapper"
```

---

## Task 7: Final cleanup and verification

- [ ] **Step 1: Verify no old code remains**

Check that `environment.py` does NOT contain:
- `_DELTAS`
- `food_regenerate`
- `food_palatability_range`
- `_to_typed_perception`
- `nearby_resources` (in `_build_perception`)
- `ate_food` (in `_build_perception`)

- [ ] **Step 2: Run full test suite one last time**

Run: `cd phase2-juan && uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 3: Commit cleanup if needed**

```bash
git add phase2-juan/simlab/environment.py
git commit -m "refactor[phase2]: remove leftover hardcoded code"
```
