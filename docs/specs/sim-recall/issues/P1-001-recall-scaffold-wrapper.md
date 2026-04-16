---
id: P1-001
title: Settings flag, recall module scaffold, and retrieve_context wrapper
status: todo
kind: strike
phase: 1
heat: core
priority: 1
blocked_by: []
created: 2026-04-17
updated: 2026-04-17
---

# P1-001: Settings flag, recall module scaffold, and retrieve_context wrapper

## Objective

Crear el paquete `simlab/recall/` con el wrapper `retrieve_context`, el tool schema y la factory `build_retriever_from_settings`. Añadir el flag `ENABLE_KNOWLEDGE_READ` a `shared.Settings`. Sin tocar el Orchestrator ni los agentes — eso vive en P1-002 y P1-003.

## Requirements

- Añadir a `shared/shared/settings.py` el campo `ENABLE_KNOWLEDGE_READ: bool = False`, parseo permisivo idéntico al de `ENABLE_KNOWLEDGE_WRITE`.
- Actualizar `.env.example` con la nueva variable + comentario.
- Crear `phase2-juan/simlab/recall/__init__.py` exportando la API pública.
- Crear `phase2-juan/simlab/recall/retrieve.py` con:
  - Constante `RETRIEVE_CONTEXT_TOOL` (dict Anthropic-tool-schema) tal como en la spec R3.
  - Función `async def retrieve_context(*, query, namespace=None, top_k=5, as_of=None, stage="phase2", run_id=None) -> str`:
    - Si `ENABLE_KNOWLEDGE_READ=False` → retorna `"## Retrieved Knowledge (0 results)\n\nNo results found."` sin más trabajo.
    - Si falta infra (`shared.vectors`/`shared.embeddings`/`shared.kg` todos None) → mismo string "0 results".
    - Si infra presente: construye un handler con `decisionlab.knowledge.retrieval.tool.create_retrieve_knowledge(kg=shared.kg, vector_store=shared.vectors, embedding_service=shared.embeddings, search_adapter=None, client=<build Anthropic client from settings>, run_id=<uuid.uuid4() si no se pasó>, stage=stage)` y llama al handler con `{"query": query, "namespace": namespace, "top_k": top_k, "as_of": as_of}`.
    - Try/except global: cualquier excepción devuelve el string "0 results" y loguea `logger.exception`.
  - Factory `async def build_retriever_from_settings(settings) -> Callable | None` — análoga a la de sim-memory; retorna `None` si el flag está OFF o falta infra. Útil para tests e integración Phase 2.
- Crear `phase2-juan/tests/recall/__init__.py` vacío.
- Crear `phase2-juan/tests/recall/test_scaffold.py` con 3 tests mínimos:
  - Imports públicos funcionan.
  - `retrieve_context(...)` con flag OFF retorna "0 results" string sin llamar a ninguna función mockeable de Pablo.
  - `RETRIEVE_CONTEXT_TOOL` es dict serializable JSON con las keys requeridas por la Anthropic tool API.

## Acceptance Criteria

- [ ] AC1: `from simlab.recall import retrieve_context, RETRIEVE_CONTEXT_TOOL, build_retriever_from_settings` funciona.
- [ ] AC2: `retrieve_context(query="test")` con `ENABLE_KNOWLEDGE_READ=False` (default) retorna el string "0 results" inmediatamente, sin llamar a `decisionlab.*` ni tocar `shared.*`.
- [ ] AC3: El tool schema cumple el shape Anthropic (`name`, `description`, `input_schema` con `type`, `properties`, `required`).
- [ ] AC4: `build_retriever_from_settings` retorna `None` si el flag está OFF o si falta infra; `callable` si todo está listo.
- [ ] AC5: Los 3 tests del scaffold pasan. No rompe los 115+27 tests existentes.

## Files Likely Affected

- `shared/shared/settings.py` — campo + parsing.
- `.env.example` — entrada nueva.
- `phase2-juan/simlab/recall/__init__.py` — nuevo.
- `phase2-juan/simlab/recall/retrieve.py` — nuevo.
- `phase2-juan/tests/recall/__init__.py` — nuevo.
- `phase2-juan/tests/recall/test_scaffold.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-recall/phase-1-context-retrieval.md` (R1, R2, R3, R7)
General spec: `docs/specs/sim-recall/general.md`
Heat: `core`
