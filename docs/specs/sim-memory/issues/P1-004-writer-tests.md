---
id: P1-004
title: Writer tests with mocks and integration test
status: done
kind: strike
phase: 1
heat: writer
priority: 4
blocked_by: [P1-003]
created: 2026-04-15
updated: 2026-04-15
---

# P1-004: Writer tests with mocks and integration test

## Objective

Cubrir `TrackerMemoryWriter.write()` con tests que verifiquen happy path, comparison run, graceful degradation y caso vacío, más un integration test real (marcado) que escriba contra Postgres + Qdrant + Voyage de verdad.

## Requirements

- Crear `phase2-juan/tests/knowledge/test_writer.py` con tests async (pytest-asyncio):
  1. **Happy path — 1 modelo / 2 agentes**: tracker_output con 1 summary, 2 trajectories, 3 episodes (2 filtrables, 1 conservable). Verificar:
     - `WriteResult.summaries_written == 1`, `trajectories_written == 2`, `episodes_written == 1`, `episodes_filtered == 2`.
     - `embedding_service.embed_texts` llamado exactamente 1 vez con una lista de 4 elementos.
     - `create_memory` llamado 4 veces (via mock de session).
     - Upsert en `memories_dense` y `memories_sparse` 4 veces cada uno, con el mismo UUID por fact.
     - `session.commit()` llamado 1 vez.
  2. **Comparison run**: 2 modelos, 2 agentes cada uno. Verificar que cada trajectory/episode fact lleva el `paradigm`/`formulation` correcto en metadata.
  3. **JSON inválido**: `tracker_output = "not json at all"` → `skipped_reason == "invalid_json"`, contadores a 0, sin llamadas a mocks de embed/qdrant/pg.
  4. **Tracker vacío**: JSON válido pero `summary=""`, `trajectories={}`, `episodes=[]` → `skipped_reason == "no_relevant_content"`.
  5. **Fallo Qdrant dense**: `vector_store.upsert_dense` raise en el 2º fact → los facts 1, 3, 4 se upsertean correctamente; fact 2 deja fila en Postgres pero warning logueado; `WriteResult` refleja lo que sí se escribió sin `skipped_reason`.
  6. **Fallo Voyage**: `embed_texts` raise → `skipped_reason.startswith("error:")`, contadores a 0.
  7. **agent_id desconocido en episode**: el episode se skip y no cuenta ni como written ni como filtered (o cuenta solo como warning — decidir con P1-002).
- Tests deben correr sin credenciales reales (todo mockeado). `VectorStore`, `EmbeddingService`, `DatabaseService`/`AsyncSession`, `create_memory` mockeados con `unittest.mock.AsyncMock`.

- Crear `phase2-juan/tests/knowledge/test_integration.py` marcado con `@pytest.mark.integration`:
  - Requiere `.env` con `VOYAGE_API_KEY`, `ZEROENTROPY_API_KEY` y docker-compose arriba (Postgres + Qdrant).
  - Construye writer real con `build_writer_from_settings`.
  - Invoca `write()` con un tracker_output fabricado.
  - Consulta Postgres directamente y verifica que hay N filas con `namespace="simulation"`, `source_stage="tracker"`.
  - Hace `vector_store.search_dense("memories_dense", query_vec, limit=5)` con un query derivado del content y verifica que la memoria escrita aparece entre los resultados.
  - Limpia tras el test (delete filas Postgres + delete points Qdrant por UUID).

## Acceptance Criteria

- [x] AC1: Los 11 tests unitarios pasan sin credenciales ni servicios externos (se ampliaron los 7 requeridos con parametrizaciones y un test extra para sparse vacío).
- [x] AC2: El integration test está marcado `@pytest.mark.integration` y NO se ejecuta en `pytest` por defecto (111 passed, 1 skipped).
- [x] AC3: El integration test, cuando se ejecuta con infra real, escribe memorias y las recupera; al terminar deja el estado limpio (cleanup Postgres + Qdrant en `finally`). No se ha ejecutado contra infra real en este strike — requiere docker-compose + keys.
- [x] AC4: Los mocks verifican número exacto de llamadas: 1x embed_texts, 4x create_memory, 4x upsert_dense, 4x upsert_sparse, 1x commit en el happy path.
- [x] AC5: `test_qdrant_dense_failure_does_not_abort_batch` verifica explícitamente que un fallo en el 2º fact no aborta los restantes.

## Completion Summary

### What was built
- `phase2-juan/tests/knowledge/test_writer.py` — 11 tests unitarios:
  1. Happy path 1 modelo / 2 agentes — verifica contadores, batch embed, upserts, commit, UUIDs compartidos.
  2. Comparison run — verifica tagging correcto de paradigm/formulation por fact.
  3. Invalid JSON (3 variantes parametrizadas: string plano, vacío, JSON que no es dict).
  4. Empty tracker — no_relevant_content.
  5. All-routine-episodes — no_relevant_content pero reporta `episodes_filtered`.
  6. Qdrant dense failure en el 2º fact — los 4 se procesan, commit ocurre.
  7. Voyage failure — skipped_reason startswith "error:", contadores a 0.
  8. Unknown agent_id en episode — skipped con warning, no cuenta en `episodes_filtered`.
  9. Sparse vector vacío — `upsert_sparse` no se llama (nueva verificación defensiva).
- `phase2-juan/tests/knowledge/test_integration.py` — integration test marcado:
  - Skip automático sin `VOYAGE_API_KEY` + `ZEROENTROPY_API_KEY`.
  - Escribe 3 memorias (summary/trajectory/episode) con `phase2_experiment_id` único.
  - Verifica filas en Postgres (namespace/source_stage/confidence/memory_type counts).
  - Hace `search_dense` filtrando por `phase2_experiment_id` y verifica recuperación.
  - Cleanup en `finally`: delete Postgres + delete Qdrant (ambas colecciones).

### Files created
- `phase2-juan/tests/knowledge/test_writer.py` (~280 LOC)
- `phase2-juan/tests/knowledge/test_integration.py` (~130 LOC)

### Decisions
- **Parametrizar JSON inválido**: cubre no-json, string vacío y JSON válido pero no-dict (array). El writer debe rechazar los 3 con el mismo `skipped_reason`.
- **Test sparse vacío extra**: no estaba en la lista del spec pero P1-003 añadió esa rama defensiva — tenerlo cubierto detecta regresiones.
- **Helper `_make_writer`** reduce boilerplate de mocking a una línea por test.
- **Acceso a `writer._db`/`_vectors`/`_embeddings`** en el integration test**: miembros "privados" por convención Python (`_prefix`) pero accesibles. Alternativas (exponer getters) añadían código sin valor para tests.
- **Integration test no corrido en CI local**: requiere docker-compose y keys. Se ha validado `--collect-only` y que skip correctamente cuando faltan keys.

## Files Likely Affected

- `phase2-juan/tests/knowledge/test_writer.py` — nuevo.
- `phase2-juan/tests/knowledge/test_integration.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R7)
General spec: `docs/specs/sim-memory/general.md`
Heat: `writer`
Depende de P1-003 (implementación completa).
