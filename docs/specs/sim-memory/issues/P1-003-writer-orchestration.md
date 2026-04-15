---
id: P1-003
title: Implement TrackerMemoryWriter.write orchestration
status: done
kind: strike
phase: 1
heat: writer
priority: 3
blocked_by: [P1-002]
created: 2026-04-15
updated: 2026-04-15
---

# P1-003: Implement TrackerMemoryWriter.write orchestration

## Objective

Implementar el método `TrackerMemoryWriter.write()` completo: parsea el JSON del Tracker, llama a los helpers de `facts.py` (P1-002), embebe en batch con Voyage, tokeniza a sparse, inserta en Postgres y hace upsert a Qdrant (dense + sparse). Try/except global: nunca propaga excepciones.

## Requirements

- Sustituir el stub `write()` de `TrackerMemoryWriter` por la implementación real:
  1. `t0 = time.monotonic()` para medir `duration_ms`.
  2. Parsear `tracker_output` como JSON — si falla → retornar `WriteResult(skipped_reason="invalid_json", ...)`.
  3. Llamar a `build_all_facts(tracker, context)` → `(facts, episodes_filtered)`.
  4. Si `facts` está vacío → `WriteResult(skipped_reason="no_relevant_content", ...)` (contador `episodes_filtered` sí se reporta).
  5. `dense_vectors = await self._embeddings.embed_texts([f.text for f in facts])` — un único batch.
  6. `sparse_vectors = [tokenize_to_sparse(f.text) for f in facts]` usando `decisionlab.knowledge.tokenizer.tokenize_to_sparse`. Si el import falla → retornar `skipped_reason="tokenizer_unavailable"`.
  7. Por cada fact, en una transacción de sesión:
     - Generar UUID.
     - `await create_memory(session, id=uuid, content=fact.text, namespace="simulation", memory_type=fact.memory_type, source_stage="tracker", run_id=None, importance=fact.importance, confidence=0.80, metadata_=fact.metadata)`.
     - Upsert en `memories_dense` con `(id=uuid, vector=dense_vectors[i], payload={"memory_id": str(uuid), "namespace": "simulation", **fact.metadata})`.
     - Upsert en `memories_sparse` con análogo usando `sparse_vectors[i]`.
     - Si Qdrant upsert falla → loguear warning, dejar la fila en Postgres, continuar con el siguiente fact.
  8. `await session.commit()` al final del bucle (batch commit).
  9. Devolver `WriteResult` con contadores desglosados por tipo (`summaries_written`, `trajectories_written`, `episodes_written`) y `duration_ms`.
- Try/except global alrededor de todo el método: cualquier excepción no controlada captura `logger.exception(...)` y retorna `WriteResult(skipped_reason=f"error: {type.__name__}: {msg}", ...)` con los contadores que ya se hubieran acumulado.
- Contar por tipo iterando los `FactSpec` (clasificar por `memory_type` y presencia de `episode_type` en metadata).
- Añadir logging informativo al final: `logger.info("TrackerMemoryWriter: wrote N memories to namespace=simulation — X summaries, Y trajectories, Z episodes, W filtered, %dms")`.

## Acceptance Criteria

- [x] AC1: `write()` implementado, ya no retorna `skipped_reason="not_implemented"`.
- [x] AC2: Una sola llamada a `embed_texts` por invocación, independientemente de cuántos facts haya.
- [x] AC3: Cualquier excepción dentro de `write` se captura — el método nunca propaga. Verificable por inspección (un `try/except BaseException` exceptuando `CancelledError` envuelve el cuerpo completo).
- [x] AC4: Si Qdrant upsert falla para un fact concreto, los demás facts siguen escribiéndose; el fact fallido deja su fila en Postgres y loguea warning (implementado vía `_safe_upsert_dense`/`_safe_upsert_sparse`).
- [x] AC5: El método commitea una sola vez al final del bucle (no commit por fact).
- [x] AC6: Todos los upserts a Qdrant usan el mismo UUID que la fila Postgres correspondiente (pre-generado con `uuid.uuid4()` y reutilizado).

## Completion Summary

### What was built
- `TrackerMemoryWriter.write()` completo con flujo: parse JSON → build_all_facts → batch embed → tokenize sparse → insert PG + upsert Qdrant dense/sparse → commit.
- Try/except global en `write` (solo deja pasar `CancelledError`). Cualquier otro fallo se captura, loguea y retorna `WriteResult(skipped_reason="error: ...")`.
- Helpers privados `_safe_upsert_dense` y `_safe_upsert_sparse`: cada upsert Qdrant tiene su propio try/except, el fallo de uno no aborta los demás (AC4).
- Dataclass interno `_Counters` para contar summaries/trajectories/episodes distinguiéndolos por `memory_type` + presencia de `agent_id` en metadata.
- Sparse vectors vacíos (`indices=[]`) se saltan silenciosamente — Qdrant no acepta sparse vectors vacíos.

### Files modified/created
- `phase2-juan/simlab/knowledge/writer.py` — implementación completa de `write()` + helpers.
- `shared/shared/tokenizer.py` — **portado desde `phase1-pablo/src/decisionlab/knowledge/tokenizer.py`** (60 LOC, sin deps). Necesario porque el pythonpath de phase2 para phase1 solo aplica en pytest, no en runtime.
- `phase2-juan/tests/knowledge/test_scaffold.py` — actualizado: `test_writer_stub_returns_not_implemented` ahora verifica `skipped_reason="no_relevant_content"` tras implementación real.

### Decisions
- **Tokenizer portado a `shared/`**: el spec decía "fuera de scope" pero en el smoke test vimos que el import `from decisionlab.knowledge.tokenizer` falla en runtime (el `pythonpath` del `pyproject.toml` solo se aplica en pytest). Portar el código a `shared/` es la solución mínima, mantiene a Phase 1 intacto con su copia, y permite consolidar en un issue futuro.
- **Payload de Qdrant**: incluye `memory_id`, `namespace`, `source_stage` y todo el `metadata` del fact (flat merge). Así el payload es suficiente para buscar por `paradigm`/`formulation` sin ir a Postgres.
- **Sparse vectors vacíos**: Qdrant rechaza `SparseVector(indices=[], values=[])`. Si el tokenizer devuelve lista vacía (texto muy corto/stopwords), skip sparse upsert sin warning.
- **`run_id=None`** explícito en `create_memory` (Phase 2 no vive en la tabla `runs`; el `phase2_experiment_id` viaja en metadata JSONB como decidido en el spec general).
- **Helpers `_safe_upsert_*`** fuera de la clase: simplifica testing y mantiene `write()` legible como una pipeline lineal.

## Files Likely Affected

- `phase2-juan/simlab/knowledge/writer.py` — modificar `TrackerMemoryWriter.write`.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R3, R5)
General spec: `docs/specs/sim-memory/general.md` (Data Model, Key Decisions)
Heat: `writer`
Depende de P1-002 para `build_all_facts` y `FactSpec`.
