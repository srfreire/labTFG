# memory-refactor — Phase Breakdown

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> References: [general.md](general.md) · [`docs/memory-system.md`](../../memory-system.md)

## Phases

- [x] **Phase 0: Stop lying** — Restore deterministic, comparable eval signal so subsequent phases can be measured. Fix model/cost mismatch, delete the unwired merge-quality suite, seed canonical KG between runs, cap unbounded `run_ids` array, kill the SQLite split-brain registry.
  - Dependencies: none
  - Issues: P0-001, P0-002, P0-003, P0-004, P0-005
  - Heats: extraction-model (P0-001), merge-quality-eval (P0-002), slug-accuracy-eval (P0-003), kg-schema (P0-004), registry (P0-005) — all 5 independent, max-4 parallel via hydra
  - Maps to: A8, A12, A13, A10, A11

- [x] **Phase 1: Canonical IDs at extraction** — Inject `canonical-paradigms.json` into the LLM extraction prompts as a constrained vocabulary; lock slug-like fields to Pydantic `Literal[...]`; route the `__NEW__` escape through the existing merger only when the LLM opts out; then delete the merger and the τ-calibration script.
  - Dependencies: Phase 0 (need eval determinism + correct model + KG resets to verify the fix)
  - Issues: P1-001 → P1-002 → P1-003 → P1-004 (single sequential chain)
  - Heats: extraction (one heat, 4 sequential issues — touches `extraction.py` / `memory_agent.py` / `canonicalize.py` together)
  - Hydra wave: 1 head at a time
  - Maps to: A1

- [x] **Phase 2: Retrieve latency** — Cut `retrieve_knowledge` p95 from 14–20s to ≤2.5s. Conditional CRAG, NER skip on confident dense hits, batched `touch_memory`, distinguish CRAG-grader errors from genuine AMBIGUOUS verdicts.
  - Dependencies: Phase 1 (Phase 1 changes which queries hit CRAG — measure new latency baseline before tuning)
  - Issues: P2-001, P2-002, P2-003, P2-004
  - Heats: crag-grader (P2-001 → P2-004, sequential), ner (P2-002, independent), db-batching (P2-003, independent)
  - Hydra wave 1: 3 parallel (P2-001, P2-002, P2-003); wave 2: P2-004
  - Maps to: A4, A5

- [x] **Phase 3: Data integrity** — Single source of truth for confidence (Postgres). Stop drift between PG and Qdrant payload. Define and apply per-store retention policies.
  - Dependencies: Phase 2 (P3 may add a PG round-trip to retrieve; needs P2's latency budget headroom)
  - Issues: P3-001, P3-002, P3-003
  - Heats: confidence (P3-001 → P3-002, sequential), retention (P3-003, independent)
  - Hydra wave 1: 2 parallel (P3-001, P3-003); wave 2: P3-002
  - Maps to: A6, A14

- [x] **Phase 4: Strategic refactors** — Drop module-level `shared` singletons in favor of a `Services` context. Collapse Qdrant collections; move `kg_entities_dense` to Neo4j native vector index. Split the `memories` table by phase. Designate Postgres `pipeline_memories` as single temporal source of truth, replicate read-only into Neo4j.
  - Dependencies: Phase 3 (need confidence consolidated before splitting/replicating)
  - Issues: P4-001, P4-002, P4-003, P4-004
  - Heats: infra (P4-001, independent), vectors (P4-002, independent), data-model (P4-003 → P4-004, sequential)
  - Hydra wave 1: 3 parallel (P4-001, P4-002, P4-003); wave 2: P4-004
  - Maps to: A7, A9, A2, A3
  - **Deferrable past TFG submission** if time is tight

## Execution notes

- Phases are strictly sequential because each unblocks the *measurement*
  of the next. Within a phase, issues are heat-grouped for parallel
  hydra execution (see each phase spec for the parallelism diagram).
- After P0+P1+P2 the failing eval suites are green and retrieve latency
  is in budget. That alone is the minimum viable refactor for the TFG.
- P3 and P4 are sustainability/architecture work. Worth doing, not
  blocking the TFG submission.
- All 20 issues across 5 phases now forged. Ready for hydra dispatch.
