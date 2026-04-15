---
id: P2-001
title: Add ENABLE_KNOWLEDGE_WRITE flag, settings, and shared singleton
status: todo
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

- [ ] AC1: `Settings(ENABLE_KNOWLEDGE_WRITE=True)` y `Settings()` (default False) son ambos válidos; el dataclass es frozen y el field tiene tipo `bool`.
- [ ] AC2: Test parametrizado verifica parsing: `"true"`, `"TRUE"`, `"1"`, `"yes"`, `"on"` → True; `"false"`, `"0"`, `""`, `"nope"`, ausente → False.
- [ ] AC3: Con flag OFF (o default), `shared.sim_memory_writer` permanece `None` tras lifecycle init (sin log spam).
- [ ] AC4: Con flag ON + `shared.db/vectors/embeddings` mockeados no-None, `shared.sim_memory_writer` queda como `TrackerMemoryWriter` tras init, con los 3 servicios inyectados.
- [ ] AC5: Con flag ON pero `shared.vectors is None` (p.ej. Qdrant no conectado), queda `None` + warning log emitido.
- [ ] AC6: Los 111 tests de phase2 y los tests actuales de shared siguen verdes.

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
