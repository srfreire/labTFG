# Tracker Agent — Design Spec

## Resumen

El Tracker es un agente LLM que recibe los Events de una simulacion ya ejecutada, los explora usando 3 tools, y devuelve un log estructurado con trayectorias por agente y episodios etiquetados.

---

## Responsabilidades

- Explorar los datos de simulacion via tools (events, trayectorias, estado interno)
- Identificar episodios significativos y etiquetarlos
- Generar un resumen estructurado con metricas por agente
- Devolver un JSON con trayectorias y episodios

## No hace

- No ejecuta simulaciones (recibe Events ya generados)
- No analiza patrones ni correlaciones (eso es el Analyst)
- No genera informes narrativos (eso es el Reporter)
- No hace multi-turno con el usuario (eso es el Orchestrator)

---

## Input / Output

**Input**: lista de `Event` (de `Environment.run()`) + prompt del Orchestrator.

Ejemplo de prompt: `"Observa esta simulacion de 100 pasos con 3 agentes buscando comida y reporta que paso."`

**Output**: JSON con esta estructura:

```json
{
  "summary": "Simulacion de 100 pasos con 3 agentes...",
  "trajectories": {
    "agent_0": {
      "steps_survived": 100,
      "resources_consumed": 23,
      "actions": {"move_up": 30, "move_down": 25, "eat": 23, "rest": 22}
    },
    "agent_1": {
      "steps_survived": 67,
      "resources_consumed": 8,
      "actions": {"move_up": 20, "move_left": 18, "eat": 8, "rest": 21}
    }
  },
  "episodes": [
    {
      "agent": "agent_0",
      "type": "foraging_success",
      "steps": [12, 15],
      "description": "Encontro comida tras 3 pasos de busqueda"
    },
    {
      "agent": "agent_1",
      "type": "starvation",
      "step": 67,
      "description": "Murio sin encontrar comida tras 20 pasos sin comer"
    }
  ]
}
```

---

## Tools (3)

### Tool schemas

```python
GET_SIMULATION_EVENTS_TOOL = {
    "name": "get_simulation_events",
    "description": "Get all events from the simulation. Returns raw events if <= 500, otherwise a summary with global metrics.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

GET_AGENT_TRAJECTORY_TOOL = {
    "name": "get_agent_trajectory",
    "description": "Get all events for a specific agent, including actions, rewards, and results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "The agent ID (e.g. 'agent_0')"},
        },
        "required": ["agent_id"],
    },
}

GET_AGENT_STATE_TOOL = {
    "name": "get_agent_state",
    "description": "Get the internal DecisionModel state of an agent at a specific step. Uses the trajectory data internally.",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "The agent ID"},
            "step": {"type": "integer", "description": "The simulation step number"},
        },
        "required": ["agent_id", "step"],
    },
}
```

### `get_simulation_events`

Devuelve todos los Events. Si hay >500, devuelve un resumen con metricas globales.

**Input**: ninguno (events inyectados via closure)

**Output**: JSON string con events o resumen

### `get_agent_trajectory(agent_id)`

Events filtrados de un agente concreto.

**Input**: `{"agent_id": "agent_0"}`

**Output**: JSON string con la lista de events del agente

### `get_agent_state(agent_id, step)`

Estado interno del DecisionModel en un step concreto. Extrae `outcome.model_state` del event correspondiente.

Nota: `model_state` es capturado por el Environment en cada `step()` via `DecisionModel.get_state()` y almacenado en `Event.outcome["model_state"]`. El Tracker no accede al modelo en vivo.

**Input**: `{"agent_id": "agent_0", "step": 42}`

**Output**: JSON string con el model_state

---

## Helpers

### `_event_to_dict`

Convierte un Event dataclass a un dict serializable:

```python
def _event_to_dict(event: Event) -> dict:
    return {
        "step": event.step,
        "agent_id": event.agent_id,
        "action": {"name": event.action.name, "params": event.action.params},
        "outcome": event.outcome,
    }
```

### `_summarize_events`

Resumen para simulaciones grandes (>500 events):

```python
def _summarize_events(events: list[Event]) -> dict:
    agents = set(e.agent_id for e in events)
    return {
        "total_events": len(events),
        "total_steps": max(e.step for e in events) + 1 if events else 0,
        "agents": list(agents),
        "events_per_agent": {a: sum(1 for e in events if e.agent_id == a) for a in agents},
        "action_counts": _count_actions(events),
    }

def _count_actions(events: list[Event]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.action.name] = counts.get(e.action.name, 0) + 1
    return counts
```

### `_strip_markdown_fences`

Extraer a `simlab/utils.py` (compartida con Architect):

```python
# simlab/utils.py
def strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
```

---

## System prompt

```
TRACKER_SYSTEM_PROMPT = """\
You are the Tracker agent for a simulation laboratory. You observe completed simulations \
and produce structured observation logs.

You have 3 tools to explore simulation data:
- get_simulation_events: overview of all events (start here)
- get_agent_trajectory: detailed events for one agent
- get_agent_state: internal model state at a specific step

## Process

1. Call get_simulation_events to understand the overall simulation
2. For each agent, call get_agent_trajectory to examine their behavior
3. Use get_agent_state to inspect internal state at interesting moments
4. Identify significant episodes (behavior changes, resource events, failures)
5. Return ONLY a valid JSON object — no markdown, no explanation

## Output schema

{
  "summary": "<1-2 sentence description of the simulation>",
  "trajectories": {
    "<agent_id>": {
      "steps_survived": int,
      "resources_consumed": int,
      "actions": {"<action_name>": count, ...}
    }
  },
  "episodes": [
    {
      "agent": "<agent_id>",
      "type": "<episode_type>",
      "steps": [start, end] or "step": int,
      "description": "<what happened and why it matters>"
    }
  ]
}

## Episode types (use these or create new descriptive ones)

- foraging_success: agent found and consumed a resource
- foraging_failure: agent searched but did not find resources
- starvation: agent state deteriorated critically
- exploration: agent moved to new areas
- exploitation: agent stayed near known resources
- state_change: significant change in internal model variables

## Rules

- Base episodes on DATA, not assumptions — cite specific steps and values
- When describing state changes, include the actual variable values from get_agent_state
- If the simulation is short (<50 steps), report all notable events
- If long (>200 steps), focus on the most significant episodes per agent
"""
```

---

## Implementacion

### Clase Tracker

```python
class Tracker:
    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(self, prompt: str, events: list[Event], *, max_iterations: int = 15) -> str:
        if not events:
            return json.dumps({"summary": "No events to observe.", "trajectories": {}, "episodes": []})
        tools, registry = _build_tools(events)
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=TRACKER_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": prompt}],
            registry=registry,
            max_iterations=max_iterations,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return strip_markdown_fences(text)
```

Nota: las tools se construyen per-run (no en `__init__`) porque dependen de los events de cada simulacion. Esto es intencionalmente diferente del Architect, donde las tools son stateless.

### Tool factories (patron de Pablo)

```python
def _build_tools(events: list[Event]) -> tuple[list[dict], Registry]:
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    async def get_simulation_events(params: dict) -> str:
        if len(events) > 500:
            return json.dumps(_summarize_events(events))
        return json.dumps([_event_to_dict(e) for e in events])

    async def get_agent_trajectory(params: dict) -> str:
        agent_id = params["agent_id"]
        agent_events = by_agent.get(agent_id, [])
        return json.dumps([_event_to_dict(e) for e in agent_events])

    async def get_agent_state(params: dict) -> str:
        agent_id = params["agent_id"]
        step = params["step"]
        agent_events = by_agent.get(agent_id, [])
        event = next((e for e in agent_events if e.step == step), None)
        if event is None:
            return json.dumps({"error": f"No event for {agent_id} at step {step}"})
        return json.dumps(event.outcome.get("model_state", {}))

    schemas = [GET_SIMULATION_EVENTS_TOOL, GET_AGENT_TRAJECTORY_TOOL, GET_AGENT_STATE_TOOL]
    registry = {
        "get_simulation_events": get_simulation_events,
        "get_agent_trajectory": get_agent_trajectory,
        "get_agent_state": get_agent_state,
    }
    return schemas, registry
```

---

## Ficheros a crear/modificar

| Fichero | Accion | Que contiene |
| --- | --- | --- |
| `simlab/tracker.py` | Crear | Clase Tracker, tool schemas, tool factories, system prompt, helpers |
| `simlab/utils.py` | Crear | `strip_markdown_fences` (compartida) |
| `simlab/architect.py` | Modificar | Importar `strip_markdown_fences` de utils |
| `tests/test_tracker.py` | Crear | Tests unitarios (tools con events mock) + integration tests |
| `tests/test_utils.py` | Crear | Tests para strip_markdown_fences |

---

## Flujo

```
Environment.run(steps) -> list[Event]
    |
    v
Tracker.run(prompt, events)
    |-- LLM recibe el prompt
    |-- llama get_simulation_events() -> resumen global
    |-- llama get_agent_trajectory("agent_0") -> detalle
    |-- llama get_agent_state("agent_0", 42) -> estado interno
    |-- genera JSON con trayectorias + episodios
    |
    v
JSON output (trayectorias + episodios etiquetados)
```

---

## Decisiones de diseno

| Decision | Valor | Razon |
| --- | --- | --- |
| Output del Tracker | JSON con trayectorias y episodios | Estructurado para que el Analyst lo procese |
| Tools | 3 tools (events, trajectory, state) | Permite al LLM explorar los datos de forma quirurgica |
| get_agent_state sobre get_agent_trajectory | Extrae model_state de los events existentes | DRY, no duplica datos |
| Resumen si >500 events | Devuelve metricas globales en vez de events crudos | Evita saturar el contexto del LLM |
| Factory pattern para tools | Closures inyectadas con los events | Patron de Pablo, testeable, sin estado global |
| Tools per-run, no en __init__ | Diferente al Architect intencionalmente | Tools dependen de events que cambian en cada simulacion |
| Clase con DI | client inyectado por constructor | Mismo patron que Architect |
| Empty events | Retorna JSON vacio inmediatamente | Evita llamar al LLM sin datos |
| strip_markdown_fences | Extraer a simlab/utils.py | Compartida entre Architect y Tracker |
| model_state | Capturado por Environment, no en vivo | El Tracker observa datos historicos, no el modelo en tiempo real |
