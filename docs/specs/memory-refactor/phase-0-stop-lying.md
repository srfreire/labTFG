# Phase 0: Stop lying

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08
> References: [general.md](general.md) · [phases.md](phases.md) · [`docs/memory-system.md`](../../memory-system.md) §A8, A10, A11, A12, A13

## Objective

Restore deterministic, comparable eval signal so subsequent phases can
be measured. This phase fixes the things that are currently *lying* to
us: the model used for extraction (doc says Haiku, code uses Sonnet —
costs 10× off); three identical merge-quality eval reports with no
"phase" knob actually wired through; non-deterministic slug-accuracy
runs that inherit each other's KG state; an unbounded `run_ids` array
that masks node-level provenance noise; a SQLite + Postgres dual
registry that can drift silently.

After P0, the failing test reports mean what they say.

## Requirements

### R1 — Align extraction model choice (A8)

`decisionlab.structured.DEFAULT_MODEL` is `"anthropic/claude-sonnet-4.6"`
today. `docs/knowledge-architecture.md` claims extraction uses Haiku
(~$0.001 per call). The eval JSON reports (e.g.
`2026-05-07-paradigm-canonicalization/report.json`) show ~30k+30k
Sonnet 4.6 tokens per topic — code-side reality is Sonnet.

Decision: pick **one** of {Haiku, Sonnet} for extraction; align the
other side. Recommendation: **Haiku** for `extraction.extract` (the
prompts are formulaic, classification-style); keep Sonnet for
`resolver._classify_conflict` (genuinely needs reasoning). Resolver
already uses `_STRUCTURED_MODEL` so we cannot just lower the global
default — needs a per-call-site model parameter.

Edge cases:
- The structured-output path uses forced tool-use, which Haiku 4.5
  supports.
- `_pre_anchor` Haiku call already exists in `router.py:802` — reuse
  the same model constant if possible.
- The `decisionlab.config.SETTINGS.knowledge_fast_model` env var
  (`DECISIONLAB_KNOWLEDGE_FAST_MODEL`) already names Haiku — extend
  its scope to extraction.

### R2 — Wire eval `phase` knob through to `_verify_merge`, or delete duplicate suites (A12)

Three reports on 2026-05-08 (08:20, 08:30, 08:44) all produced
**bit-identical** numbers (`tp=3, fp=0, fn=7, tn=8`). The "phase"
identifier is in the directory name only; the eval runner does not
plumb anything to `canonicalize._verify_merge`.

Decision: since Phase 1 deletes the merger entirely (A1), the lowest-
risk path is to **delete the duplicate `*-merge-quality` report directories
and the suite-level phase artifact**. If the user wants to keep the
suite alive temporarily as a regression alarm until P1 lands, instead
add a real `phase` field to `merge_precision_recall` args, validate
it's read inside `_verify_merge`, and surface the value in the report
JSON so identical-output bugs are visible at a glance.

Edge cases:
- `evals/reports/*-merge-quality/` directories are tracked outputs;
  deleting them does not affect runtime.
- `evals/suites/merge-quality.yaml` is the suite definition — if we
  delete it now, the `merge-quality` CI step starts erroring on
  "suite not found". Coordinate with R5 of P1 (delete merger).

### R3 — Reset KG between slug-accuracy runs + seed canonicals (A13)

`evals/suites/slug-accuracy.yaml` has `reset_kg_before: false`. Two runs
the same day (10:39, 13:56) produced different hit rates (7/8 vs 4/8)
on the same fixture because phase4 inherited phase3's KG residue.

Decision: change `reset_kg_before: true` and run
`seed_canonical_paradigms` (already implemented in
`decisionlab.knowledge.seed`) before the suite topics. This means the
first topic always starts from the canonical paradigm set as if Phase 1
were already in place — the slug-accuracy assertion is then a *real*
"can the Researcher reuse what's already in the KG" test.

Edge cases:
- `cumulative-growth.yaml` legitimately needs `reset_kg_before: true`
  + empty seed (it's the bootstrap suite). Keep its current behaviour.
- The seed function takes a path; default to
  `evals/fixtures/canonical-paradigms.json`.
- Reset must be a Cypher `MATCH (n) DETACH DELETE n`. Verify the eval
  KG instance is segregated from any prod KG.

### R4 — Cap `run_ids` accumulation on KG nodes (A10)

`shared.knowledge_graph.KnowledgeGraph` has no `run_ids` property in
`_SCHEMA`, but `kg_writer.py:_node_work` writes:

```cypher
ON MATCH SET n += $update_props,
             n.run_ids = coalesce(n.run_ids, []) + $run_id
```

Every MERGE appends. After 100 runs, popular `Paradigm` nodes carry
100-element arrays serialised on every read.

Decision: replace the array with `run_count` + `last_run_at` on the
node (cheap O(1) update); keep per-run history in a new Postgres table
`node_run_observations(id, label, key_value, run_id, observed_at)`.

Edge cases:
- Existing nodes already carry the array. Migration must:
  1. Read each node's `run_ids` array length → set `run_count`.
  2. Read max array element's index → set `last_run_at` (or fall back
     to `n.updated_at`).
  3. Backfill `node_run_observations` from the existing arrays
     (best-effort; missing `observed_at` per element is OK — set to
     `coalesce(updated_at, now())`).
  4. Remove the `run_ids` property in a follow-up step after callers
     stop reading it.
- Callers reading `n.run_ids` today: search the codebase. (Most
  retrieval code reads `payload.run_id` from Qdrant, not from KG.)

### R5 — Kill SQLite registry (A11)

`shared/store.py` keeps a sync `sqlite3` registry at `data/labtfg.db`
for Phase 2 model + experiment metadata. Postgres has the same tables
(`models`, `experiments`) via SQLAlchemy. The SQLite path is a fallback
"when Phase 2 runs standalone" — but the docker-compose stack always
provides Postgres, and the SQLite root is detected by walking up
looking for `CLAUDE.md`, which silently fails in containers.

Decision: delete `shared/store.py`. Migrate every caller to the
existing async Postgres helpers in `shared.models` (with thin sync
adapters where needed). Remove `data/labtfg.db` from the repo.

Edge cases:
- `shared/store.py` is imported by Phase 2 CLI (`phase2-juan/simlab/cli.py`?)
  and the model loader. Audit all imports before deleting.
- `data/labtfg.db` is in `data/` which may or may not be gitignored —
  check before `rm`.
- Phase 2 currently can run without docker — after this change, it
  can't. Document the new requirement in `phase2-juan` README.

## Acceptance Criteria

- [ ] **AC1**: `extraction.extract` consistently uses Haiku 4.5 (or
      Sonnet 4.6 — pick one), and `docs/knowledge-architecture.md` +
      `docs/memory-system.md` accurately reflect the choice. A test
      asserts the model constant. Eval cost per topic, re-measured on a
      single `cumulative-growth` topic, matches the architecture
      doc's claim within ±25%.
- [ ] **AC2**: Either (a) `evals/reports/*-merge-quality` dirs and
      `evals/suites/merge-quality.yaml` are deleted, or (b) the suite
      grows a `phase` arg threaded through to `_verify_merge` and
      surfaced in `report.json`; running the suite twice with two
      different `phase` values produces two different JSON outputs.
- [ ] **AC3**: `evals/suites/slug-accuracy.yaml` has
      `reset_kg_before: true` and the eval runner invokes
      `seed_canonical_paradigms` before the first topic. Two
      back-to-back runs of `slug-accuracy.yaml` produce identical
      assertion outcomes.
- [ ] **AC4**: `Paradigm`/`Variable`/`Postulate` nodes no longer
      accumulate `run_ids` arrays on MERGE. New
      `node_run_observations` table exists and is written to per
      MERGE. Migration backfills existing data without dropping any
      run-provenance information.
- [ ] **AC5**: `shared/store.py` is deleted. All callers compile and
      tests pass. `data/labtfg.db` removed from working tree. Phase 2
      readme documents the Postgres requirement.

## Technical Notes

- **Files / modules per requirement:**
  - R1: `phase1-pablo/src/decisionlab/structured.py`,
    `phase1-pablo/src/decisionlab/knowledge/extraction.py`,
    `docs/knowledge-architecture.md`, `docs/memory-system.md`.
  - R2: `phase1-pablo/evals/suites/merge-quality.yaml`,
    `phase1-pablo/evals/reports/2026-05-08-*-merge-quality/`,
    `phase1-pablo/src/decisionlab/eval/assertions.py:_merge_precision_recall`.
  - R3: `phase1-pablo/evals/suites/slug-accuracy.yaml`,
    `phase1-pablo/src/decisionlab/eval/runner.py`,
    `phase1-pablo/src/decisionlab/knowledge/seed.py`,
    `phase1-pablo/src/decisionlab/cli_eval.py`.
  - R4: `shared/shared/knowledge_graph.py`,
    `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`,
    `shared/shared/models.py`,
    `shared/migrations/versions/<new>.py`.
  - R5: `shared/shared/store.py` (delete),
    `phase2-juan/simlab/*` (callers),
    `data/labtfg.db` (delete).
- **Migration discipline:** every schema change ships its own alembic
  revision. R4's revision adds `node_run_observations`; a follow-up
  revision (likely in P3 cleanup) drops the `run_ids` property after
  callers verified.
- **Test convention:** unit tests in `tests/`, integration tests
  marked `@pytest.mark.integration`. R3 needs at least one
  integration test that runs the suite twice and diffs the report.

## Decisions

- **Haiku for extraction (recommended).** Eval cost goes from
  ~$0.10/topic to ~$0.01/topic at the extraction step. If Haiku
  quality regresses on the structured-output schema, gate behind a
  flag and fall back per-call. Defer the call to the user during R1
  implementation if the test eval shows quality drop.
- **Delete merge-quality entirely (recommended).** Phase 1 makes the
  merger redundant; keeping the suite green for one more week is more
  work than deleting + replacing in P1. If the user wants regression
  defense in the meantime, the alternative path in R2 is supported.
- **Cap `run_ids`, do not just truncate.** Truncating a circular
  buffer loses the audit trail; the `node_run_observations` table
  preserves it queryable.
