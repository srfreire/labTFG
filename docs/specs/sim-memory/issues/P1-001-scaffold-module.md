---
id: P1-001
title: Scaffold knowledge module with data classes and factory
status: todo
kind: strike
phase: 1
heat: writer
priority: 1
blocked_by: []
created: 2026-04-15
updated: 2026-04-15
---

# P1-001: Scaffold knowledge module with data classes and factory

## Objective

Crear la estructura del módulo `phase2-juan/simlab/knowledge/` con las data classes, un stub vacío de `TrackerMemoryWriter`, y el factory `build_writer_from_settings`. Deja el terreno preparado para que P1-002 y P1-003 trabajen encima con firmas ya acordadas.

## Requirements

- Crear `phase2-juan/simlab/knowledge/__init__.py` exportando los nombres públicos: `TrackerMemoryWriter`, `WriteResult`, `ModelInfo`, `SimulationContext`, `build_writer_from_settings`.
- Crear `phase2-juan/simlab/knowledge/writer.py` con:
  - Data classes `ModelInfo`, `SimulationContext`, `WriteResult` (frozen dataclasses, firmas exactas del spec R2).
  - Clase `TrackerMemoryWriter` con `__init__(*, vector_store, embedding_service, db)` y stub `async def write(self, tracker_output, context) -> WriteResult` que de momento retorna `WriteResult(0, 0, 0, 0, 0, skipped_reason="not_implemented")`.
  - Función `async def build_writer_from_settings(settings: Settings) -> TrackerMemoryWriter | None`: conecta Postgres vía `DatabaseService`, Qdrant vía `VectorStore.connect()` + `init_collections()`, y crea `EmbeddingService(voyage_api_key, zeroentropy_api_key)` si ambas keys están presentes. Si falta alguna key o falla una conexión, loguea warning y retorna `None`.
- Crear `phase2-juan/tests/knowledge/__init__.py` (vacío).
- Crear `phase2-juan/tests/knowledge/test_scaffold.py` con 3 tests mínimos:
  - Los 3 dataclasses son instanciables con los campos correctos.
  - `TrackerMemoryWriter` puede construirse pasando mocks de los 3 servicios.
  - `build_writer_from_settings` con settings sin `VOYAGE_API_KEY` retorna `None`.

## Acceptance Criteria

- [ ] AC1: Existen los archivos listados, `from simlab.knowledge import TrackerMemoryWriter, WriteResult, ModelInfo, SimulationContext, build_writer_from_settings` funciona.
- [ ] AC2: `TrackerMemoryWriter(...).write(...)` retorna `WriteResult` con `skipped_reason="not_implemented"` y contadores a 0.
- [ ] AC3: `build_writer_from_settings` con settings mockeado sin `VOYAGE_API_KEY` retorna `None` y emite un log warning.
- [ ] AC4: Los 3 tests en `test_scaffold.py` pasan.

## Files Likely Affected

- `phase2-juan/simlab/knowledge/__init__.py` — nuevo.
- `phase2-juan/simlab/knowledge/writer.py` — nuevo.
- `phase2-juan/tests/knowledge/__init__.py` — nuevo.
- `phase2-juan/tests/knowledge/test_scaffold.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R1, R2, R3 stub, R6)
General spec: `docs/specs/sim-memory/general.md`
Heat: `writer`
