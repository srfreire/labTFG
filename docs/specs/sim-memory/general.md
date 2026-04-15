# sim-memory — General Specification

> Status: current | Created: 2026-04-15 | Last updated: 2026-04-15

## Overview

Cierra el loop entre Phase 2 (virtual lab — simulación y observación) y Phase 1 (pipeline de Pablo — generación de modelos). Cada vez que el Tracker termina de observar una simulación, las observaciones significativas se escriben como memorias en el Knowledge Backbone (namespace `simulation`). Así, en runs futuros del pipeline de Pablo, el Builder puede recuperar "cómo se comportó este modelo / paradigma / formulación en simulaciones previas" y aprender de fallos reales (starvation, no convergencia, bucles de exploración) para mejorar el código que genera.

El componente central es un `TrackerMemoryWriter` en Phase 2 que transforma el JSON estructurado del Tracker en memorias persistidas en Postgres + Qdrant (dense + sparse), sin llamadas LLM adicionales.

## Core Features

- **Sin LLM extra**: el JSON del Tracker ya es estructurado (summary, trajectories, episodes). El writer convierte directamente sus campos a "facts" en lenguaje natural, sin re-extracción.
- **Filtro de episodios**: solo se persisten tipos de episode con valor de aprendizaje para runs futuros (`starvation`, `foraging_failure`, `state_change`, y genéricos no reconocidos). Los rutinarios (`foraging_success`, `exploration`, `exploitation`) se omiten.
- **Multi-model aware**: un experimento con varios modelos genera memorias separadas por modelo, enlazadas correctamente vía `paradigm`/`formulation` en metadata.
- **Metadata rica para join cross-phase**: cada memoria lleva `paradigm`, `formulation`, `model_class_name`, `phase1_run_id` (el run que produjo el modelo), `phase2_experiment_id` (el experimento de simulación), `environment`, `steps`, `seed`. Esto permite al Builder de Pablo recuperar por cualquier dimensión.
- **Importance estática por tipo**: reglas simples sin LLM (starvation=9, foraging_failure=7, state_change=8, trajectory=6, summary=5).
- **Confidence fija 0.80**: observación empírica directa, equivalente al reasoner de Phase 1 — alta porque pasó de verdad en el simulador, pero no máxima porque el modelo en sí puede tener fallos que desvirtúen la observación.
- **Flag de activación**: `ENABLE_KNOWLEDGE_WRITE=true|false` en `.env`. Default `false` hasta estar probado.
- **Graceful degradation**: si Qdrant, Postgres o Voyage no están disponibles, se loguea warning y se omite sin romper el pipeline de simulación.
- **Invocación post-Tracker síncrona**: el writer se llama dentro de `observe_simulation` en el Orchestrator, justo después de guardar el tracker_output en S3/DB. Síncrono — añade <1s, imperceptible frente al Tracker LLM loop.

## Out of Scope

- **Nodos en Neo4j** — no creamos entidades `Simulation`/`Observation`. Deja la decisión al futuro si multi-hop retrieval se demuestra necesario (anotado en `CLAUDE.md`).
- **Extracción LLM de insights** — el JSON del Tracker es la fuente de verdad. Si más adelante se quiere enriquecer (p.ej. Haiku leyendo el JSON para extraer "aprendizajes tácitos"), será una iteración futura.
- **Retrieval desde Phase 2** — este scope es solo escritura. Que Analyst/Architect/Reporter lean del KG vía `retrieve_knowledge` es un TODO separado.
- **Escritura a `artifacts_*`** — solo escribimos a `memories_dense` y `memories_sparse`. El JSON completo del Tracker sigue viviendo en MinIO/S3 como hasta ahora; no lo troceamos ni lo indexamos como artefacto.
- **Retención / pruning** — no gestionamos expiración. Pazos ya tiene consolidation post-run en Phase 1 (P5-003) — si hace falta eso para Phase 2, se integrará después.
- **Confidence evolution automática** — importance y confidence se fijan en escritura. El sistema de corroboraciones/contradicciones ya existente en `shared.memories` aplicará de forma natural cuando Pablo lo dispare desde sus runs.

## Data Model

No se añaden tablas nuevas. Se escribe en la tabla `memories` existente ([shared/shared/models.py:151](shared/shared/models.py)) y en las colecciones `memories_dense` / `memories_sparse` de Qdrant ya creadas por Pazos.

### Campos por memoria

| Campo | Valor |
|---|---|
| `id` | UUID generado |
| `content` | Fact en inglés, frase única autocontenida |
| `namespace` | `"simulation"` |
| `memory_type` | `"semantic"` (summary, trajectory) o `"episodic"` (episodes) |
| `source_stage` | `"tracker"` |
| `run_id` | `None` (Phase 2 no tiene entrada en tabla `runs`) |
| `importance` | float fijo por tipo (ver Importance Rules) |
| `confidence` | `0.80` |
| `metadata` (JSONB) | ver abajo |

### Metadata JSONB

```json
{
  "phase2_experiment_id": "<UUID>",
  "model_id": "<UUID del Model de Phase 1>",
  "model_class_name": "HomeostaticDriveReductionRL",
  "paradigm": "homeostatic-regulation",
  "formulation": "drive-reduction-rl",
  "phase1_run_id": "<UUID del run de Phase 1 que produjo el modelo>",
  "environment": "grid_10x10",
  "steps": 200,
  "seed": 42,
  "agent_id": "agent_0",          // solo para trajectory/episode
  "episode_type": "starvation",   // solo para episode
  "step": 120                     // solo para episode (o [start, end] si es rango)
}
```

### Fact generation rules

Dado un `tracker_output` JSON:

- **summary** → 1 memoria:
  `"Model {class_name} ({paradigm}/{formulation}) in {environment}: {summary_text}"`
  importance=5, type=semantic.

- **trajectories[agent_id]** → 1 memoria por agente:
  `"Agent {agent_id} using {class_name} in {environment} survived {N} steps, consumed {R} resources, actions: {top_actions}"`
  importance=6, type=semantic.

- **episodes[i]** → 1 memoria por episode si `type` pasa el filtro:
  `"Model {class_name} ({paradigm}/{formulation}) in {environment}: {description} (type={type}, agent={agent}, step={step})"`
  importance por tipo (ver tabla), type=episodic.

### Importance rules

| Tipo | Importance |
|---|---|
| `starvation` | 9 |
| `state_change` | 8 |
| `foraging_failure` | 7 |
| (episode type desconocido) | 6 |
| trajectory | 6 |
| summary | 5 |

Episodios con type ∈ {`foraging_success`, `exploration`, `exploitation`} se **omiten** (no se crean memorias).

## Integrations

- **Postgres** — escritura vía `shared.memories.create_memory()`.
- **Qdrant** — upsert a `memories_dense` y `memories_sparse` vía `shared.vector_store.VectorStore`.
- **Voyage AI** — embeddings vía `shared.embedding.EmbeddingService` (requiere `VOYAGE_API_KEY`).
- **Tokenizer sparse** — reutilizamos `decisionlab.knowledge.tokenizer.tokenize_to_sparse` de Pablo (o lo portamos a `shared/` si hace falta).
- **Orchestrator Phase 2** — punto de invocación único: tras `observe_simulation` en [orchestrator.py:641](phase2-juan/simlab/orchestrator.py:641).

## User Flows

### Flow 1: Simulación exitosa con flag OFF (comportamiento actual)

1. Usuario corre simulación desde CLI/Web.
2. Tracker termina, guarda JSON en S3/DB.
3. `ENABLE_KNOWLEDGE_WRITE=false` → writer no se invoca.
4. Pipeline sigue como hasta ahora. Zero cambios observables.

### Flow 2: Simulación exitosa con flag ON, infra arriba

1. Usuario corre simulación (1 modelo, 3 agentes, 200 pasos en grid 10x10).
2. Tracker produce JSON con summary, trajectories[agent_0/1/2], episodes (p.ej. 1 starvation en agent_1 paso 120, 2 foraging_success).
3. Orchestrator llama a `TrackerMemoryWriter.write(tracker_output, experiment_context)`.
4. Writer parsea el JSON:
   - 1 fact de summary.
   - 3 facts de trajectories (uno por agente).
   - 1 fact de episode (starvation; los 2 foraging_success se filtran).
5. Writer embebe las 5 frases con Voyage (batch), tokeniza para sparse.
6. Writer hace upsert atómico: insert en Postgres + upsert en ambas colecciones Qdrant, con mismo UUID.
7. Se loguea: "Wrote 5 memories to namespace=simulation (1 summary, 3 trajectories, 1 episode)".

### Flow 3: Comparison run (varios modelos)

1. Usuario corre simulación con `model_ids=["T01-P01-F01", "T01-P02-F01"]`, 2 agentes cada uno.
2. Tracker produce JSON con 4 trajectories y N episodes con `agent_id` diferenciados.
3. Writer resuelve `agent_id → model` vía `state["agents_by_model"]` (o equivalente — ver Technical Notes).
4. Cada fact lleva el `paradigm`/`formulation` del modelo correcto en metadata.
5. Resultado: memorias separadas por modelo, joineable por Pablo.

### Flow 4: Infra caída (graceful degradation)

1. Usuario corre simulación con `ENABLE_KNOWLEDGE_WRITE=true` pero Qdrant no está arriba.
2. Writer intenta conexión, falla.
3. Se loguea `WARNING: knowledge write skipped — Qdrant unreachable`.
4. Pipeline de simulación continúa. Analyst y Reporter funcionan normalmente.

## Constraints & Non-Functional Requirements

- **Latencia**: <1 segundo añadido al turno `observe_simulation` (1 batch embed de ~5-20 frases + inserts). Aceptable frente al Tracker que tarda decenas de segundos.
- **Coste**: Voyage embeddings ~5-20 frases por simulación, <$0.0001. Insignificante.
- **Fiabilidad**: **ningún fallo de escritura rompe el pipeline**. Try/except global en el writer; logs pero no propagación.
- **Idempotencia**: si el usuario llama `observe_simulation` dos veces con el mismo experimento, se escriben duplicados (acepto por simplicidad). La dedup entre runs se la come Pablo cuando lea. Mitigación futura: check por `phase2_experiment_id` antes de escribir.
- **Reversibilidad**: el flag apagado devuelve al estado actual sin cambios en DB.
- **Tests**: unit tests para conversión JSON→facts + filtrado (mocks de Voyage/Qdrant/PG). Integration test con docker-compose arriba (marcado `@pytest.mark.integration`).

## Key Decisions

| Decisión | Elección | Razón |
|---|---|---|
| Fuente de facts | JSON del Tracker directamente | Ya es estructurado. Sin coste LLM. Control total sobre el contenido. |
| Extracción LLM | No | YAGNI. Si luego hace falta, se añade. |
| Neo4j nodes | No | Pazos ya tiene `Model`/`TestResult` en el KG; añadir `Simulation` requiere negociar schema. YAGNI. |
| Activación | Flag `ENABLE_KNOWLEDGE_WRITE` en `.env` | Permite probar sin activar en producción. Default OFF. |
| Invocación | Síncrono dentro de `observe_simulation` | <1s overhead, simplifica el control de errores y la UX. |
| Tokenizer sparse | Reutilizar `decisionlab.knowledge.tokenizer` | DRY. Si no está accesible desde Phase 2 por packaging, portarlo a `shared/`. |
| Importance por LLM | No, reglas fijas por tipo | Cero coste, determinista. |
| Filtro de episodes | Solo fallos/cambios de estado | Los éxitos rutinarios saturan el KG sin aportar. |
| `run_id` en Memory | `None` | Phase 2 no está en la tabla `runs` (solo experimentos). Phase 2's `experiment_id` va en metadata JSONB. |
| `memory_type` | `"semantic"` vs `"episodic"` | Summary/trajectory son hechos generales; episodes son eventos concretos (patrón cognitivo). |
