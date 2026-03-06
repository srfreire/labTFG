# Design: Environment Base

## Resumen

Framework generico en Python que define las abstracciones de un mundo de simulacion para paradigmas de toma de decisiones humanas. Es la "caja de arena vacia" sobre la que:

- **Agente Plataforma** (Claude, fase 2) construye environments concretos
- **Agentes de la fase 1** (codigo Python) pueblan el environment como organismos
- **Agentes Observador/Analitico/Redactor** (Claude, fase 2) monitorizan, analizan e informan

## Decisiones tomadas

| Decision | Valor | Razon |
|----------|-------|-------|
| Tipo de mundo | Solo Grid 2D | YAGNI. Se amplia si hace falta |
| Agentes de simulacion | Codigo Python (reglas, EDOs, RL) | Nunca LLM en runtime de simulacion |
| Multi-agente | Si, desde el inicio | El script de Denis ya lo soporta |
| Mix de paradigmas | Si | Cada agente puede tener distinto DecisionModel |
| Visualizacion | Fuera del environment | Responsabilidad del Observador/Redactor |
| Arquitectura | Composicion con Protocol | Flexible, intercambiable, Pythonico |
| Stack | Python puro, sin frameworks | Control total, adecuacion academica |

## Estructura de ficheros

```
phase2/
├── simlab/
│   ├── __init__.py
│   └── environment.py   # Todo el framework base
```

Un solo fichero. Se separa solo si crece demasiado.

## Conceptos del framework

| Concepto | Que es | Ejemplo (caso Denis) |
|----------|--------|---------------------|
| `Grid` | Espacio 2D (ancho x alto) | Grid 10x10 |
| `Resource` | Objeto en el grid con propiedades | Comida en (3,4) con palatabilidad=0.8 |
| `Agent` | Contenedor: posicion + estado + decision_model | Organismo con energia=20, nutrientes=25 |
| `DecisionModel` | Protocol — cualquier objeto con `decide()` | RuleBasedModel, QLearningModel (fase 1) |
| `Action` | Lo que un agente hace en un step | Move(dx=1,dy=0), Rest, Eat |
| `Event` | Registro de algo que paso | "agente_1 comio en (3,4) step=42" |
| `Environment` | Orquesta el loop de simulacion | 100 steps, 5 agentes, comida escasa |

## API principal

```python
from dataclasses import dataclass, field
from typing import Protocol, Any

# --- Tipos basicos ---

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

# --- Protocol para paradigmas de decision (fase 1 lo implementa) ---

class DecisionModel(Protocol):
    def decide(self, perception: dict) -> Action: ...

# --- Resource ---

@dataclass
class Resource:
    id: str
    position: Position
    properties: dict = field(default_factory=dict)
    # properties puede ser: {"type": "food", "palatability": 0.8, "energy": 10}

# --- Agent (contenedor, no decide por si mismo) ---

@dataclass
class Agent:
    id: str
    position: Position
    state: dict = field(default_factory=dict)
    decision_model: DecisionModel | None = None
    alive: bool = True

# --- Environment ---

class Environment:
    def __init__(self, width: int, height: int, seed: int | None = None): ...

    def add_agent(self, agent: Agent) -> None: ...
    def add_resource(self, resource: Resource) -> None: ...

    def step(self) -> list[Event]:
        """Avanza un paso: percepcion -> decision -> accion -> actualizacion."""
        ...

    def run(self, steps: int) -> list[Event]:
        """Ejecuta N pasos y devuelve todos los eventos."""
        ...

    def is_finished(self) -> bool:
        """Condicion de terminacion (todos muertos, objetivo cumplido, etc.)."""
        ...

    def get_state(self) -> dict:
        """Snapshot serializable del estado actual (para el Observador)."""
        ...
```

## Flujo de un step

```
1. Para cada agente vivo:
   a. Percepcion: el environment construye un dict con lo que el agente "ve"
      (posicion, recursos cercanos, otros agentes, su propio estado)
   b. Decision: agent.decision_model.decide(perception) -> Action
   c. Ejecucion: el environment aplica la accion (mover, comer, descansar...)
   d. Actualizacion: se actualiza el estado del agente y del environment
   e. Registro: se crea un Event con lo que paso

2. Actualizacion global del environment (regenerar recursos, etc.)

3. Devolver lista de Events del step
```

## Que NO hace el environment base

- No implementa ningun paradigma de decision (eso es fase 1)
- No visualiza nada (eso es el Observador/Redactor)
- No usa LLMs en runtime de simulacion
- No persiste datos (eso lo hace el Observador con los Events)

## Extensibilidad

El Agente Plataforma (Claude) puede construir environments concretos:
- Configurando parametros (tamanio grid, numero de recursos, propiedades)
- Definiendo reglas de actualizacion (como se regeneran recursos, condiciones de muerte)
- Combinando agentes con distintos DecisionModels

Los paradigmas de decision de la fase 1 solo necesitan implementar:
```python
class MiModelo:
    def decide(self, perception: dict) -> Action:
        # cualquier logica
        return Action(name="move", params={"dx": 1, "dy": 0})
```
