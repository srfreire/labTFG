# Phase 1: Context Retrieval

> Status: current | Created: 2026-04-17 | Last updated: 2026-04-17
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Hacer que los agentes de Phase 2 (Architect, Analyst, Reporter) puedan consultar el Knowledge Backbone de Pablo durante su razonamiento. Se expone una tool `retrieve_context` desde un wrapper limpio en `simlab/recall/`, accesible (a) al Orchestrator como tool LLM explícito y (b) a los tres agentes via inyección en sus system prompts. No es obligatoria para ningún agente — el LLM decide cuándo consultar.

## Requirements

### R1: Paquete `simlab/recall/`

- Crear `phase2-juan/simlab/recall/` con `__init__.py` exportando la API pública.
- Módulos iniciales: `retrieve.py` (wrapper + tool schema).
- Módulo simétrico a `simlab/knowledge/` (escritura): `recall` es el lado de lectura del Knowledge Backbone.
- Public API:
  ```python
  from simlab.recall import (
      RETRIEVE_CONTEXT_TOOL,    # dict con el tool schema Claude
      retrieve_context,          # async función (query, namespace=None, top_k=5, as_of=None) -> str
      build_retriever_from_settings,  # factory None-safe
  )
  ```

### R2: Wrapper `retrieve_context`

- Firma:
  ```python
  async def retrieve_context(
      *,
      query: str,
      namespace: str | None = None,  # "paradigm" | "formulation" | "model" | "simulation" | "meta"
      top_k: int = 5,
      as_of: str | None = None,       # ISO8601
  ) -> str:
      """Retrieve relevant knowledge from the backbone; returns markdown-formatted results."""
  ```
- Internamente llama a `decisionlab.knowledge.retrieval.tool.retrieve_knowledge` (el de Pazos), adaptando parámetros.
- **Pasa `stage=f"phase2-{agent_name}"`** (e.g. `"phase2-architect"`) a la tool de Pablo. Su código hace `_STAGE_DESCRIPTIONS.get(stage, f"working in the {stage} stage")` — el fallback genérico funciona con cualquier string, no hace falta PR.
- **Graceful degradation**: si `shared.vectors` / `shared.embeddings` son None (infra caída) o el flag `ENABLE_KNOWLEDGE_READ=false`, retorna string vacío `"## Retrieved Knowledge (0 results)\n\nNo results found."` — igual que cuando no hay matches.
- **Nunca raise**: cualquier excepción de la tool de Pablo se captura, loguea y devuelve el mismo string "0 results" con `skipped_reason` solo en logs.

### R3: Tool schema para el Orchestrator

- Expone `RETRIEVE_CONTEXT_TOOL` siguiendo el patrón Claude-tool existente en Phase 2:
  ```python
  RETRIEVE_CONTEXT_TOOL = {
      "name": "retrieve_context",
      "description": (
          "Query the Knowledge Backbone for scientific facts, papers, postulates, "
          "and patterns from past pipeline runs. Use before generating specs "
          "(Architect), comparing against postulates (Analyst), or citing "
          "references (Reporter)."
      ),
      "input_schema": {
          "type": "object",
          "properties": {
              "query": {"type": "string", "description": "Natural language query"},
              "namespace": {
                  "type": "string",
                  "enum": ["paradigm", "formulation", "model", "simulation", "meta"],
                  "description": "Optional namespace filter",
              },
              "top_k": {"type": "integer", "default": 5},
          },
          "required": ["query"],
      },
  }
  ```
- Registrado en el `Orchestrator._build_tools()` junto a las otras tools (`create_environment`, `run_simulation`, etc.).
- El handler del Orchestrator llama al wrapper `retrieve_context(**params)` y devuelve el string al loop de tool_use.

### R4: Integración con Architect

- Añadir sección al system prompt del Architect instruyendo que si el input menciona un paradigma científico, llame a `retrieve_context(query=..., namespace="paradigm")` antes de generar el spec.
- El Architect se inicializa con `tools=[EXISTING_TOOLS, RETRIEVE_CONTEXT_TOOL]` solo si `ENABLE_KNOWLEDGE_READ` está activado. Si el flag está off, `tools` se mantiene como estaba y el prompt tampoco menciona la tool.
- La integración es **opcional**: el Architect puede decidir no llamarla si el input no lo requiere.

### R5: Integración con Analyst

- Misma estrategia: prompt instruye consultar postulates conocidos antes de interpretar patrones.
- Query típica: `retrieve_context(query=f"postulates and predictions for paradigm {paradigm}", namespace="paradigm")`.
- Si el retrieval retorna resultados, el Analyst debe **citar** el Postulate concreto al contrastarlo con una observación ("Observación X es consistente con Postulate P3: dopamine mediates wanting").

### R6: Integración con Reporter

- Prompt instruye enriquecer la sección "References" del PDF con papers reales del KG.
- Query: `retrieve_context(query=f"papers and authors for paradigm {paradigm}", top_k=10)`.
- Reporter formatea las referencias en LaTeX usando los campos `paper_title`, `year`, `doi` del metadata retornado.
- Si el retrieval no devuelve resultados, el Reporter genera referencias genéricas como hasta ahora (backward compat).

### R7: Flag `ENABLE_KNOWLEDGE_READ`

- Añadir a `shared.settings.Settings`: `ENABLE_KNOWLEDGE_READ: bool = False`, parseo permisivo igual que `ENABLE_KNOWLEDGE_WRITE`.
- **No hay singleton** en `shared.__init__` para Phase 1 — las llamadas son stateless, el wrapper construye lo que necesita.
- Cuando `ENABLE_KNOWLEDGE_READ=False`:
  - El Orchestrator **no registra** `RETRIEVE_CONTEXT_TOOL` en su tool registry.
  - Architect/Analyst/Reporter **no ven** la tool ni la mención del KG en sus prompts.
  - Comportamiento equivalente al estado actual de main.

### R8: Tests

- **Unit tests** en `phase2-juan/tests/recall/test_retrieve.py`:
  - Wrapper traduce parámetros correctamente (Pazos recibe los valores esperados).
  - `retrieve_context` con `ENABLE_KNOWLEDGE_READ=False` retorna string vacío sin llamar a Pazos.
  - Graceful degradation: si la tool de Pazos raise, el wrapper captura y devuelve 0-results.
  - Tool schema es JSON-serializable.
- **Hook tests** en `phase2-juan/tests/recall/test_agent_wiring.py`:
  - Con flag ON: Architect/Analyst/Reporter construidos reciben el tool en su lista.
  - Con flag OFF: la tool no aparece.
- **Integration test (opt-in)** en `tests/integration/test_sim_recall_roundtrip.py`:
  - Escribe vía `TrackerMemoryWriter` (simulando un run Phase 2).
  - Llama `retrieve_context(query=..., namespace="simulation")` y verifica que encuentra su propia escritura.
  - Demuestra el loop sim-memory → sim-recall end-to-end.

## Acceptance Criteria

- [ ] AC1: `from simlab.recall import retrieve_context, RETRIEVE_CONTEXT_TOOL, build_retriever_from_settings` funciona.
- [ ] AC2: Con `ENABLE_KNOWLEDGE_READ=false` (default), `retrieve_context` retorna inmediatamente con 0 results sin llamar a Pablo ni tocar infra.
- [ ] AC3: Con flag ON + infra up, `retrieve_context(query="test")` llama a `decisionlab.knowledge.retrieval.tool.retrieve_knowledge` con los parámetros correctos y devuelve el markdown formateado.
- [ ] AC4: Cualquier excepción lanzada por la tool de Pablo es capturada por el wrapper; el Orchestrator nunca ve la excepción.
- [ ] AC5: El Orchestrator con flag ON incluye `RETRIEVE_CONTEXT_TOOL` en su lista de tools; con flag OFF, no.
- [ ] AC6: Architect/Analyst/Reporter con flag ON reciben la tool y su system prompt menciona cuándo usarla; con flag OFF no cambia nada.
- [ ] AC7: Los 115 tests actuales de phase2 + 27 de shared siguen verdes.
- [ ] AC8: El integration test demuestra el loop sim-memory write → sim-recall read.

## Technical Notes

- **Pablo's retrieve_knowledge signature**: revisar [phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py](phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py). La factory `create_retrieve_knowledge` construye un handler cerrado sobre clientes — hay que ver si podemos invocarla directamente o si hace falta reconstruir los clientes. Mejor reusar `shared.vectors` / `shared.embeddings` / `shared.kg` si están arriba.
- **Stage parameter**: Pablo hardcodea stages en `_STAGE_DESCRIPTIONS` (researcher/formalizer/reasoner/builder). Decidir entre (a) añadir `phase2` a su map (PR a Pazos), (b) pasar uno neutral como `builder` como compromiso, (c) no pasar stage y ver si es opcional. Inspección del código dirá.
- **Prompts afectados**:
  - `phase2-juan/simlab/architect.py:ARCHITECT_SYSTEM_PROMPT` (si existe así; hay que localizar).
  - `phase2-juan/simlab/analyst.py:ANALYST_SYSTEM_PROMPT`.
  - `phase2-juan/simlab/reporter.py:REPORTER_SYSTEM_PROMPT`.
- **Archivos afectados** (estimación):
  - `phase2-juan/simlab/recall/__init__.py` — nuevo.
  - `phase2-juan/simlab/recall/retrieve.py` — nuevo.
  - `phase2-juan/simlab/architect.py` — prompt + tool injection.
  - `phase2-juan/simlab/analyst.py` — idem.
  - `phase2-juan/simlab/reporter.py` — idem.
  - `phase2-juan/simlab/orchestrator.py` — registrar RETRIEVE_CONTEXT_TOOL en `_build_tools`.
  - `shared/shared/settings.py` — flag.
  - Tests nuevos.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Wrapper vs llamada directa | Wrapper `retrieve_context` en `simlab/recall/` | Decoupling; si Pablo cambia API no rompe Phase 2. Facilita mocking en tests. |
| Exposure | Tool del Orchestrator + inyección en agentes | Claude del Orchestrator decide cuándo preguntas del user, agentes deciden cuándo razonando. |
| Obligatorio vs opcional | Opcional via prompt | LLM-native; no forzamos llamadas que pueden ser redundantes. |
| Flag scope | Un solo flag `ENABLE_KNOWLEDGE_READ` para toda la feature | Simplicidad. Si después se quiere granularidad por agente, issue aparte. |
| Singleton en `shared` | No (wrapper stateless) | Pablo ya maneja conexiones reutilizando `shared.vectors`/`embeddings`; no añadimos otro singleton. |
| Query defaults por agente | Definidos en el system prompt | Más flexible que hardcode; el LLM adapta la query al contexto de la conversación. |
