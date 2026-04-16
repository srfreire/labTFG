---
id: P1-002
title: Orchestrator wiring of retrieve_context tool
status: todo
kind: strike
phase: 1
heat: wiring
priority: 2
blocked_by: [P1-001]
created: 2026-04-17
updated: 2026-04-17
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

- [ ] AC1: Con `ENABLE_KNOWLEDGE_READ=False`, `Orchestrator()._build_tools()` retorna la misma lista de tools que antes (verificable por snapshot).
- [ ] AC2: Con flag ON y mocks de infra, la lista incluye exactamente una entrada más con `name="retrieve_context"`; el registry tiene una clave `"retrieve_context"` callable.
- [ ] AC3: El handler llama a `simlab.recall.retrieve_context` con los parámetros mapeados correctamente (`query`, `namespace`, `top_k`, `stage="phase2-orchestrator"`).
- [ ] AC4: El `ORCHESTRATOR_SYSTEM_PROMPT` efectivo (el que el agent loop envía) incluye la mención de `retrieve_context` cuando flag ON; no la incluye cuando OFF.
- [ ] AC5: Los 115+27 tests existentes siguen verdes.

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — modificar `_build_tools()` + `ORCHESTRATOR_SYSTEM_PROMPT` build path.

## Context

Phase spec: `docs/specs/sim-recall/phase-1-context-retrieval.md` (R3)
General spec: `docs/specs/sim-recall/general.md`
Heat: `wiring`
Depende de P1-001 (wrapper + schema + factory).
