---
id: P1-002
title: Orchestrator wiring of retrieve_context tool
status: done
kind: strike
phase: 1
heat: wiring
priority: 2
blocked_by: [P1-001]
created: 2026-04-17
updated: 2026-04-25
---

# P1-002: Orchestrator wiring of retrieve_context tool

## Objective

Registrar `RETRIEVE_CONTEXT_TOOL` en el tool registry del Orchestrator y enlazar su handler. Respeta el flag: si `ENABLE_KNOWLEDGE_READ=False` (default), ni el tool schema ni el handler aparecen — comportamiento idéntico al actual.

## Requirements

- En `phase2-juan/simlab/orchestrator.py`, dentro de `_build_tools()`:
  - Leer `shared.settings` (o pasar settings al Orchestrator si es más limpio).
  - Si `ENABLE_KNOWLEDGE_READ=True`:
    - Importar `from simlab.recall import RETRIEVE_CONTEXT_TOOL, retrieve_context`.
    - Añadir `RETRIEVE_CONTEXT_TOOL` a la lista `ALL_TOOLS` retornada.
    - Añadir handler al registry:
      ```python
      async def retrieve_context_handler(params: dict) -> str:
          return await retrieve_context(
              query=params["query"],
              namespace=params.get("namespace"),
              top_k=params.get("top_k", 5),
              stage="phase2-orchestrator",
          )
      registry["retrieve_context"] = retrieve_context_handler
      ```
  - Si `ENABLE_KNOWLEDGE_READ=False`: no se importa nada (import local dentro del if para evitar el coste si flag OFF), no se añade tool ni handler — comportamiento actual intacto.
- Añadir sección al `ORCHESTRATOR_SYSTEM_PROMPT` (solo cuando el flag está ON) que describe la tool y cuándo usarla: "If the user asks about scientific concepts, paradigms, authors, papers, or prior simulations, call `retrieve_context` first to ground your answer in real knowledge."
- **No tocar** Architect/Analyst/Reporter — eso es P1-003.

## Acceptance Criteria

- [x] AC1: Con `ENABLE_KNOWLEDGE_READ=False`, `Orchestrator()._build_tools()` retorna la misma lista de tools que antes (verificable por snapshot).
- [x] AC2: Con flag ON y mocks de infra, la lista incluye exactamente una entrada más con `name="retrieve_context"`; el registry tiene una clave `"retrieve_context"` callable.
- [x] AC3: El handler llama a `simlab.recall.retrieve_context` con los parámetros mapeados correctamente (`query`, `namespace`, `top_k`, `stage="phase2-orchestrator"`).
- [x] AC4: El `ORCHESTRATOR_SYSTEM_PROMPT` efectivo (el que el agent loop envía) incluye la mención de `retrieve_context` cuando flag ON; no la incluye cuando OFF.
- [x] AC5: Los 115+27 tests existentes siguen verdes.

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — modificar `_build_tools()` + `ORCHESTRATOR_SYSTEM_PROMPT` build path.

## Context

Phase spec: `docs/specs/sim-recall/phase-1-context-retrieval.md` (R3)
General spec: `docs/specs/sim-recall/general.md`
Heat: `wiring`
Depende de P1-001 (wrapper + schema + factory).

## Completion Summary

**Commit:** `ef25914` — feat[sim-recall]: P1-002 wire retrieve_context into Orchestrator

### What was built
- Conditional `RETRIEVE_CONTEXT_TOOL` + handler in `_build_tools()` (lazy import, zero cost when flag off)
- `_build_system_prompt()` method — appends Knowledge Backbone section when flag on
- Defensive `params.get("query")` guard for malformed LLM calls
- Settings loaded once per `chat()` call, passed to both methods (simplifier improvement)
- 7 tests covering all 5 acceptance criteria

### Files created/modified
- `phase2-juan/simlab/orchestrator.py` — `_build_system_prompt()`, extended `_build_tools()`, `load_settings` import
- `phase2-juan/tests/recall/test_orchestrator_wiring.py` — 7 new tests

### Decisions
- Settings passed as parameter to `_build_tools(settings)` and `_build_system_prompt(settings)` to avoid double `load_settings()` call (simplifier suggestion)
- Defensive `.get("query")` instead of `params["query"]` — reviewer caught potential KeyError on malformed LLM calls
