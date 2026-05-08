# memory-refactor — General Specification

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> Source: [`docs/memory-system.md`](../../memory-system.md) (architectural critique A1–A14)

## Overview

Coordinated, phased refactor of the labTFG persistent memory system
(Postgres + Neo4j + Qdrant + MinIO + SQLite). The current state has
six failing eval suites on 2026-05-08, structural latency in
`retrieve_knowledge` (p95 = 14–20s vs 2.5s budget), and a merge step that
exists only because identity is solved one layer too late. The refactor
fixes the failing tests at root, then unwinds the structural debt that
made them possible.

## Core Features

- **Stop the false-signal eval runs** — three identical merge-quality
  reports today proved the eval harness's "phase" knob isn't wired.
  Restore deterministic, comparable runs before any other fix.
- **Eliminate post-hoc merging** by injecting `canonical-paradigms.json`
  into the LLM extraction prompts as a constrained vocabulary
  (Pydantic `Literal[...]` + `__NEW__` escape). Kills three failing
  eval suites simultaneously and removes a Sonnet call per entity.
- **Cut `retrieve_knowledge` p95 to ≤ 2.5s** by making CRAG conditional
  on rerank confidence, skipping Haiku NER when dense retrieval is
  confident, batching `touch_memory` writes, and distinguishing
  CRAG-grader errors from genuine AMBIGUOUS verdicts.
- **Single source of truth for confidence** — replace the partial
  Postgres↔Qdrant sync with one helper that updates atomically, or
  drop confidence from Qdrant payload entirely and read from PG at
  retrieval time.
- **Per-store retention policies** — MinIO bucket lifecycle, eval `runs`
  archival, Qdrant TTL on artifacts, KG `Reflection` rollup.
  Required for the system to remain sustainable past 6 months of CI.
- **Strategic refactors (deferrable)** — drop module-level
  `shared.kg/vectors/embeddings` singletons in favor of a `Services`
  context object; collapse `artifacts_dense/sparse` and move
  `kg_entities_dense` to Neo4j's native vector index; split the
  overloaded `memories` table; designate Postgres `memories` as the
  single temporal source of truth and replicate read-only into Neo4j.

## Out of Scope

- New paradigms / new pipeline stages — orthogonal.
- Phase 1 ↔ Phase 2 contract changes that aren't directly required
  by the refactors above (e.g. DecisionModel duck-typing, agent
  count, environment specs).
- TFG memoria writing.
- Re-architecting the Memory Agent's per-stage extraction structure
  beyond the model-choice decision (A8) and the Literal-slug change
  (A1). The 4-stage pipeline (researcher / formalizer / reasoner /
  builder) stays.
- Migrating Neo4j to a managed offering, replacing Qdrant with another
  vector DB, or changing Voyage / ZeroEntropy / Anthropic providers.

## Data Model

No new fundamental entities. Schema-level changes per phase:

- **P0** — drop `Paradigm.run_ids` array, add new
  `node_run_observations(node_id, label, run_id, observed_at)` table in
  Postgres; delete `data/labtfg.db` SQLite tables (functionality moves
  to existing Postgres `experiments`).
- **P1** — `canonical-paradigms.json` becomes a runtime-loaded
  constant; `_SLUG_LIKE_LABELS` become `Literal[...]` Pydantic types
  in `decisionlab.knowledge.extraction._Extraction`.
- **P2** — none.
- **P3** — `memories.confidence` becomes the single source of truth;
  Qdrant payload `confidence` field is dropped (or kept read-only).
  New tables for retention bookkeeping (e.g.
  `eval_runs(run_id, suite, archived_at)`).
- **P4** — split `memories` into `pipeline_memories` +
  `simulation_observations`; remove `valid_from/valid_to/confidence`
  from Neo4j relations (carry `memory_id` FK only); collapse
  `artifacts_dense/sparse` Qdrant collections; remove
  `kg_entities_dense` in favor of native Neo4j vector index.

## Integrations

- **Postgres** — primary lifecycle store; alembic migrations
  in `shared/migrations/versions/`.
- **Neo4j** — schema in `shared/shared/knowledge_graph.py`. P4 adds a
  vector index; P4 drops temporal properties from relations.
- **Qdrant** — collections in `shared/shared/vector_store.py`. P3 stops
  writing confidence. P4 removes 2-3 collections.
- **MinIO** — P3 adds bucket lifecycle policy.
- **Voyage AI / ZeroEntropy / Anthropic** — no provider changes; only
  model selection (P0) and call-site changes (P2).

## User Flows

### Flow 1 — Eval suite green-light (after P0 + P1)

1. CI runs `cumulative-growth.yaml` on a fresh KG seeded with
   `canonical-paradigms.json`.
2. Researcher emits `Paradigm.slug` from the canonical Literal set,
   never minting `q-eligibility-traces` when `reinforcement-learning`
   already exists.
3. `slug-accuracy.yaml` re-runs; passes 8/8.
4. `merge-quality.yaml` is **deleted**; the merger it tested no longer
   exists.

### Flow 2 — Retrieve under load (after P2)

1. Agent calls `retrieve_knowledge(query)`.
2. Dense retrieval returns top hits with rerank scores ≥ 0.5.
3. CRAG is skipped; results pass through with no Haiku call.
4. `touch_memory` updates batched into a single `UPDATE ... WHERE id IN (...)`.
5. Total wall time ≤ 2.5s p95.

### Flow 3 — Confidence corroboration (after P3)

1. Memory Agent classifies a fact as CORROBORATION of an existing memory.
2. `update_memory_confidence(id, +0.05)` updates Postgres only.
3. Retrieve-time confidence factor is fetched from Postgres, not Qdrant payload.
4. Sparse/dense channels can no longer drift.

## Constraints & Non-Functional Requirements

- **Reversibility**: each phase reversible via single `git revert`
  before subsequent phases land. No destructive migrations without
  backup migration in the same alembic revision.
- **Cost predictability**: P0 fixes the model-choice doc/code mismatch
  (A8) — after P0, eval cost per topic is stable.
- **Latency target**: `retrieve_knowledge` p95 ≤ 2.5s after P2.
- **Eval determinism**: after P0, two consecutive runs of any suite on
  the same fixture produce identical KG growth and identical assertion
  outcomes (modulo LLM noise on the canonicalize verifier path; P1
  removes that path entirely).
- **Backwards compatibility**: P0 + P1 + P2 do not change the public
  `retrieve_knowledge` / `retrieve_context` tool schemas — agents
  unchanged.
- **CI gating**: regression alert on merge-quality goes away in P1
  (test deleted). Regression alert on slug-accuracy persists.
- **Storage hygiene** (P3+): MinIO bucket size, Postgres
  `memories` row count, Qdrant point count all stable past 90 days
  given a steady eval cadence.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Project namespace | `memory-refactor` | Cross-cuts existing `sim-memory`, `kg-enrichment`, `knowledge`, `sim-recall` specs — none owns the cross-cutting refactor |
| Phase numbering | P0–P4 (matches the recommended sequence in `memory-system.md`) | Preserves the user's mental model: "Stop lying → root cause → latency → integrity → strategic" |
| Phase boundaries | Each phase blocks the next | P0 deterministic signal needed before measuring P1; P1 root cause must land before P2 timing budget is meaningful; etc. |
| Internal phase parallelism | Heat-based (per A4 spec convention) | Issues in different heats touch different files → can run as separate `/strike` agents in parallel |
| Cost-quality threshold for "split phase" | None split — largest is 5 issues, smallest is 3 | Within `phases.md` red-line guidance (≤10, ≥3) |
| Out-of-band knowledge | Reuse `docs/memory-system.md` | Source of truth for the critique; spec links back instead of duplicating |
| TFG submission risk | P3 + P4 deferrable | If the TFG ships before P3 lands, P0 + P1 + P2 alone deliver green tests + 2.5s retrieval |
