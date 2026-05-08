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

### R1 — Per-stage extraction model tiering (A8)

`decisionlab.structured.DEFAULT_MODEL` is `"anthropic/claude-sonnet-4.6"`
today. `docs/knowledge-architecture.md` claims extraction uses Haiku
(~$0.001 per call). The eval JSON reports show ~30k input + ~30k
output Sonnet tokens per topic — code-side reality is Sonnet.

Decision: **drop the blanket DEFAULT_MODEL for extraction; tier by
stage difficulty.**

Per-stage analysis of the prompts:

| Stage | Task profile | Model |
|---|---|---|
| Researcher | Filter garbage slugs ("decision-making", "trade-off", web chrome) + scope `paradigm_slug` across nested entities — judgment-heavy | **Sonnet 4.6** |
| Formalizer | Pull Equation/Variable/Parameter/Formulation from structured `### Equations` / `### Variables` tables — rigid schema | **Haiku 4.5** |
| Reasoner | Trace `DERIVES_FROM` chains by walking JSON `rules` array, matching `source_postulate` — multi-step reasoning | **Sonnet 4.6** |
| Builder | Extract one `Model` node + `IMPLEMENTS` from `.py` + pass/fail — mechanical | **Haiku 4.5** |
| `resolver._score_importance` | Rate 1–10 per fact — currently Sonnet, wasteful | **Haiku 4.5** |
| `resolver._classify_conflict` | DUPLICATE / CORROBORATION / ENRICHMENT / CONTRADICTION + write merged content | **Sonnet 4.6** (keep) |

Implementation: introduce a `_STAGE_MODELS` dict in
`decisionlab/knowledge/extraction.py` mapping stage → model, and pass
the resolved model to `call_structured(..., model=...)`. Mirror the
existing pattern at the resolver call sites for `_score_importance`.
Update `docs/knowledge-architecture.md` and `docs/memory-system.md`
to document the per-stage tiering.

Expected cost cut: ~50 % drop on extraction (2 of 4 stages move to
Haiku) plus the importance call. Researcher stays on Sonnet because
the "what counts as a paradigm" filter is the exact kind of judgment
Haiku stumbles on.

Edge cases:
- Haiku 4.5 supports forced tool-use (Pydantic schema), so
  `call_structured` works unchanged.
- `_pre_anchor` Haiku call in `router.py:802` already uses the
  `knowledge_fast_model` config — reuse the same constant for
  Formalizer/Builder/importance.
- A regression run on `cumulative-growth` after the swap should match
  pre-change KG growth ±10 %; if not, revert that specific stage.

### R2 — Delete merge-quality suite (A12)

Three reports on 2026-05-08 (08:20, 08:30, 08:44) all produced
**bit-identical** numbers (`tp=3, fp=0, fn=7, tn=8`). The "phase"
identifier was in the directory name only; the eval runner does not
plumb anything to `canonicalize._verify_merge`.

Decision (confirmed): **delete the suite now**. Phase 1 (A1) replaces
the entire merge-decision pathway with canonical-ID injection at
extraction time, so the merger this suite tests will not exist. No
transitional wiring of a `phase` arg.

Files to delete:
- `phase1-pablo/evals/suites/merge-quality.yaml`
- `phase1-pablo/evals/reports/2026-05-*-baseline-merge-quality/`
- `phase1-pablo/evals/reports/2026-05-*-phase[1234]-merge-quality/`
- `phase1-pablo/evals/fixtures/canonicalize-pairs.json`
  (only used by this suite + `scripts/calibrate_canonicalize_tau.py`,
  both going away in P1)
- The `merge_precision_recall` assertion handler in
  `phase1-pablo/src/decisionlab/eval/assertions.py` if no other
  suite references it (verify with grep).

Edge cases:
- If any CI workflow references `merge-quality` by name, update or
  remove that step in the same commit.
- Keep `_verify_merge` itself untouched in P0 — P1 is the issue that
  deletes the canonicalize module.

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

- [ ] **AC1**: `extraction.extract` resolves the model per stage from
      a `_STAGE_MODELS` dict (Researcher+Reasoner = Sonnet 4.6,
      Formalizer+Builder = Haiku 4.5). `resolver._score_importance`
      uses Haiku. Documentation in `docs/knowledge-architecture.md` +
      `docs/memory-system.md` lists the per-stage choices. A test
      asserts the model resolution for each stage. Re-running
      `cumulative-growth` shows total Sonnet token spend on extraction
      drops ≥40 % vs the pre-change baseline.
- [ ] **AC2**: `evals/suites/merge-quality.yaml`,
      `evals/reports/*-merge-quality/`, and
      `evals/fixtures/canonicalize-pairs.json` are deleted.
      `merge_precision_recall` is removed from
      `eval/assertions.py` (or kept only if another live suite
      references it). Any CI workflow step naming `merge-quality` is
      removed.
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
