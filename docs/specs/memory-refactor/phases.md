# memory-refactor — Phase Breakdown

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> References: [general.md](general.md) · [`docs/memory-system.md`](../../memory-system.md)

## Phases

- [ ] **Phase 0: Stop lying** — Restore deterministic, comparable eval signal so subsequent phases can be measured. Fix model/cost mismatch, wire (or delete) the eval phase knob, seed canonical KG between runs, cap unbounded `run_ids` array, kill the SQLite split-brain registry.
  - Dependencies: none
  - Estimated issues: 5
  - Maps to: A8, A12, A13, A10, A11

- [ ] **Phase 1: Canonical IDs at extraction** — Inject `canonical-paradigms.json` into the LLM extraction prompts as a constrained vocabulary. Make slug-like fields Pydantic `Literal[...]`. Route the `__NEW__` escape through the existing merger, then delete the merger and the calibration scripts. Kills three failing eval suites at once.
  - Dependencies: Phase 0 (need eval determinism + correct model + KG resets to verify the fix)
  - Estimated issues: 4
  - Maps to: A1

- [ ] **Phase 2: Retrieve latency** — Cut `retrieve_knowledge` p95 from 14–20s to ≤2.5s. Conditional CRAG, NER skip on confident dense hits, batched `touch_memory`, distinguish CRAG-grader errors from genuine AMBIGUOUS verdicts.
  - Dependencies: Phase 1 (Phase 1 changes which queries hit CRAG — measure new latency baseline before tuning)
  - Estimated issues: 4
  - Maps to: A4, A5

- [ ] **Phase 3: Data integrity** — Single source of truth for confidence (Postgres). Stop drift between PG and Qdrant payload. Define and apply per-store retention policies.
  - Dependencies: Phase 2 (P3 may add a PG round-trip to retrieve; needs P2's latency budget headroom)
  - Estimated issues: 3
  - Maps to: A6, A14

- [ ] **Phase 4: Strategic refactors** — Drop module-level `shared` singletons in favor of a `Services` context. Collapse Qdrant collections; move `kg_entities_dense` to Neo4j native vector index. Split the `memories` table by phase. Designate Postgres `memories` as single temporal source of truth, replicate read-only into Neo4j.
  - Dependencies: Phase 3 (need confidence consolidated before splitting/replicating)
  - Estimated issues: 4
  - Maps to: A7, A9, A2, A3
  - **Deferrable past TFG submission** if time is tight

## Execution notes

- Phases are strictly sequential because each unblocks the *measurement*
  of the next. Within a phase, issues are heat-grouped for parallel
  `/strike` execution (see each phase spec for the parallelism diagram).
- After P0+P1+P2 the failing eval suites are green and retrieve latency
  is in budget. That alone is the minimum viable refactor for the TFG.
- P3 and P4 are sustainability/architecture work. Worth doing, not
  blocking the TFG submission.
