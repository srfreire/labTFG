---
id: P0-002
title: Delete merge-quality eval suite, reports, fixture and assertion
status: todo
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
