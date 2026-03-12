# Generic Environment Design

**Date**: 2026-03-12
**Context**: Acuerdo con Eduardo — la integración entre Fase 1 (Pablo) y Fase 2 (Juan) es iterativa. El Environment define recursos y acciones dinámicamente según lo que Pablo describe.

---

## Problem

El Environment actual (`simlab/environment.py`) tiene acciones hardcoded (`_DELTAS`: up/down/left/right/stay), recursos hardcoded (food con palatability), lógica fija en `_apply_action` y rewards fijos. Esto no soporta el flujo iterativo acordado donde Pablo describe paradigmas arbitrarios y el Environment crea una sandbox con las acciones y recursos apropiados.

## Flujo iterativo entre fases

1. Pablo describe de qué tratan sus agentes (texto informal)
2. El Environment (Agente Plataforma) crea la sandbox con recursos y acciones apropiados
3. Se devuelve a Pablo una spec declarativa: `{"available_actions": [...], "resource_types": [...], "grid": {...}}`
4. Pablo programa sus DecisionModels contra esa spec

## Approach

Enfoque B — **dataclasses de configuración**. Tipado y validable, pero serializable a/desde dict para que un LLM lo genere. Grid 2D como única topología.

---

## Effect types

Mecánicas del mundo — qué puede pasar cuando un agente actúa. Conjunto fijo, extensible añadiendo nuevos tipos cuando se necesiten.

```python
@dataclass
class MoveEffect:
    """Mueve al agente en el grid."""
    dx: int
    dy: int
    reward: float = 0.0

@dataclass
class ConsumeEffect:
    """Consume un recurso en la misma posición del agente."""
    resource_type: str
    reward: float

@dataclass
class NoopEffect:
    """No hace nada (descansar, esperar...)."""
    reward: float = 0.0

# Requiere Python 3.10+ (pyproject.toml ya exige >=3.12)
Effect = MoveEffect | ConsumeEffect | NoopEffect
```

## Nota de migración: acciones atómicas

En el código actual, un movimiento (ej: `move_right`) mueve al agente Y automáticamente comprueba si hay comida en la nueva posición. En el diseño genérico, mover y consumir son efectos separados — el agente debe decidir `"eat"` como acción distinta.

Esto es un cambio intencional: cada acción tiene un único efecto, lo que hace el sistema más genérico y composable. Los DecisionModels de Pablo deberán adaptarse para emitir acciones de consumo explícitas. El `homeostatic_perception_mapper` ya traduce `last_action_result.consumed` a `ate_food` para mantener compatibilidad en la percepción.

La penalización temporal actual (`-0.01` por movimiento) se configura ahora por acción: `MoveEffect(dx=0, dy=-1, reward=-0.01)`. Los environments que repliquen el paradigma de supervivencia deben configurarlo explícitamente.

## ActionRule and ResourceRule

Conectan lo que Pablo pide con las mecánicas del mundo.

```python
@dataclass
class ActionRule:
    """Una acción que los agentes pueden ejecutar."""
    name: str       # nombre libre: "drink", "dance", "move_up"...
    effect: Effect  # qué pasa en el mundo

@dataclass
class ResourceRule:
    """Define un tipo de recurso que existe en el mundo."""
    type: str                   # "food", "water", "gold"...
    properties: dict            # propiedades con rangos, ej: {"palatability": (0.1, 1.0)}
    count: int                  # instancias iniciales en el grid
    regenerate: bool = True     # si se regenera al consumirse
```

## Environment refactorizado

### Constructor

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
```

- `_action_registry`: dict `{name: ActionRule}` para lookup rápido
- `_resource_rules`: dict `{type: ResourceRule}` para regeneración
- `_spawn_initial_resources()`: se llama en `__init__`, genera las instancias iniciales según cada `ResourceRule`
- `add_agent()` y `add_resource()` siguen existiendo para setup adicional y tests. Los recursos añadidos manualmente coexisten con los auto-generados. Nota: los recursos manuales deben incluir `"type"` en `properties` para que `ConsumeEffect` y `_build_perception` los detecten

### _apply_action (genérico)

Despacha por tipo de efecto en vez de lógica fija:

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
```

`_apply_action` ahora devuelve `tuple[float, dict]` — reward + resultado de la acción (para la percepción genérica).

### _apply_move and _apply_consume

```python
def _apply_move(self, agent: Agent, effect: MoveEffect) -> tuple[float, dict]:
    """Mueve al agente, clamping a los bordes del grid."""
    agent.position.x = max(0, min(self.width - 1, agent.position.x + effect.dx))
    agent.position.y = max(0, min(self.height - 1, agent.position.y + effect.dy))
    return effect.reward, {}

def _apply_consume(self, agent: Agent, effect: ConsumeEffect) -> tuple[float, dict]:
    """Consume un recurso del tipo indicado en la posición del agente."""
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

### _spawn_initial_resources and _spawn_resource

```python
def _spawn_initial_resources(self) -> None:
    """Genera instancias iniciales según cada ResourceRule."""
    for rule in self._resource_rules.values():
        for _ in range(rule.count):
            self._spawn_resource(rule)

def _spawn_resource(self, rule: ResourceRule) -> None:
    """Crea una instancia de recurso con posición aleatoria y propiedades sampleadas."""
    self._resource_counter += 1
    properties = {"type": rule.type}
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

`_spawn_resource` copia `rule.type` en `properties["type"]` para que el filtrado en `_build_perception` y `_apply_consume` funcione.

### step() (actualizado)

La interfaz pública de `step()` no cambia, pero la implementación interna se adapta al nuevo `_apply_action` que devuelve `tuple[float, dict]`:

```python
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

Cambios respecto al actual:
- `reward, ate_food` pasa a `reward, action_result`
- `new_perception["ate_food"] = ate_food` pasa a `new_perception["last_action_result"] = action_result`
- `Event.outcome` usa `action_result` (dict genérico) en vez de `ate_food` (bool)

### _build_perception (genérico)

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
```

- `nearby_resources` (lista plana) pasa a `resources` (dict agrupado por tipo)
- `ate_food` (booleano hardcoded) pasa a `last_action_result` (dict genérico)
- Observabilidad completa: cada agente ve todos los recursos del grid. Si en el futuro se necesita visión limitada, se añade un `vision_radius` al Agent

### get_spec()

Devuelve la spec declarativa que se le manda a Pablo:

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

### Desaparece

- `_DELTAS` — el movimiento viene del `MoveEffect(dx, dy)`
- `food_regenerate` — configuración por `ResourceRule`
- `food_palatability_range` — propiedad dentro de `ResourceRule.properties`

### Se mantiene sin cambios (interfaz pública)

- `add_agent()`, `add_resource()` — siguen existiendo para setup manual y tests
- `run()`, `is_finished()`, `get_state()` — sin cambios
- `Position`, `Action`, `Event`, `Resource`, `Agent` — dataclasses base
- `DecisionModel` Protocol — sigue usando `Action` de Phase 2 (`simlab.environment`). El `ModelAdapter` traduce a/desde tipos de Phase 1

### Cambia internamente (misma interfaz)

- `step()` — misma firma, pero internamente usa `tuple[float, dict]` y `action_result` genérico
- `Event.outcome` — pasa de `{"ate_food": bool, ...}` a `{"action_result": dict, "reward": float, "model_state": dict}`

## ModelAdapter generalizado

El adapter recibe un `perception_mapper` opcional que traduce la percepción genérica al formato concreto de Pablo:

```python
class ModelAdapter:
    def __init__(self, phase1_model, perception_mapper=None):
        self._model = phase1_model
        self._mapper = perception_mapper

    def decide(self, perception: dict) -> Action:
        if self._mapper:
            p1_perception = self._mapper(perception)
        else:
            p1_perception = perception
        p1_action = self._model.decide(p1_perception)
        return Action(name=p1_action.name, params=p1_action.params)

    def update(self, action: Action, reward: float, new_perception: dict) -> None:
        from decisionlab.models.protocol import Action as P1Action
        p1_action = P1Action(action.name, action.params)
        if self._mapper:
            p1_perception = self._mapper(new_perception)
        else:
            p1_perception = new_perception
        self._model.update(p1_action, reward, p1_perception)

    def get_state(self) -> dict:
        return self._model.get_state()
```

El mapper actual para food/homeostático se extrae como función reutilizable. Nota: los dicts de recursos en `perception["resources"]["food"]` incluyen una clave `"type"` extra (inyectada por `_spawn_resource`), que es ignorada por `P1Perception`:

```python
def homeostatic_perception_mapper(perception: dict):
    """Mapper para el caso food/homeostático de Pablo."""
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

## Tests

Se reescriben los tests existentes para usar `ActionRule`/`ResourceRule` en vez de la config hardcoded. Misma cobertura:

- Dataclass tests (Position, Action, Event, Resource) — sin cambios
- Protocol test — sin cambios
- Environment init — usa actions/resources params
- Step/run — configura acciones vía ActionRule
- Movement — usa MoveEffect
- Resource collection — usa ConsumeEffect + ResourceRule
- Determinism — misma lógica, nueva config
- Serialization — sin cambios
- Adapter tests — usan perception_mapper, prueban pass-through y mapper concreto
