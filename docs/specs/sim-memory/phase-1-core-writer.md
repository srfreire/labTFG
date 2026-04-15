# Phase 1: Core Writer

> Status: current | Created: 2026-04-15 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Construir el componente `TrackerMemoryWriter` como clase standalone en `phase2-juan/simlab/knowledge/`, con todos sus helpers y tests unitarios, sin tocar el orchestrator ni introducir dependencias nuevas. Al terminar esta fase, el writer es invocable pero nadie lo invoca todavía.

## Requirements

### R1: Módulo y estructura

- Crear carpeta `phase2-juan/simlab/knowledge/` con `__init__.py`.
- Módulo principal: `phase2-juan/simlab/knowledge/writer.py`.
- Posibles sub-módulos internos si clarifica (p.ej. `facts.py` para reglas de conversión).
- Export público en `__init__.py`: `from simlab.knowledge.writer import TrackerMemoryWriter, WriteResult`.

### R2: Data classes

En `writer.py` (o un `models.py` interno):

```python
@dataclass(frozen=True)
class ModelInfo:
    """Información del modelo que rige a un agente."""
    model_id: str              # UUID Model row
    class_name: str            # e.g. "HomeostaticDriveReductionRL"
    paradigm: str              # e.g. "homeostatic-regulation"
    formulation: str           # e.g. "drive-reduction-rl"
    phase1_run_id: str | None  # UUID del run de Phase 1 que produjo el modelo

@dataclass(frozen=True)
class SimulationContext:
    """Contexto de la simulación para enriquecer memorias."""
    phase2_experiment_id: str
    environment: str           # e.g. "grid_10x10" — derivado del spec
    steps: int
    seed: int | None
    agent_to_model: dict[str, ModelInfo]  # "agent_0" → ModelInfo

@dataclass(frozen=True)
class WriteResult:
    summaries_written: int
    trajectories_written: int
    episodes_written: int
    episodes_filtered: int     # cuántos se descartaron por tipo
    duration_ms: int
    skipped_reason: str | None # None si se escribió, texto si se saltó todo
```

### R3: Clase `TrackerMemoryWriter`

Firma exacta:

```python
class TrackerMemoryWriter:
    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        db: DatabaseService,
    ) -> None: ...

    async def write(
        self,
        tracker_output: str,        # JSON string producido por el Tracker
        context: SimulationContext,
    ) -> WriteResult: ...
```

**Comportamiento de `write`**:

1. Parsea `tracker_output` como JSON. Si falla, retorna `WriteResult(skipped_reason="invalid_json", ...)`.
2. Si el JSON no tiene `summary` ni `trajectories` ni `episodes`, retorna con `skipped_reason="empty_tracker_output"`.
3. Llama a `_build_facts(parsed_json, context)` → lista `[(fact_text, importance, memory_type, metadata), ...]`.
4. Si la lista está vacía tras filtrado, retorna con `skipped_reason="no_relevant_content"`.
5. Embebe todas las frases en **un único batch** con `embedding_service.embed_texts(facts)` (auto-batching interno a 128/call — nuestros 5-20 facts típicos caben en 1 API call).
6. Tokeniza cada frase a sparse con el tokenizer reutilizado (ver R5).
7. Por cada fact: genera UUID, crea fila en Postgres (`create_memory`), upsert en Qdrant dense + sparse con mismo UUID y payload `{memory_id, namespace, ...metadata}`.
8. Retorna `WriteResult` con contadores.

**Manejo de errores**:
- **Try/except global** alrededor de todo `write`. Si algo falla, loguea `exception` y retorna `WriteResult(skipped_reason="error: <msg>", ...)` con contadores a 0 — nunca propaga excepción.
- Escritura Postgres + Qdrant: si Postgres insert tiene éxito pero Qdrant falla, loguea warning y mantiene la fila en Postgres (consistencia eventual; aceptable en este scope).

### R4: Reglas de conversión JSON → facts

Implementadas en helper(s) puros (testables sin mocks):

**Summary** (si existe y no vacío):
- 1 fact: `"Model {class_name} ({paradigm}/{formulation}) in {environment}: {summary_text}"`.
- En comparison runs (varios modelos), usa el modelo del primer agente del `agent_to_model` como "representative" y anota en metadata `models_compared: [class_name1, class_name2, ...]`. Al Builder le vale para saber que la sim fue comparativa.
- importance=5, memory_type="semantic".
- Si el summary viene en español, se emite en inglés de forma mecánica: se prefija con el encabezado en inglés del modelo/entorno y se conserva el summary tal cual como "raw: \"...\"". Sin traducción automática en este scope.

**Trajectories** (para cada agent_id en `trajectories`):
- 1 fact: `"Agent {agent_id} using {class_name} in {environment} survived {steps_survived} steps, consumed {resources_consumed} resources; top actions: {top_3_actions}"`.
- `top_3_actions` = las 3 con mayor count, formato `"move_east(42), consume(17), move_west(9)"`.
- importance=6, memory_type="semantic".
- Metadata incluye `agent_id`.
- Si el `agent_id` no está en `agent_to_model` → skip esa trajectory y loguea warning.

**Episodes** (iterar sobre `episodes`):
- Filtrar por `type`:
  - **Omitir**: `foraging_success`, `exploration`, `exploitation` (incrementa `episodes_filtered`).
  - **Conservar**: todos los demás (`starvation`, `foraging_failure`, `state_change`, y cualquier tipo desconocido).
- 1 fact por episode conservado:
  `"Model {class_name} ({paradigm}/{formulation}) in {environment}: {description} [type={type}, agent={agent_id}, {step_or_range}]"`.
- `step_or_range` = `"step=N"` o `"steps=N..M"` según si `step` es int o lista `[start, end]`.
- importance: `starvation=9`, `state_change=8`, `foraging_failure=7`, desconocido=6. memory_type="episodic".
- Metadata incluye `agent_id`, `episode_type`, `step` (o `step_start`/`step_end`).
- Si `agent_id` no está en `agent_to_model` → skip y warning.

**Metadata común a todos** (los que aplique):
```python
{
  "phase2_experiment_id": context.phase2_experiment_id,
  "model_id": model_info.model_id,
  "model_class_name": model_info.class_name,
  "paradigm": model_info.paradigm,
  "formulation": model_info.formulation,
  "phase1_run_id": model_info.phase1_run_id,  # puede ser null
  "environment": context.environment,
  "steps": context.steps,
  "seed": context.seed,                        # puede ser null
  # agent_id, episode_type, step(s), models_compared: añadidos según corresponda
}
```

### R5: Tokenizer sparse

- Reutilizar `decisionlab.knowledge.tokenizer.tokenize_to_sparse` de Phase 1. Está accesible porque `phase1-pablo/src` ya está en el `pythonpath` del `pyproject.toml` de Phase 2 (marked for pytest — ver [phase2-juan/pyproject.toml](phase2-juan/pyproject.toml)).
- Si el import falla en runtime (no en tests), el writer debe retornar `skipped_reason="tokenizer_unavailable"`.
- **Fuera de scope**: portar el tokenizer a `shared/`. Si más adelante el pythonpath no funciona en producción, se aborda como issue separado.

### R6: Factory helper

Helper standalone para construir la instancia con servicios reales desde `settings`:

```python
async def build_writer_from_settings(settings: Settings) -> TrackerMemoryWriter | None:
    """Construye el writer conectando a Postgres/Qdrant/Voyage.
    Retorna None si falta VOYAGE_API_KEY o cualquier servicio no conecta."""
```

Esto centraliza la lógica de "¿está la infra lista?" y simplifica la integración en Phase 2.

### R7: Tests unitarios

- **Tests puros** (sin mocks) para las reglas de conversión: dado un JSON de tracker, verificar facts generados, importance, metadata.
- **Tests con mocks** para `TrackerMemoryWriter.write`:
  - Mock `VectorStore`, `EmbeddingService`, `DatabaseService.get_session`.
  - Caso happy path: 1 modelo, 2 agentes, 1 summary + 2 trajectories + 2 episodes (1 filtrado, 1 conservado) → verificar contadores y llamadas a mocks.
  - Caso comparison run: 2 modelos, 2 agentes cada uno.
  - Caso graceful degradation: `Qdrant.upsert` levanta → retorna `skipped_reason="error: ..."` con contadores a 0 (o parciales según lo que haya escrito antes de fallar).
  - Caso JSON inválido.
  - Caso tracker_output vacío (`summary="No events to observe."`).
- **Integration test**: marcado `@pytest.mark.integration`, corre solo con docker-compose arriba + `VOYAGE_API_KEY`. Verifica escritura real y lectura posterior.

## Acceptance Criteria

- [x] AC1: Existe `phase2-juan/simlab/knowledge/__init__.py` y `writer.py` con `TrackerMemoryWriter`, `WriteResult`, `ModelInfo`, `SimulationContext` exportados.
- [ ] AC2: `TrackerMemoryWriter.write` aplica las reglas de filtrado de episodes: `foraging_success`, `exploration`, `exploitation` se descartan; los demás se conservan.
- [ ] AC3: Los facts generados llevan metadata completa (`paradigm`, `formulation`, `model_class_name`, `phase2_experiment_id`, `phase1_run_id`, `environment`, `steps`, `seed`) y en el caso de trajectories/episodes también `agent_id`.
- [ ] AC4: El writer nunca propaga excepciones — cualquier fallo interno se captura, se loguea, y se retorna `WriteResult` con `skipped_reason` poblado.
- [ ] AC5: Todos los facts se embeben en un único batch para eficiencia (1 llamada a Voyage por `write`).
- [ ] AC6: Tests unitarios cubren: conversión pura, happy path con mocks, comparison run, JSON inválido, tracker vacío, fallo de infra. Marcador `integration` para el test con servicios reales.
- [ ] AC7: `build_writer_from_settings` retorna `None` si `VOYAGE_API_KEY` no está y loguea razón.

## Technical Notes

- **Patrón a imitar**: la pipeline determinística de [phase1-pablo/src/decisionlab/agents/memory_agent.py](phase1-pablo/src/decisionlab/agents/memory_agent.py) — misma filosofía "nunca raises, siempre retorna un result con contadores".
- **Reutilización `shared/`**: `shared.memories.create_memory`, `shared.vector_store.VectorStore`, `shared.embedding.EmbeddingService`, `shared.database.DatabaseService`. No duplicar nada.
- **Payload Qdrant**: copiar el patrón que usa Pazos en [phase1-pablo/src/decisionlab/knowledge/resolver.py](phase1-pablo/src/decisionlab/knowledge/resolver.py) para mantener forma consistente.
- **Archivos afectados (solo creación)**:
  - `phase2-juan/simlab/knowledge/__init__.py` (nuevo)
  - `phase2-juan/simlab/knowledge/writer.py` (nuevo)
  - `phase2-juan/tests/knowledge/__init__.py` (nuevo)
  - `phase2-juan/tests/knowledge/test_writer.py` (nuevo)
  - `phase2-juan/tests/knowledge/test_fact_rules.py` (nuevo)
  - `phase2-juan/tests/knowledge/test_integration.py` (nuevo, `@pytest.mark.integration`)
- **Ninguna modificación** a `orchestrator.py`, `tracker.py`, `shared/*`, o fichero de config en Phase 1.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Ubicación | `phase2-juan/simlab/knowledge/` | Deja sitio para retrieval futuro sin ensuciar `simlab/` raíz. |
| API | Clase con servicios inyectados en `__init__` | Coherente con el `MemoryAgent` de Pazos; facilita el mocking en tests. |
| `agent_to_model` | dict invertido `{agent_id: ModelInfo}` | Lookup O(1) al iterar trajectories/episodes. |
| Batch embedding | Un solo call a Voyage por `write` | Minimiza latencia y coste. |
| Tokenizer | Import de Phase 1 vía pythonpath | DRY. Si rompe en prod, issue aparte. |
| Episode "desconocido" | Conservar con importance=6 | Mejor guardar y filtrar al leer que perder datos potencialmente útiles. |
| Traducción ES→EN del summary | No traducción, adjuntar raw | Sin coste LLM. Pazos puede leer español igual (Voyage multilingüe). |
