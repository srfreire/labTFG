---
id: P1-004
title: Writer tests with mocks and integration test
status: todo
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

- [ ] AC1: Los 7 tests unitarios pasan sin credenciales ni servicios externos.
- [ ] AC2: El integration test está marcado `@pytest.mark.integration` y NO se ejecuta en `pytest` por defecto (solo con `pytest -m integration`).
- [ ] AC3: El integration test, cuando se ejecuta con infra real, escribe memorias y las recupera; al terminar deja el estado limpio.
- [ ] AC4: Los mocks verifican número exacto de llamadas (embed 1x, upserts 2×N, create_memory Nx, commit 1x) para detectar regresiones.
- [ ] AC5: El test de fallo Qdrant verifica explícitamente que un fallo intermedio no aborta el resto del bucle.

## Files Likely Affected

- `phase2-juan/tests/knowledge/test_writer.py` — nuevo.
- `phase2-juan/tests/knowledge/test_integration.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R7)
General spec: `docs/specs/sim-memory/general.md`
Heat: `writer`
Depende de P1-003 (implementación completa).
