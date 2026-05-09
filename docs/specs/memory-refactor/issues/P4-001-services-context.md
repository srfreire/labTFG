---
id: P4-001
title: Replace shared module-level singletons with a Services context object
status: done
kind: strike
phase: 4
heat: infra
priority: 2
blocked_by: [P3-002, P3-003]
created: 2026-05-08
updated: 2026-05-09
---

# P4-001: Services context replaces shared singletons

## Objective

Drop the module-level `shared.kg`, `shared.vectors`, `shared.embeddings`,
`shared.db`, `shared.storage`, `shared.sim_memory_writer` globals.
Replace with a `Services` dataclass passed explicitly through entry
points. Removes the test-seam workarounds (`_get_kg`,
`_get_vector_store`, `_get_embedding_service`) that exist solely to
support monkeypatching, and resolves the Phase 1 ↔ Phase 2 import
cycle in `_init_sim_memory_writer`.

## Requirements

Per phase spec R1:

1. Create `shared/shared/services.py`:
   ```python
   @dataclass(frozen=True)
   class Services:
       db: DatabaseService
       storage: StorageService
       kg: KnowledgeGraph | None
       vectors: VectorStore | None
       embeddings: EmbeddingService | None
       sim_memory_writer: object | None = None
   ```
2. Add `init_services(settings) -> Services` and
   `shutdown_services(services)` factory functions, replacing
   `shared.init` / `shared.shutdown`.
3. Wire `Services` through every entry point:
   - `phase1-pablo/src/decisionlab/server.py` (FastAPI lifespan).
   - `phase1-pablo/src/decisionlab/cli.py`.
   - `phase1-pablo/src/decisionlab/cli_eval.py`.
   - `phase2-juan/simlab/api.py`.
   - `phase2-juan/simlab/cli.py` (or wherever main lives).
4. Update every consumer to take `services: Services` as a parameter
   (or as a closure-captured argument in tool factories like
   `create_retrieve_knowledge`).
5. Remove the test seams `_get_kg`, `_get_vector_store`,
   `_get_embedding_service` — they were proxies for the globals.
   Tests now construct `Services(kg=FakeKG(), ...)` directly.
6. Resolve the import cycle: move `_init_sim_memory_writer` out of
   `shared/__init__.py`. The Phase 2 entrypoint constructs its own
   `TrackerMemoryWriter` from a `Services` it received.
7. Delete `shared.init`, `shared.shutdown`, and the module-level
   globals in `shared/__init__.py` — final commit. Optional:
   `shared/__init__.py` becomes empty or just re-exports.

## Acceptance Criteria

- [x] AC1: `Services` dataclass + `init_services` / `shutdown_services`
      exist; documented in `shared/shared/services.py`.
- [x] AC2: Every entry point (Phase 1 + Phase 2 servers, CLIs)
      constructs `Services` once and threads it down. No `import
      shared; shared.kg` reads remain anywhere — `grep -rn
      'shared\.kg\|shared\.vectors\|shared\.embeddings\|shared\.db\|shared\.storage'`
      returns no live read.
- [x] AC3: Test seams (`_get_kg`, `_get_vector_store`,
      `_get_embedding_service`) deleted. Tests construct `Services`
      directly with fakes.
- [x] AC4: `_init_sim_memory_writer` no longer lives in
      `shared/__init__.py`. The Phase 1 ↔ Phase 2 import cycle is
      gone.
- [x] AC5: Full eval suite (smoke + cumulative-growth +
      slug-accuracy) green. Phase 2 web app + CLI smoke-test pass.

## Files Likely Affected

- `shared/shared/services.py` — new.
- `shared/shared/__init__.py` — drop globals, drop init/shutdown.
- `shared/shared/database.py`, `storage.py`, `knowledge_graph.py`,
  `vector_store.py`, `embedding.py` — unchanged structurally.
- Every Phase 1 + Phase 2 entry point (server/cli/api).
- Every consumer that reads `shared.kg/vectors/embeddings` (audit
  via grep).
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` —
  `_get_embedding_service` / `_get_vector_store` removed; deps
  passed in.
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` —
  factory closure captures `Services`.

## Context

Phase spec: `docs/specs/memory-refactor/phase-4-strategic-refactors.md` (R1)
Heat: `infra` (independent of P4-002 / P4-003)

## Completion Summary

### What was built

- `shared/shared/services.py` — `Services` (frozen dataclass: `db`, `storage`,
  `kg`, `vectors`, `embeddings`, `sim_memory_writer`) + `init_services` /
  `shutdown_services`.
- `shared/__init__.py` reduced to an empty docstring — module-level globals
  and `init`/`shutdown` deleted.
- `simlab.knowledge.build_writer_from_services` builds the Phase 2 sim-memory
  writer from a `Services`. Phase 2 `api.py` lifespan calls it and threads
  through via `dataclasses.replace(services, sim_memory_writer=writer)` —
  resolves the Phase 1 ↔ Phase 2 import cycle.
- Every entry point (`phase1-pablo/src/decisionlab/server.py`, `cli.py`,
  `cli_eval.py`, `phase2-juan/simlab/api.py`, scripts) now boots services
  via `init_services()` and threads them through.
- Every consumer (Router, Researcher/Formalizer/Reasoner/Builder + sub-
  agents, MemoryAgent, kg_writer, kg_retrieval, retrieval/tool, eval/*,
  Orchestrator, recall/retrieve, charts/tools/nlsql/reporter/analyst,
  feedback/feedback_port/web_feedback, tools/{files,reports,tests},
  artifacts) accepts explicit deps (`services` or individual `db`/`storage`/
  `kg`/`vectors`/`embeddings` parameters).
- Test seams removed: `_get_kg`, `_get_vector_store`,
  `_get_embedding_service`, `_get_db`. Tests construct `Services` /
  fakes directly.

### Files created/modified

- `shared/shared/services.py` — new module.
- `shared/shared/__init__.py` — emptied.
- `shared/shared/artifacts.py` — `register_artifact` takes `db`.
- ~80 source files across `phase1-pablo/src/`, `phase2-juan/simlab/`,
  `scripts/` — refactored to accept services / explicit deps.
- ~50 test files updated — drop monkeypatched seams, build `Services`
  directly. `tests/conftest.py` gains a `services` fixture; legacy
  `shared_initialized` fixture removed.

### Decisions

- Lower-level utility functions (`populate_kg`, `_record_node_run_observation`)
  take individual deps (`db`, `embeddings`, `vectors`) as kw-only — easier
  for tests to pass mocks without wrapping in a full `Services`.
- Higher-level facades (`Router`, `Orchestrator`, `Researcher`) take the
  full `Services` (or strict subset) so call sites stay terse.
- `_get_legacy_services` helper used during transition to bridge api.py
  was deleted in the final commit alongside the shim — no transitional
  scaffolding left.

### Verification

```
phase1-pablo: 930 passed, 12 skipped, 42 deselected (integration)
phase2-juan:  167 passed,    2 deselected (integration)
shared:        32 passed,  115 deselected (integration)
ruff: All checks passed!
```

`grep` for live `shared.{kg,vectors,embeddings,db,storage,sim_memory_writer,init,shutdown}`
reads in production code returns zero matches (only legitimate
`from shared.<submodule> import X` remains).
