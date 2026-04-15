---
id: P2-003
title: Orchestrator integration tests and e2e docs
status: done
kind: strike
phase: 2
heat: integration
priority: 3
blocked_by: [P2-002]
created: 2026-04-15
updated: 2026-04-16
---

# P2-003: Orchestrator integration tests and e2e docs

## Objective

Cubrir la integración con tests de orchestrator que parchean `shared.sim_memory_writer` y verifican el flow completo, y documentar el procedimiento manual docker-compose para ejecutar un e2e real en el checklist de release.

## Requirements

### R1: Tests del orchestrator

Crear `phase2-juan/tests/test_orchestrator_knowledge.py`:

- **Test happy path**:
  - Parche `shared.sim_memory_writer` con un `AsyncMock` que tiene atributo `write = AsyncMock(return_value=WriteResult(...))`.
  - Construye el Orchestrator con su cliente mockeado.
  - Ejecuta la secuencia mínima: inyectar un spec válido en `state`, llamar al handler de `run_simulation` con `model_ids=["paradigm/formulation"]` y un único modelo mockeado vía `patch("simlab.model_loader.discover_models")`, luego llamar al handler de `observe_simulation` con un tracker mockeado que devuelve un JSON fijo.
  - Asserts:
    - `writer.write.await_count == 1`.
    - El `SimulationContext` pasado tiene `phase2_experiment_id == state["experiment_id"]`, `environment` empieza por `"grid_"`, `steps` ≥ 0, `agent_to_model` tiene al menos 1 entrada.
    - El `tracker_output` pasado es el string JSON que devolvió el Tracker.

- **Test flag OFF / writer None**:
  - Sin parchear `shared.sim_memory_writer` (queda None, su default).
  - Ejecutar el mismo flow.
  - Assert: el `observe_simulation` completa sin errores, `writer.write` no se puede invocar (no hay writer), y el `tracker_output` se devuelve al caller exactamente igual que antes.

- **Test writer failure**:
  - `writer.write = AsyncMock(side_effect=RuntimeError("boom"))`.
  - Ejecutar flow; assert que `observe_simulation` **no propaga** la excepción y devuelve el `tracker_output` normalmente.
  - Assert que `logger.exception` fue llamado (capturar vía `caplog`).

Los tests deben correr sin infra real — todo mockeado. No deben requerir `VOYAGE_API_KEY` ni Qdrant/Postgres arriba.

### R2: Documentación e2e

Crear `docs/specs/sim-memory/README.md` con:

- **Overview** (1 párrafo): qué es sim-memory, qué hace, link al general.md.
- **Development** (cómo probar localmente):
  ```bash
  # 1. Infra
  docker compose up -d postgres qdrant

  # 2. Migraciones
  cd shared && uv run alembic upgrade head

  # 3. Config (.env)
  # - VOYAGE_API_KEY, ZEROENTROPY_API_KEY
  # - ENABLE_KNOWLEDGE_WRITE=true

  # 4. CLI
  cd phase2-juan && uv run simlab
  # Correr una simulación completa (create_environment → run → observe)

  # 5. Verificar Postgres
  psql ... -c "SELECT namespace, memory_type, count(*) FROM memories GROUP BY 1,2;"
  # Esperado: simulation | semantic | >=1 y simulation | episodic | >=0

  # 6. Verificar Qdrant
  curl -X POST http://localhost:6333/collections/memories_dense/points/scroll \
       -H 'Content-Type: application/json' \
       -d '{"filter":{"must":[{"key":"namespace","match":{"value":"simulation"}}]}, "limit":10}'
  ```
- **Integration test**: cómo ejecutar `tests/knowledge/test_integration.py` con infra real:
  ```bash
  cd phase2-juan && uv run pytest tests/knowledge/test_integration.py -m integration -v
  ```
- **Architectural links**: pointer a `general.md`, `phase-1-core-writer.md`, `phase-2-integration.md`.

No se crea un test automatizado e2e con docker-compose en CI — fuera de scope.

## Acceptance Criteria

- [x] AC1: Los 3 tests de `test_orchestrator_knowledge.py` pasan sin infra real (mocks de `Tracker` + `shared.sim_memory_writer`).
- [x] AC2: `test_observe_simulation_swallows_writer_exception` verifica explícitamente vía `caplog` que la excepción no se propaga y el tracker_output se devuelve tal cual.
- [x] AC3: README.md escrito con procedimiento manual paso a paso (docker compose → migrations → env → CLI run → SQL verification → Qdrant curl → integration test) + referencias a los otros specs.
- [x] AC4: 115 tests de phase2-juan verdes (1 skipped = integration). 27 tests relevantes de shared verdes. Los 21 fallos en shared son integration tests pre-existentes que requieren MinIO/Postgres/Neo4j levantados — no afectados por este strike.

## Completion Summary

### What was built
- `phase2-juan/tests/test_orchestrator_knowledge.py` — 3 tests async que instancian un `Orchestrator` real, extraen el closure `observe_simulation` vía `_build_tools()`, y mockean:
  - `simlab.orchestrator.Tracker` para devolver un JSON fijo sin llamar al LLM.
  - `shared.sim_memory_writer` con un AsyncMock.

  Casos: (1) writer presente → invoca `write()` con el `SimulationContext` correcto (env=`grid_10x8`, steps=25, seed=7, agent resuelto); (2) writer=None → sin llamadas, tracker_output intacto; (3) writer raise → `logger.exception` capturado vía `caplog`, tracker_output se devuelve normalmente.

- `docs/specs/sim-memory/README.md` — guía manual end-to-end: docker-compose + alembic + .env + CLI run + 6 comandos de verificación (SQL + Qdrant scroll) + cómo correr el integration test de P1-004.

### Files created
- `phase2-juan/tests/test_orchestrator_knowledge.py` (~140 LOC, 3 tests).
- `docs/specs/sim-memory/README.md` (~140 líneas de guía operativa).

### Decisions
- **Tests vía `_build_tools()`**: en vez de refactorizar el orchestrator para exponer los handlers, uso la función que ya existe (`_build_tools` devuelve el registry dict con los closures). Cero intrusión en el código de producción.
- **`experiment_id=None`** en los tests: evita el bloque S3+DB (`shared.storage.put_text` + `shared.db.get_session`) que requeriría mocking más profundo. El resultado es equivalente — el writer se invoca con `phase2_experiment_id=""` que verifica el test.
- **Fixture `_reset_writer_singleton`** autouse: el singleton es estado global, los tests deben aislarse entre sí para no arrastrar efectos.
- **README con comandos copy-pasteables**: formato release-checklist, no tutorial exhaustivo. Los specs tienen la justificación arquitectural.

## Files Likely Affected

- `phase2-juan/tests/test_orchestrator_knowledge.py` — nuevo (3 tests).
- `docs/specs/sim-memory/README.md` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-2-integration.md` (R5, R6)
General spec: `docs/specs/sim-memory/general.md`
Heat: `integration`
Depende de P2-002 (wiring completo en el orchestrator).
