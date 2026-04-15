---
id: P1-003
title: Implement TrackerMemoryWriter.write orchestration
status: todo
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

- [ ] AC1: `write()` implementado, ya no retorna `skipped_reason="not_implemented"`.
- [ ] AC2: Una sola llamada a `embed_texts` por invocación, independientemente de cuántos facts haya.
- [ ] AC3: Cualquier excepción dentro de `write` se captura — el método nunca propaga. Verificable por inspección (un `try/except BaseException` exceptuando `CancelledError` envuelve el cuerpo completo).
- [ ] AC4: Si Qdrant upsert falla para un fact concreto, los demás facts siguen escribiéndose; el fact fallido deja su fila en Postgres y loguea warning.
- [ ] AC5: El método commitea una sola vez al final del bucle (no commit por fact).
- [ ] AC6: Todos los upserts a Qdrant usan el mismo UUID que la fila Postgres correspondiente.

## Files Likely Affected

- `phase2-juan/simlab/knowledge/writer.py` — modificar `TrackerMemoryWriter.write`.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R3, R5)
General spec: `docs/specs/sim-memory/general.md` (Data Model, Key Decisions)
Heat: `writer`
Depende de P1-002 para `build_all_facts` y `FactSpec`.
