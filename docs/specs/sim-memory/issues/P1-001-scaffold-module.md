---
id: P1-001
title: Scaffold knowledge module with data classes and factory
status: done
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

- [x] AC1: Existen los archivos listados, `from simlab.knowledge import TrackerMemoryWriter, WriteResult, ModelInfo, SimulationContext, build_writer_from_settings` funciona.
- [x] AC2: `TrackerMemoryWriter(...).write(...)` retorna `WriteResult` con `skipped_reason="not_implemented"` y contadores a 0.
- [x] AC3: `build_writer_from_settings` con settings mockeado sin `VOYAGE_API_KEY` retorna `None` y emite un log warning.
- [x] AC4: Los 3 tests en `test_scaffold.py` pasan (se añadieron 6 por robustez extra).

## Completion Summary

**Commit:** (se añade en el merge)

### What was built
- Módulo `phase2-juan/simlab/knowledge/` con `__init__.py` exportando la API pública.
- `writer.py` con 3 frozen dataclasses (`ModelInfo`, `SimulationContext`, `WriteResult`) y stub de `TrackerMemoryWriter.write()` que retorna `skipped_reason="not_implemented"`.
- Factory `build_writer_from_settings()` con short-circuit si faltan API keys o Postgres/Qdrant no conectan; gestión limpia de recursos (cierra `db` si Qdrant falla tras Postgres OK).
- 6 tests en `tests/knowledge/test_scaffold.py` (3 requeridos + 3 extra cubriendo ZeroEntropy key missing y fallo de Postgres).

### Files created
- `phase2-juan/simlab/knowledge/__init__.py`
- `phase2-juan/simlab/knowledge/writer.py`
- `phase2-juan/tests/knowledge/__init__.py`
- `phase2-juan/tests/knowledge/test_scaffold.py`

### Decisions
- Añadidos 3 tests extra (ZeroEntropy key vacía, Postgres falla) porque las ramas de error del factory son parte del contrato con Phase 2 integration.
- Imports pesados (`DatabaseService`, `VectorStore`, `EmbeddingService`) se hacen dentro de `build_writer_from_settings` en vez de a nivel de módulo, para mantener el import de `simlab.knowledge` barato aunque Voyage no esté instalado.

### Notas para runs futuros
- El entorno `phase2-juan/.venv` está con Python 3.14 y `voyageai` no soporta esa versión (pydantic v1 incompat). Tests corren con `uv run --python 3.13 pytest`. El fallo afecta también a los tests existentes — conviene fijar `.python-version=3.13` o upgradear voyageai en un issue separado.

## Files Likely Affected

- `phase2-juan/simlab/knowledge/__init__.py` — nuevo.
- `phase2-juan/simlab/knowledge/writer.py` — nuevo.
- `phase2-juan/tests/knowledge/__init__.py` — nuevo.
- `phase2-juan/tests/knowledge/test_scaffold.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R1, R2, R3 stub, R6)
General spec: `docs/specs/sim-memory/general.md`
Heat: `writer`
