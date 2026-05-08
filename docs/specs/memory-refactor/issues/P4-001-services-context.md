---
id: P4-001
title: Replace shared module-level singletons with a Services context object
status: todo
kind: strike
phase: 4
heat: infra
priority: 2
blocked_by: [P3-002, P3-003]
created: 2026-05-08
updated: 2026-05-08
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

- [ ] AC1: `Services` dataclass + `init_services` / `shutdown_services`
      exist; documented in `shared/shared/services.py`.
- [ ] AC2: Every entry point (Phase 1 + Phase 2 servers, CLIs)
      constructs `Services` once and threads it down. No `import
      shared; shared.kg` reads remain anywhere — `grep -rn
      'shared\.kg\|shared\.vectors\|shared\.embeddings\|shared\.db\|shared\.storage'`
      returns no live read.
- [ ] AC3: Test seams (`_get_kg`, `_get_vector_store`,
      `_get_embedding_service`) deleted. Tests construct `Services`
      directly with fakes.
- [ ] AC4: `_init_sim_memory_writer` no longer lives in
      `shared/__init__.py`. The Phase 1 ↔ Phase 2 import cycle is
      gone.
- [ ] AC5: Full eval suite (smoke + cumulative-growth +
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
