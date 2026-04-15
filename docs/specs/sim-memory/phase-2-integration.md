# Phase 2: Integration

> Status: current | Created: 2026-04-15 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md) | [phase-1-core-writer.md](phase-1-core-writer.md)

## Objective

Integrar el `TrackerMemoryWriter` construido en Phase 1 con el flujo real de Phase 2. Añadir el flag `ENABLE_KNOWLEDGE_WRITE`, inicializar el writer como singleton en `shared` siguiendo el patrón existente (`shared.db`, `shared.storage`, `shared.vectors`), y llamarlo desde el `Orchestrator.observe_simulation()` justo después de la persistencia en S3/DB.

## Requirements

### R1: Flag y settings

- Añadir campo `ENABLE_KNOWLEDGE_WRITE: bool = False` a `shared.settings.Settings` con default False.
- Parseo permisivo en `load_settings`: el valor viene como env var string, convertirlo con `{"1", "true", "yes", "on"}` → True (case-insensitive). Cualquier otro string (incluido "false", "0", vacío) → False.
- Añadir la misma línea de ejemplo a `.env.example` con un comentario:
  ```
  # Knowledge Backbone — Phase 2 simulation observations
  ENABLE_KNOWLEDGE_WRITE=false
  ```
- No se añaden flags separados para desactivar Qdrant/Voyage — el factory `build_writer_from_settings` ya cubre ese caso (retorna None si faltan keys).

### R2: Writer singleton en `shared.__init__`

- Extender `shared/shared/__init__.py` siguiendo el patrón que ya usa para `db`, `storage`, `kg`, `vectors`, `embeddings`:
  - Añadir `sim_memory_writer: TrackerMemoryWriter | None = None` como módulo-level.
  - En la función lifecycle de init (la que ya construye `db`/`vectors`/`embeddings`), tras construir esos servicios, si `settings.ENABLE_KNOWLEDGE_WRITE=True` **instanciar `TrackerMemoryWriter` directamente** reutilizando las instancias ya conectadas:
    ```python
    if settings.ENABLE_KNOWLEDGE_WRITE:
        if vectors is None or embeddings is None or db is None:
            logger.warning(
                "ENABLE_KNOWLEDGE_WRITE=true but infra missing — "
                "Qdrant/Voyage/Postgres not initialised; knowledge writes disabled",
            )
        else:
            sim_memory_writer = TrackerMemoryWriter(
                vector_store=vectors,
                embedding_service=embeddings,
                db=db,
            )
            logger.info("Knowledge writes enabled (namespace=simulation)")
    ```
  - Si el flag es False, dejar `sim_memory_writer = None` (sin log — es el caso común).
- **No se modifica `build_writer_from_settings`**: sigue siendo el entry point correcto para tests aislados y el integration test de P1-004 que sí necesitan abrir sus propias conexiones. Los tests de P1-001 quedan intactos.

### R3: Invocación desde el Orchestrator

- En `phase2-juan/simlab/orchestrator.py`, función `observe_simulation`:
  - **Después** de guardar el tracker_output en S3 y actualizar `DBExperiment.status="tracked"`.
  - Leer `shared.sim_memory_writer`. Si es `None`, salir silenciosamente (no log — el flag OFF es el caso común).
  - Construir `SimulationContext` usando datos del `state`:
    - `phase2_experiment_id` = `state["experiment_id"]`.
    - `environment` = `f"grid_{state['spec']['grid_width']}x{state['spec']['grid_height']}"` o fallback `"unknown"` si falta el spec.
    - `steps` = `len(state["replay"]["frames"])` si existe, si no `0`.
    - `seed` = el seed del último `run_simulation` — hay que persistirlo en `state["seed"]` (no lo hace ahora; ver R4).
    - `agent_to_model` = diccionario construido durante `run_simulation` (ver R4).
  - Llamar `await shared.sim_memory_writer.write(tracker_output_json, context)`.
  - Loguear `INFO` con el `WriteResult` (contadores + duration).
  - Cualquier excepción inesperada (el writer promete no propagar, pero defensivo): `try/except` con `logger.exception` para no romper el `observe_simulation`.

### R4: Construcción de `agent_to_model` en `run_simulation`

- En `run_simulation` de `orchestrator.py`, durante el bucle que añade agentes al environment (línea ~530), acumular el mapping:
  ```python
  agent_to_model: dict[str, dict] = {}
  # dentro del for sobre model_ids:
  for i in range(num_agents):
      # ... crear agente ...
      agent_to_model[agent_id] = {
          "model_id": info.id,
          "class_name": info.class_name,
          "paradigm": info.paradigm,
          "formulation": info.formulation,
          "phase1_run_id": info.run_id,
      }
  ```
- Guardar en `state["agent_to_model"] = agent_to_model` y `state["seed"] = params.get("seed")`.
- En `observe_simulation`, convertir el dict de dicts a `dict[str, simlab.knowledge.ModelInfo]` antes de construir el `SimulationContext`.
- Si `state["agent_to_model"]` no existe (simulación pre-update o sin modelos), `agent_to_model={}`; el writer filtrará por agent desconocido y escribirá solo el summary (o nada si también filtra el summary por falta de `_distinct_models`).

### R5: Tests

- **Unit test del Orchestrator (mocked)**: test nuevo en `phase2-juan/tests/test_orchestrator_knowledge.py`:
  - Parche `shared.sim_memory_writer` con un AsyncMock.
  - Ejecuta el flow: `create_environment` → `run_simulation` → `observe_simulation`.
  - Verifica que el writer se invoca una vez con un `SimulationContext` que contiene el experiment_id, environment `"grid_WxH"` correcto y `agent_to_model` con las entradas esperadas.
  - Un test con `shared.sim_memory_writer = None` verifica que `observe_simulation` funciona sin llamar al writer.
- **Unit test de `shared.init_services`**: añadir a `shared/tests/test_lifecycle.py` (o crear nuevo) un test que verifique:
  - Con flag ON + keys válidas + mocks de connect → `shared.sim_memory_writer` es un `TrackerMemoryWriter`.
  - Con flag OFF → `shared.sim_memory_writer` es `None`.
  - Con flag ON + keys vacías → `shared.sim_memory_writer` es `None` + log warning.
- **Unit test del parsing del flag**: test pequeño que verifique `"true"`, `"1"`, `"on"`, `"yes"` → True; `"false"`, `"0"`, `""`, `"xyz"` → False.
- **Tests existentes de P1 siguen verdes**: regression gate.

### R6: End-to-end docker-compose test (manual / opt-in)

- No se añade un test automatizado nuevo (el de Phase 1 ya cubre la escritura real contra infra). En su lugar, documentar en `docs/specs/sim-memory/README.md` (o al final del phase-2 spec) el procedimiento manual:
  1. `docker compose up -d` con Postgres/Qdrant.
  2. Alembic migrations aplicadas.
  3. `.env` con `VOYAGE_API_KEY`, `ZEROENTROPY_API_KEY`, `ENABLE_KNOWLEDGE_WRITE=true`.
  4. `cd phase2-juan && uv run simlab` → correr una simulación completa.
  5. Verificación SQL: `SELECT count(*) FROM memories WHERE namespace='simulation'` debe aumentar.
  6. Verificación Qdrant: `curl` al endpoint de points en `memories_dense` con filtro por `phase2_experiment_id`.
- Opcional pero recomendado: añadir el integration test de Phase 1 (`tests/knowledge/test_integration.py`) a la lista de comandos esperados para la release.

## Acceptance Criteria

- [ ] AC1: Correr Phase 2 con `ENABLE_KNOWLEDGE_WRITE=false` (default) no produce escrituras al KG, sin cambios de comportamiento observables frente a main.
- [ ] AC2: Con flag ON + infra arriba + keys, tras una simulación de 1 modelo/2 agentes/200 pasos, la tabla `memories` contiene ≥3 filas con `namespace='simulation'` (1 summary + 2 trajectories + N episodes).
- [ ] AC3: Los tests del orchestrator pasan: escrituras suceden cuando el writer está presente, y `observe_simulation` no rompe si el writer es `None`.
- [ ] AC4: Los 111 tests unitarios previos siguen verdes.
- [ ] AC5: `shared.sim_memory_writer` se inicializa solo una vez por proceso y se reutilizan las conexiones existentes de Postgres/Qdrant/Voyage.
- [ ] AC6: El parsing del flag acepta formas comunes (`true`/`1`/`yes`/`on`) sin ser sensible a mayúsculas.
- [ ] AC7: Un fallo inesperado del writer (bug, infra caída post-init) se loguea vía `logger.exception` y no aborta `observe_simulation`.

## Technical Notes

- **Patrón a seguir**: lifecycle de servicios en [shared/shared/__init__.py](shared/shared/__init__.py). Ya tiene `db`, `storage`, `kg`, `vectors`, `embeddings` como module-level vars inicializados en una función lifecycle.
- **Conversión `simlab.model_loader.ModelInfo` → `simlab.knowledge.ModelInfo`**: hacer un helper privado en `orchestrator.py` o en `simlab/knowledge/__init__.py`. Los tipos son diferentes (el del model_loader tiene `description`, `s3_model_key`). La traducción es trivial (`id` → `model_id`, `run_id` → `phase1_run_id`).
- **Archivos afectados**:
  - `shared/shared/settings.py` — añadir campo + parseo.
  - `shared/shared/__init__.py` — añadir singleton + init.
  - `phase2-juan/simlab/orchestrator.py` — agent_to_model en run_simulation, llamada en observe_simulation.
  - `.env.example` — flag documentado.
  - `phase2-juan/tests/test_orchestrator_knowledge.py` — nuevo.
  - `shared/tests/test_lifecycle.py` — ampliado.
  - `shared/tests/test_settings.py` — parsing del flag.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Lugar de invocación | Post-S3/DB persist dentro de `observe_simulation` | La persistencia cruda del tracker_output es la fuente de verdad; el KG es derivado. Si el writer falla, no se pierde data. |
| Lifecycle | Singleton en `shared` | Patrón consistente con `db`/`vectors`/`embeddings`. Evita construir/destruir por simulación. |
| Connection sharing | Instanciar `TrackerMemoryWriter` directamente en `shared.__init__` reutilizando `shared.db/vectors/embeddings` | Evita conexiones duplicadas sin tocar el factory de P1-001. Más simple (5 líneas vs refactor). |
| Flag parsing | `{"1","true","yes","on"}` case-insensitive | UX: aceptar formas comunes sin ser estricto. |
| e2e test | Manual documentado + integration test de P1-004 | No duplicamos infra setup. El manual run se hace una vez por release; el integration test de P1 ya ejercita el writer contra infra real. |
| Conversión entre ModelInfos | Translation en orchestrator | Mantiene la separación de layers: `simlab.knowledge` no depende de `simlab.model_loader`. |
| `environment` string format | `f"grid_{W}x{H}"` | Descriptivo y joineable. No intentamos reconstruir el nombre del spec (no lo tiene). |
| Fallback sin agent_to_model | Writer filtra agents desconocidos, summary se emite sin problema | Graceful degradation si sims antiguas no tienen el state enriquecido. |
