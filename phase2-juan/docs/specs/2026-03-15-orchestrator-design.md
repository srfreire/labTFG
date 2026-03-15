# Orchestrator Agent — Design Spec

## Resumen

El Orchestrator es un agente LLM conversacional que coordina los 4 agentes (Architect, Tracker, Analyst, Reporter) segun lo que pida el usuario. Puede ejecutar el pipeline completo con un solo prompt o pasos individuales en modo conversacional.

---

## Responsabilidades

- Interpretar peticiones del usuario en lenguaje natural
- Decidir que agentes invocar y en que orden
- Mantener estado entre llamadas (spec, events, tracker output, analyst output)
- Devolver resultados conversacionales al usuario
- Ejecutar pipeline completo si el usuario lo pide de golpe

## No hace

- No implementa DecisionModels (vienen de la Fase 1 / Pablo)
- No tiene logica de pipeline hardcodeada (el LLM decide el flujo)
- No accede a datos de simulacion directamente (delega en Tracker/Analyst)

---

## Input / Output

**Input**: Prompt del usuario en lenguaje natural.

Ejemplos:
- Pipeline completo: `"Simula 2 organismos buscando comida en un grid 10x10 durante 50 pasos y genera un informe"`
- Paso a paso: `"Crea un environment de 15x15 con comida y agua"`
- Seguimiento: `"Ahora corre la simulacion 30 pasos"`
- Analisis: `"Que patrones encontraste?"`

**Output**: Texto conversacional + resultados de los agentes invocados.

---

## Tools (5)

### `create_environment`

Llama al Architect para generar un JSON spec.

```python
CREATE_ENVIRONMENT_TOOL = {
    "name": "create_environment",
    "description": "Create a simulation environment from a natural language description. Returns a JSON spec.",
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Description of the environment to create"},
        },
        "required": ["description"],
    },
}
```

### `run_simulation`

Construye el Environment desde la spec almacenada, instancia agentes con los DecisionModels disponibles, y ejecuta la simulacion.

```python
RUN_SIMULATION_TOOL = {
    "name": "run_simulation",
    "description": "Run a simulation with the current environment spec. Requires create_environment first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "num_agents": {"type": "integer", "description": "Number of agents to place in the simulation"},
            "steps": {"type": "integer", "description": "Number of simulation steps to run"},
            "seed": {"type": "integer", "description": "Random seed for reproducibility (optional)"},
        },
        "required": ["num_agents", "steps"],
    },
}
```

### `observe_simulation`

Llama al Tracker con los events almacenados.

```python
OBSERVE_SIMULATION_TOOL = {
    "name": "observe_simulation",
    "description": "Observe the simulation results using the Tracker agent. Requires run_simulation first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to focus on when observing (optional)"},
        },
    },
}
```

### `analyze_results`

Llama al Analyst con el tracker output y los events.

```python
ANALYZE_RESULTS_TOOL = {
    "name": "analyze_results",
    "description": "Analyze simulation results using the Analyst agent. Requires observe_simulation first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to focus on in the analysis (optional)"},
        },
    },
}
```

### `generate_report`

Llama al Reporter con todo el contexto acumulado.

```python
GENERATE_REPORT_TOOL = {
    "name": "generate_report",
    "description": "Generate a PDF report with all results. Requires analyze_results first.",
    "input_schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "What to emphasize in the report (optional)"},
        },
    },
}
```

---

## Estado interno

El Orchestrator mantiene estado entre tool calls via closures. Cada tool almacena su resultado para que la siguiente pueda acceder:

```python
state = {
    "spec": None,        # JSON spec del Architect
    "events": None,      # list[Event] de la simulacion
    "tracker_output": None,  # JSON del Tracker
    "analyst_output": None,  # JSON del Analyst
    "pdf_path": None,    # Path del PDF generado
}
```

Las tools validan que el estado previo existe (ej: `run_simulation` requiere `state["spec"]`).

---

## Implementacion

### Clase Orchestrator

```python
class Orchestrator:
    def __init__(self, *, client, decision_models=None, research_dir, output_dir, model=DEFAULT_MODEL):
        self.client = client
        self.decision_models = decision_models or []
        self.research_dir = research_dir
        self.output_dir = output_dir
        self.model = model
        self._state = {}
        self._messages = []

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the response."""
        self._messages.append({"role": "user", "content": user_message})
        tools, registry = self._build_tools()
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            tools=tools,
            messages=self._messages,
            registry=registry,
            max_iterations=25,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        self._messages.append({"role": "assistant", "content": response.content})
        return text
```

Nota: `_messages` se acumula entre llamadas a `chat()` — esto es lo que habilita el modo conversacional. El Orchestrator recuerda lo que ya se hizo.

### Tool factories

```python
def _build_tools(self):
    state = self._state

    async def create_environment(params):
        arch = Architect(client=self.client)
        spec_json = await arch.run(params["description"])
        state["spec"] = json.loads(spec_json)
        return spec_json

    async def run_simulation(params):
        if not state.get("spec"):
            return json.dumps({"error": "No environment created. Call create_environment first."})
        env = spec_to_environment(state["spec"], seed=params.get("seed"))
        # Instantiate agents with available DecisionModels
        for i in range(params["num_agents"]):
            model = self.decision_models[i % len(self.decision_models)] if self.decision_models else DummyModel()
            env.add_agent(Agent(id=f"agent_{i}", position=Position(...), decision_model=model))
        events = env.run(steps=params["steps"])
        state["events"] = events
        return json.dumps({"agents": params["num_agents"], "steps": params["steps"], "total_events": len(events)})

    async def observe_simulation(params):
        if not state.get("events"):
            return json.dumps({"error": "No simulation run. Call run_simulation first."})
        tracker = Tracker(client=self.client)
        focus = params.get("focus", "Observa la simulacion y reporta que paso.")
        result = await tracker.run(focus, state["events"])
        state["tracker_output"] = result
        return result

    async def analyze_results(params):
        if not state.get("tracker_output"):
            return json.dumps({"error": "No observations. Call observe_simulation first."})
        analyst = Analyst(client=self.client)
        focus = params.get("focus", "Analiza patrones y compara los agentes.")
        result = await analyst.run(focus, state["tracker_output"], state["events"])
        state["analyst_output"] = result
        return result

    async def generate_report(params):
        if not state.get("analyst_output"):
            return json.dumps({"error": "No analysis. Call analyze_results first."})
        reporter = Reporter(client=self.client)
        focus = params.get("focus", "Genera un informe completo.")
        result = await reporter.run(
            focus, state["tracker_output"], state["analyst_output"],
            research_dir=self.research_dir, output_dir=self.output_dir,
        )
        state["pdf_path"] = str(self.output_dir / "report.pdf")
        return result

    # return schemas + registry
```

### Modelo

`anthropic/claude-sonnet-4-5` — necesita razonar sobre que hacer y encadenar agentes.

---

## Ficheros a crear

| Fichero | Accion | Que contiene |
| --- | --- | --- |
| `simlab/orchestrator.py` | Crear | Clase Orchestrator, tools, prompt |
| `tests/test_orchestrator.py` | Crear | Integration tests |

---

## Flujo

```
Usuario: "Simula 2 organismos en un grid 10x10 y dame un informe"
    |
    v
Orchestrator (LLM razona)
    |-- "necesito crear environment" → create_environment
    |-- "ahora simular" → run_simulation
    |-- "observar que paso" → observe_simulation
    |-- "analizar patrones" → analyze_results
    |-- "generar PDF" → generate_report
    |-- responde al usuario con resumen + path PDF
    |
    v
Usuario: "Que patron fue el mas interesante?"
    |-- Orchestrator recuerda el contexto, responde usando analyst_output
```

---

## Decisiones de diseno

| Decision | Valor | Razon |
| --- | --- | --- |
| Conversacional | Si, mantiene _messages entre chat() | El usuario puede iterar |
| Pipeline completo | El LLM decide llamar las 5 tools en secuencia | Sin logica hardcodeada |
| Estado | Dict mutable accesible via closures | Simple, sin persistencia |
| DecisionModels | Inyectados en constructor | Vienen de Pablo, el Orchestrator no los crea |
| Modelo | Sonnet 4.5 | Necesita razonar sobre flujo |
| DummyModel fallback | Si no hay models inyectados, usa un dummy | Permite testear sin Fase 1 |
