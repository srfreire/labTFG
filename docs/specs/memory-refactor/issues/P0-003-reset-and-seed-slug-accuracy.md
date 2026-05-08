---
id: P0-003
title: Reset KG and seed canonical paradigms before slug-accuracy runs
status: todo
kind: strike
phase: 0
heat: slug-accuracy-eval
priority: 1
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

# P0-003: Reset KG and seed canonicals before slug-accuracy

## Objective

Make `slug-accuracy` deterministic across runs. Today the suite has
`reset_kg_before: false` so the second run inherits residue from the
first — phase3 (10:39) hit 7/8, phase4 (13:56) hit 4/8 on the same
fixture. Switching to a fresh KG seeded with `canonical-paradigms.json`
before each run gives a repeatable baseline that future phases can
measure against.

## Requirements

Per the phase spec R3:

1. Edit `phase1-pablo/evals/suites/slug-accuracy.yaml`:
   - Set `reset_kg_before: true`.
   - Add a `setup` block (extending the runner where needed) that
     calls `seed_canonical_paradigms` against the eval KG before the
     first topic runs.

2. If the eval runner does not yet support per-suite setup, add it in
   `phase1-pablo/src/decisionlab/eval/runner.py`. Hook signature:
   accept a list of `setup` actions in the suite YAML, each with a
   `kind` (e.g. `seed_canonical_paradigms`) and optional `args`.

3. Reset wipes the eval KG via Cypher `MATCH (n) DETACH DELETE n`.
   Verify the eval KG instance is segregated from any prod KG
   (different `NEO4J_URI` or named database) — abort with a clear
   error otherwise.

4. Do not change `cumulative-growth.yaml` — it correctly resets +
   bootstraps from empty.

5. Add an integration test
   (`@pytest.mark.integration`,
   `phase1-pablo/tests/eval/test_slug_accuracy_determinism.py`) that
   runs the suite twice in the same pytest session and asserts the
   assertion-outcome set is identical between runs.

## Acceptance Criteria

- [ ] AC1: `evals/suites/slug-accuracy.yaml` has
      `reset_kg_before: true` and a `setup` block that seeds canonical
      paradigms from `evals/fixtures/canonical-paradigms.json`.
- [ ] AC2: The eval runner reads the new `setup:` block and invokes
      `seed_canonical_paradigms`. Unit test covers the parser.
- [ ] AC3: KG reset is gated by an environment / URI check; running
      against a URI without an `eval` marker raises and aborts.
- [ ] AC4: Integration test runs `slug-accuracy` twice and asserts
      the assertion-outcome set is identical between runs.
- [ ] AC5: A manual re-run of `slug-accuracy` against the current
      fixture produces ≥7/8 hit rate (matching the phase3 best).

## Files Likely Affected

- `phase1-pablo/evals/suites/slug-accuracy.yaml` — set
  `reset_kg_before`, add `setup`.
- `phase1-pablo/src/decisionlab/eval/runner.py` — add setup-hook
  handling.
- `phase1-pablo/src/decisionlab/eval/assertions.py` — possibly
  register a setup-action dispatcher.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — ensure
  `seed_canonical_paradigms` is invocable from the runner with the
  expected signature.
- `phase1-pablo/tests/eval/test_slug_accuracy_determinism.py` — new.
- `phase1-pablo/src/decisionlab/cli_eval.py` — possibly update if it
  exposes the same setup actions manually.

## Context

Phase spec: `docs/specs/memory-refactor/phase-0-stop-lying.md` (R3)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A13
Heat: `slug-accuracy-eval`
