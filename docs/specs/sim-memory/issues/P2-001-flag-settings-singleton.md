---
id: P2-001
title: Add ENABLE_KNOWLEDGE_WRITE flag, settings, and shared singleton
status: done
kind: strike
phase: 2
heat: integration
priority: 1
blocked_by: []
created: 2026-04-15
updated: 2026-04-15
---

# P2-001: Add ENABLE_KNOWLEDGE_WRITE flag, settings, and shared singleton

## Objective

Añadir el flag de activación `ENABLE_KNOWLEDGE_WRITE` a `Settings` con parseo permisivo, exponer `shared.sim_memory_writer` como singleton opcional, e inicializarlo en la función lifecycle de `shared` reutilizando `shared.db`, `shared.vectors`, `shared.embeddings`. Sin tocar el factory de Phase 1.

## Requirements

- **Settings**: añadir campo `ENABLE_KNOWLEDGE_WRITE: bool = False` al dataclass `Settings` en `shared/shared/settings.py`.
- **Parseo permisivo**: `load_settings()` actualmente hace `overrides[name] = val` sin convertir tipos. Añadir una ruta de parseo específica para el campo bool: cuando `os.environ.get("ENABLE_KNOWLEDGE_WRITE")` exista, convertir con `str(val).strip().lower() in {"1", "true", "yes", "on"}`. Cualquier otro valor (incluido string vacío) → False.
- **Shared singleton**: en `shared/shared/__init__.py`:
  - Añadir `sim_memory_writer: TrackerMemoryWriter | None = None` como module-level var (tras las otras globals como `vectors`, `embeddings`).
  - En la función lifecycle de inicialización (revisar cuál es — probablemente `init_services` o similar), después de construir `vectors`/`embeddings`/`db`, añadir:
    ```python
    global sim_memory_writer
    if settings.ENABLE_KNOWLEDGE_WRITE:
        if vectors is None or embeddings is None or db is None:
            logger.warning(
                "ENABLE_KNOWLEDGE_WRITE=true but infra missing — "
                "Qdrant/Voyage/Postgres not initialised; knowledge writes disabled"
            )
        else:
            from simlab.knowledge import TrackerMemoryWriter  # local import to avoid cycle
            sim_memory_writer = TrackerMemoryWriter(
                vector_store=vectors,
                embedding_service=embeddings,
                db=db,
            )
            logger.info("Knowledge writes enabled (namespace=simulation)")
    ```
  - **Ojo con el ciclo de imports**: `shared` no debe depender de `simlab` a nivel de módulo. El import local dentro de la función es suficiente si se llama tras haber añadido `simlab` al path. Alternativa: mover la import a cuando se invoque la función.
  - **Si el import falla** (p.ej. phase2 no instalada en este contexto): loguear warning y dejar `sim_memory_writer = None`.
- **`.env.example`**: añadir entrada documentada:
  ```
  # Knowledge Backbone — Phase 2 simulation observations (see docs/specs/sim-memory/)
  ENABLE_KNOWLEDGE_WRITE=false
  ```
- **No se modifica `build_writer_from_settings`** ni tests de P1-001/P1-004.

## Acceptance Criteria

- [x] AC1: `Settings(ENABLE_KNOWLEDGE_WRITE=True)` y `Settings()` (default False) son ambos válidos; el dataclass es frozen y el field tiene tipo `bool`.
- [x] AC2: Tests parametrizados (8 truthy + 8 falsy + absent) verifican parsing.
- [x] AC3: Con flag OFF, `shared.sim_memory_writer` permanece `None` tras `_init_sim_memory_writer` (verificado por test).
- [x] AC4: Con flag ON + infra no-None, `shared.sim_memory_writer` queda como `TrackerMemoryWriter` con las 3 instancias reutilizadas (test en `phase2-juan/tests/test_sim_memory_init.py`).
- [x] AC5: Con flag ON pero cualquier servicio None, queda `None` + warning log (test parametrizado en 3 variantes).
- [x] AC6: 27 tests en `shared/` + 112 tests en `phase2-juan/` (1 skipped = integration). Sin regresiones.

## Completion Summary

### What was built
- `shared/shared/settings.py`: añadido `ENABLE_KNOWLEDGE_WRITE: bool = False` + helper `_parse_bool` aceptando `{"1","true","yes","on"}` case-insensitive. `load_settings` ahora convierte tipos bool en vez de pasar el string directo.
- `shared/shared/__init__.py`: nueva global `sim_memory_writer`, función privada `_init_sim_memory_writer(settings)` que reutiliza `shared.vectors/embeddings/db` sin abrir conexiones propias. Llamada desde `init()`. `shutdown()` lo resetea a None.
- `.env.example`: añadidas `ZEROENTROPY_API_KEY` (faltaba) y `ENABLE_KNOWLEDGE_WRITE=false` con comentario apuntando a los specs.
- Tests:
  - `shared/tests/test_settings.py`: +19 parametrizaciones para ENABLE_KNOWLEDGE_WRITE (8 truthy, 8 falsy, absent, default). Fixed `test_defaults` que asertaba `NEO4J_PASSWORD=="labtfg"` en vez del real `"labtfg-neo4j"`.
  - `shared/tests/test_sim_memory_init.py` (nuevo): flag-off, flag-on-without-infra (3 variantes), import-failure.
  - `phase2-juan/tests/test_sim_memory_init.py` (nuevo): happy-path con `TrackerMemoryWriter` real (requiere simlab, no puede vivir en shared/).

### Files created/modified
- `shared/shared/settings.py` — añadir flag + _parse_bool + bool type detection en load_settings.
- `shared/shared/__init__.py` — sim_memory_writer global + _init_sim_memory_writer + shutdown reset.
- `.env.example` — entrada ZEROENTROPY_API_KEY + ENABLE_KNOWLEDGE_WRITE documentada.
- `shared/tests/test_settings.py` — tests del flag + fix del password default.
- `shared/tests/test_sim_memory_init.py` — nuevo (4 escenarios short-circuit).
- `phase2-juan/tests/test_sim_memory_init.py` — nuevo (happy-path).

### Decisions
- **`sim_memory_writer` tipado como `object | None`**: evita ciclo de imports (shared no debe importar simlab a nivel de módulo). El import de `TrackerMemoryWriter` está diferido dentro de `_init_sim_memory_writer`.
- **Función separada `_init_sim_memory_writer`** en vez de inline en `init()`: facilita testing unitario sin levantar Postgres/Qdrant/MinIO reales.
- **Happy-path test en phase2-juan**: `simlab` solo existe en ese entorno; shared cubre únicamente las ramas de short-circuit.
- **Detección de tipo bool en `load_settings`**: usa `dataclasses.fields` + comparación `f.type is bool` / `f.type == "bool"` (cubre el caso `from __future__ import annotations` donde los type hints son strings).
- **Fix colateral**: `test_defaults` tenía `NEO4J_PASSWORD == "labtfg"` (string) pero el real default es `"labtfg-neo4j"`. Fixed en este strike porque estaba en mi camino; pre-existente.

## Files Likely Affected

- `shared/shared/settings.py` — añadir campo + parseo permisivo.
- `shared/shared/__init__.py` — añadir global + lógica en lifecycle.
- `.env.example` — entry nueva documentada.
- `shared/tests/test_settings.py` — test de parseo.
- `shared/tests/test_lifecycle.py` — tests de 3 escenarios (flag OFF, flag ON feliz, flag ON con infra faltante).

## Context

Phase spec: `docs/specs/sim-memory/phase-2-integration.md` (R1, R2)
General spec: `docs/specs/sim-memory/general.md`
Heat: `integration`
