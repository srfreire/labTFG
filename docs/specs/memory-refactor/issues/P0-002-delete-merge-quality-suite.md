---
id: P0-002
title: Delete merge-quality eval suite, reports, fixture and assertion
status: done
kind: strike
phase: 0
heat: merge-quality-eval
priority: 1
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

# P0-002: Delete merge-quality eval suite

## Objective

Delete the `merge-quality` eval suite. It produced three bit-identical
FAIL reports on 2026-05-08 (08:20, 08:30, 08:44) — the "phase"
identifier never reached `_verify_merge`. Phase 1 (P1) deletes the
merger this suite tests, so transitional wiring is wasted effort.
Removing the suite now declutters CI and stops generating
useless reports.

## Requirements

Per the phase spec R2:

1. Delete `phase1-pablo/evals/suites/merge-quality.yaml`.
2. Delete every report dir under `phase1-pablo/evals/reports/` ending
   in `-merge-quality` (`baseline-`, `phase1-`, `phase2-`).
3. Delete `phase1-pablo/evals/fixtures/canonicalize-pairs.json` (only
   consumers are the deleted suite + `scripts/calibrate_canonicalize_tau.py`,
   which P1 also deletes).
4. Remove the `merge_precision_recall` assertion handler in
   `phase1-pablo/src/decisionlab/eval/assertions.py` IF no other live
   suite references it (verify with `grep -rn merge_precision_recall
   phase1-pablo/evals/suites/`). If kept for future use, mark with a
   dated `# unused — keep for future use` comment.
5. Audit any CI workflow file (`.github/workflows/*.yml` or similar)
   for a `merge-quality` step name; remove it.
6. Do **not** touch `decisionlab/canonicalize.py` itself — that's
   P1's job.

## Acceptance Criteria

- [ ] AC1: `phase1-pablo/evals/suites/merge-quality.yaml` no longer
      exists.
- [ ] AC2: No directory under `phase1-pablo/evals/reports/` matches
      `*-merge-quality`.
- [ ] AC3: `phase1-pablo/evals/fixtures/canonicalize-pairs.json` no
      longer exists.
- [ ] AC4: `grep -rn merge_precision_recall phase1-pablo/` returns no
      live caller (the function may remain with a documented stay).
- [ ] AC5: `uv run cli_eval list` (or equivalent) does not surface
      `merge-quality` as an available suite. CI passes without
      referencing it.

## Files Likely Affected

- `phase1-pablo/evals/suites/merge-quality.yaml` — DELETE.
- `phase1-pablo/evals/reports/2026-05-*-baseline-merge-quality/` — DELETE.
- `phase1-pablo/evals/reports/2026-05-*-phase[1234]-merge-quality/` — DELETE.
- `phase1-pablo/evals/fixtures/canonicalize-pairs.json` — DELETE.
- `phase1-pablo/src/decisionlab/eval/assertions.py` — possibly remove
  `_merge_precision_recall` and the `@register_suite` decorator.
- `.github/workflows/*` (if present) — remove any merge-quality step.

## Context

Phase spec: `docs/specs/memory-refactor/phase-0-stop-lying.md` (R2)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A12
Heat: `merge-quality-eval`

## Completion Summary

**Commit:** `28133ea` — `feat[phase1-eval]: delete merge-quality suite, fixture, and assertion (P0-002)`

### What was built

Pure deletion task — wiped the merge-quality eval suite end-to-end so it
stops generating bit-identical FAIL reports while we wait for P1 to
delete the merger it was testing.

- AC1 ✓: `evals/suites/merge-quality.yaml` deleted.
- AC2 ✓: All three local report dirs under `evals/reports/`
  (`2026-05-08-baseline-merge-quality/`, `-phase1-merge-quality/`,
  `-phase2-merge-quality/`) removed (untracked, gitignored).
- AC3 ✓: `evals/fixtures/canonicalize-pairs.json` deleted.
- AC4 ✓: `_merge_precision_recall` predicate + `_pair_text` helper
  removed from `eval/assertions.py`. `grep -rn merge_precision_recall
  phase1-pablo/` returns no live caller (only stale references inside
  historical `docs/superpowers/` plans, which are documentation, not
  code).
- AC5 ✓: `evals/suites/` no longer surfaces `merge-quality`. CI
  workflow (`.github/workflows/ci.yml`) had no reference; left
  untouched. Full phase1 unit suite (854 passed, 12 skipped) and
  ruff lint+format check both green.

### Files created/modified

- `phase1-pablo/evals/suites/merge-quality.yaml` — deleted.
- `phase1-pablo/evals/fixtures/canonicalize-pairs.json` — deleted.
- `phase1-pablo/tests/eval/test_assertions_merge.py` — deleted (its
  only purpose was testing `_merge_precision_recall`).
- `phase1-pablo/src/decisionlab/eval/assertions.py` — dropped the
  `_merge_precision_recall` predicate and its sole caller helper
  `_pair_text` (~105 lines).
- `phase1-pablo/tests/eval/test_phase_f_artifacts.py` — dropped the
  three tests that validated the deleted fixture; kept the canonical-
  paradigms validators that still apply.
- `phase1-pablo/tests/eval/test_report.py` — retargeted the suite-
  assertion example payloads from `merge_precision_recall` to
  `p95_below` (still-registered predicate) so the test data reflects
  living code rather than a deleted predicate.
- `phase1-pablo/src/decisionlab/eval/runner.py` — dropped the stale
  `merge-quality.yaml` example mention from the offline-suite comment.

### Decisions

- `_pair_text` was removed alongside the predicate even though the
  spec only required removing the predicate: it was a private helper
  used exclusively by `_merge_precision_recall`. A near-duplicate
  `_pair_text` lives in `scripts/calibrate_canonicalize_tau.py`, which
  P1 deletes — kept that copy alone (out of scope for P0).
- `decisionlab.canonicalize._verify_merge` and the rest of
  `canonicalize.py` were intentionally **not** touched — that is P1's
  responsibility per the phase spec.
- Updated `test_report.py` rather than deleting the affected tests:
  they assert renderer behavior, not the predicate, so retargeting to
  a still-registered predicate keeps the coverage useful.
- Leaving `scripts/calibrate_canonicalize_tau.py` broken (it imports
  the deleted fixture). The phase-0 spec confirms P1 deletes that
  script too — repairing now would only get reverted.
