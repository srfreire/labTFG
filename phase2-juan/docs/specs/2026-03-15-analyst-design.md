# Analyst Agent — Design Spec

## Resumen

El Analyst es un agente LLM que recibe el output del Tracker (trayectorias + episodios) como contexto, tiene acceso a los Events crudos via tools, y produce un analisis estructurado en JSON con patrones, comparaciones y metricas.

---

## Responsabilidades

- Identificar patrones de comportamiento en los datos de simulacion
- Comparar rendimiento entre agentes
- Calcular metricas relevantes
- Devolver un JSON estructurado procesable por el Reporter

## No hace

- No observa simulaciones (eso ya lo hizo el Tracker)
- No genera informes narrativos (eso es el Reporter)
- No ejecuta simulaciones

---

## Input / Output

**Input**:
- JSON del Tracker (trayectorias + episodios) — inyectado en el prompt del usuario
- Events crudos — accesibles via las 3 tools del Tracker
- Prompt del Orchestrator (ej: "Analiza los datos y encuentra patrones")

**Output**: JSON con esta estructura:

```json
{
  "patterns": [
    {
      "id": "P1",
      "type": "behavioral",
      "agents": ["agent_0"],
      "description": "Intervalos regulares de foraging cada ~10 pasos",
      "evidence": "Consumos en steps 1, 10, 20 — intervalos de 9-10 pasos"
    },
    {
      "id": "P2",
      "type": "strategic",
      "agents": ["agent_0", "agent_1"],
      "description": "Ambos agentes priorizan movimiento sobre descanso",
      "evidence": "move actions > 70% del total en ambos agentes"
    }
  ],
  "comparisons": [
    {
      "agents": ["agent_0", "agent_1"],
      "metric": "foraging_efficiency",
      "values": {"agent_0": 0.3, "agent_1": 0.1},
      "insight": "agent_0 es 3x mas eficiente buscando comida"
    }
  ],
  "metrics": {
    "agent_0": {"survival_rate": 1.0, "avg_hunger": 4.5, "resources_per_step": 0.1},
    "agent_1": {"survival_rate": 1.0, "avg_hunger": 8.2, "resources_per_step": 0.1}
  }
}
```

---

## Tools

Reutiliza las mismas 3 tools del Tracker via `_build_tools` de `tracker.py`:

- `get_simulation_events` — overview de todos los events
- `get_agent_trajectory(agent_id)` — events de un agente
- `get_agent_state(agent_id, step)` — estado interno en un step

---

## Implementacion

### Clase Analyst

```python
class Analyst:
    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(self, prompt: str, tracker_output: str, events: list[Event], *, max_iterations: int = 15) -> str:
        tools, registry = _build_tools(events)  # reutiliza tracker._build_tools
        user_message = f"{prompt}\n\n## Tracker observation log\n\n{tracker_output}"
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=ANALYST_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            registry=registry,
            max_iterations=max_iterations,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return strip_markdown_fences(text)
```

Nota: `_build_tools` se importa desde `tracker.py` — no se duplica.

### System prompt

```
ANALYST_SYSTEM_PROMPT = """\
You are the Analyst agent for a simulation laboratory. You receive observation logs \
from the Tracker and raw simulation data, then identify patterns, compare agents, \
and compute metrics.

You have 3 tools to explore raw simulation data:
- get_simulation_events: overview of all events
- get_agent_trajectory: detailed events for one agent
- get_agent_state: internal model state at a specific step

The Tracker's observation log is provided in the user message. Use it as your starting \
point — the Tracker already identified trajectories and episodes. Your job is to go \
deeper: find patterns, compare agents, and quantify behavior.

## Process

1. Read the Tracker log to understand what happened
2. Use tools to verify claims and gather additional data
3. Identify behavioral patterns (repeated behaviors, strategies, transitions)
4. Compare agents against each other (efficiency, strategy, outcomes)
5. Compute concrete metrics per agent
6. Return ONLY a valid JSON object — no markdown, no explanation

## Output schema

{
  "patterns": [
    {
      "id": "P1",
      "type": "<behavioral|strategic|temporal|resource>",
      "agents": ["<agent_ids involved>"],
      "description": "<what the pattern is>",
      "evidence": "<specific steps, values, or data supporting this>"
    }
  ],
  "comparisons": [
    {
      "agents": ["<agent_a>", "<agent_b>"],
      "metric": "<what is being compared>",
      "values": {"<agent_a>": number, "<agent_b>": number},
      "insight": "<what the comparison reveals>"
    }
  ],
  "metrics": {
    "<agent_id>": {
      "survival_rate": float,
      "<other relevant metrics>": value
    }
  }
}

## Rules

- Every pattern MUST cite specific evidence (steps, values, counts)
- Comparisons must include concrete numerical values
- Metrics should be normalized where possible (per-step rates, percentages)
- If the Tracker missed something interesting in the raw data, flag it as a new pattern
- Do NOT repeat the Tracker's episodes — synthesize higher-level insights
"""
```

### Modelo

Mismo default que el Tracker (`anthropic/claude-sonnet-4-5`).

---

## Ficheros a crear/modificar

| Fichero | Accion | Que contiene |
| --- | --- | --- |
| `simlab/analyst.py` | Crear | Clase Analyst, system prompt. Importa `_build_tools` de tracker |
| `tests/test_analyst.py` | Crear | Integration test |

No se necesitan tests unitarios nuevos — las tools ya estan testeadas en `test_tracker.py`.

---

## Flujo

```
Tracker.run(prompt, events) -> tracker_output (JSON)
    |
    v
Analyst.run(prompt, tracker_output, events)
    |-- LLM lee el tracker_output como contexto
    |-- opcionalmente llama tools para verificar/profundizar
    |-- genera JSON con patterns + comparisons + metrics
    |
    v
JSON output (patrones + comparaciones + metricas)
```

---

## Decisiones de diseno

| Decision | Valor | Razon |
| --- | --- | --- |
| Tools | Reutiliza las 3 del Tracker | YAGNI, los datos son los mismos |
| Input del Tracker | Inyectado en el prompt del usuario | Simple, el LLM lo lee como contexto |
| Output | JSON estructurado | Procesable por el Reporter |
| _build_tools | Importado de tracker.py, no duplicado | DRY |
| Sin tools propias | El LLM puede comparar leyendo datos | No justifica la complejidad extra |
