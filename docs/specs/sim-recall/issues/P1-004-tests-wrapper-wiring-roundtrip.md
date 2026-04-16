---
id: P1-004
title: Tests — wrapper unit, agent wiring, and sim-memory→sim-recall roundtrip
status: todo
kind: strike
phase: 1
heat: tests
priority: 3
blocked_by: [P1-002, P1-003]
created: 2026-04-17
updated: 2026-04-17
---

# P1-004: Tests — wrapper unit, agent wiring, and sim-memory→sim-recall roundtrip

## Objective

Cubrir Phase 1 con tres niveles de test: unit del wrapper con mocks, hook tests del wiring en Orchestrator y agentes (verificando que el flag manda), e integration test end-to-end que demuestra el loop sim-memory write → sim-recall read.

## Requirements

### R1: Unit tests del wrapper

`phase2-juan/tests/recall/test_retrieve.py`:
- Con flag OFF → retorna "0 results" inmediatamente; no import de `decisionlab.*`, no touch de `shared.*`.
- Con flag ON + `shared.vectors=None` (infra caída) → 0 results, loguea warning, no excepción.
- Con flag ON + mocks de infra → llama a `decisionlab.knowledge.retrieval.tool.create_retrieve_knowledge` con los kwargs correctos (kg, vector_store, embedding_service, client, run_id, stage).
- Con flag ON + mock que raise → captura, loguea `exception`, retorna "0 results".
- Parámetros opcionales (`namespace=None`, `as_of=None`) se propagan correctamente.

### R2: Orchestrator wiring tests

`phase2-juan/tests/recall/test_orchestrator_tool.py`:
- Snapshot: con flag OFF, la lista de tools del Orchestrator es idéntica a la de main (test boundary: len y nombres).
- Con flag ON: la lista incluye `retrieve_context` (1 entrada más); el registry tiene la clave callable.
- El system prompt efectivo incluye la sección "Knowledge Backbone access" solo con flag ON.
- Invocar el handler registrado (con `simlab.recall.retrieve_context` mockeado) llama al mock con `stage="phase2-orchestrator"`.

### R3: Agent wiring tests

`phase2-juan/tests/recall/test_agent_wiring.py`:
- Para cada uno de Architect/Analyst/Reporter:
  - Con flag OFF: construcción estándar, sin `extra_tools`; prompt es el original.
  - Con flag ON: la tool aparece en la lista pasada al `run_agent_loop`; el prompt incluye la sección condicional esperada (substring assert).

### R4: Integration test — sim-memory → sim-recall roundtrip

`tests/integration/test_sim_recall_roundtrip.py` (usa fixtures top-level de Pazos):
- Marked `@pytest.mark.integration`.
- Setup: `settings`, `db_service`, `vector_store`, `session` vienen del conftest.
- Flow:
  1. Construye `TrackerMemoryWriter` (sim-memory) y escribe 3 memories con un `paradigm_slug` único (p.ej. `recall-e2e-{uuid}`).
  2. Invoca `simlab.recall.retrieve_context(query=f"what happened to paradigm {paradigm_slug}", namespace="simulation")` — nota que Phase 2 escribe al namespace `simulation`, Feature 1 principalmente consulta `paradigm`, pero este test usa `simulation` para verificar el loop completo.
  3. Verifica que el string retornado contiene el `paradigm_slug` (nuestra memoria fue recuperada).
  4. Verifica que el formato es el esperado ("## Retrieved Knowledge (N results)").
  5. Cleanup: borra filas y points.
- **Este es el único test que demuestra el contrato cross-feature sim-memory ↔ sim-recall.**

### R5: Cross-stack import smoke test

- Verificar que importar `simlab.recall` desde `tests/` funciona (el path dep está correctamente declarado). Ya quedó implícito tras sim-memory's setup pero re-verificar.

## Acceptance Criteria

- [ ] AC1: Unit tests del wrapper pasan sin infra (5+ casos cubriendo flag off, infra off, mock normal, mock raise, params opcionales).
- [ ] AC2: Orchestrator wiring tests pasan con mocks (flag off/on combos).
- [ ] AC3: Agent wiring tests pasan para los 3 agentes.
- [ ] AC4: El integration test recupera lo que sim-memory escribió, probando el loop end-to-end.
- [ ] AC5: Los 115+27 tests previos siguen verdes (no regresiones).

## Files Likely Affected

- `phase2-juan/tests/recall/test_retrieve.py` — nuevo.
- `phase2-juan/tests/recall/test_orchestrator_tool.py` — nuevo.
- `phase2-juan/tests/recall/test_agent_wiring.py` — nuevo.
- `tests/integration/test_sim_recall_roundtrip.py` — nuevo (usa fixtures de top-level).

## Context

Phase spec: `docs/specs/sim-recall/phase-1-context-retrieval.md` (R8)
General spec: `docs/specs/sim-recall/general.md`
Heat: `tests`
Depende de P1-002 AND P1-003 (para poder verificar wiring real).
