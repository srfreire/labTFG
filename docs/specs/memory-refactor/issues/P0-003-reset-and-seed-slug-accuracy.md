---
id: P0-003
title: Reset KG and seed canonical paradigms before slug-accuracy runs
status: done
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

- [x] AC1: `evals/suites/slug-accuracy.yaml` has
      `reset_kg_before: true` and a `setup` block that seeds canonical
      paradigms from `evals/fixtures/canonical-paradigms.json`.
- [x] AC2: The eval runner reads the new `setup:` block and invokes
      `seed_canonical_paradigms`. Unit test covers the parser.
- [x] AC3: KG reset is gated by an environment / URI check; running
      against a URI without an `eval` marker raises and aborts.
- [x] AC4: Integration test runs `slug-accuracy` twice and asserts
      the assertion-outcome set is identical between runs.
- [ ] AC5: A manual re-run of `slug-accuracy` against the current
      fixture produces ≥7/8 hit rate (matching the phase3 best).
      *(Deferred — the harness change is in; the manual eval rerun
      against live OpenRouter / Anthropic budget is queued for the
      next phase-0 wrap-up.)*

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

## Completion Summary

**Branch:** `strike/slug-accuracy-eval-P0-003`

### What was built

- Suite-level `setup:` block parser + dispatcher in
  `decisionlab.eval.suite` — `SetupAction` dataclass, registered
  `seed_canonical_paradigms` kind, fixture-path arg.
- Eval-KG segregation guard (`_assert_eval_kg_segregation`) that
  refuses the destructive `MATCH (n) DETACH DELETE n` unless the
  active Neo4j is marked as eval. Marker = `LABTFG_EVAL_KG=1` env
  var, OR `eval` as a delimited token in `NEO4J_URI` /
  `NEO4J_DATABASE`. Token-boundary regex avoids substring
  collisions (`evaluation-prod` is rejected).
- `slug-accuracy.yaml` flipped to `reset_kg_before: true` with a
  `seed_canonical_paradigms` setup action pointing at
  `evals/fixtures/canonical-paradigms.json`.
- `cli_eval._replace_*` rewritten on top of `dataclasses.replace`,
  fixing a latent bug where `suite_assertions` was silently
  dropped on every `--no-reset` / `--stages` override.
- `decisionlab.knowledge.seed._seed_one` switched to a
  closure pattern so the call signature matches
  `KnowledgeGraph.execute_write` (the previous shape passed extra
  positional args the wrapper rejects).

### Files created / modified

- `phase1-pablo/src/decisionlab/eval/suite.py` — parser, guard,
  dispatcher.
- `phase1-pablo/src/decisionlab/cli_eval.py` — `_clone_spec`
  refactor.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — closure call
  shape (preserves the new run_count / last_run_at schema from
  P0-004).
- `phase1-pablo/evals/suites/slug-accuracy.yaml` — config flip.
- `phase1-pablo/tests/eval/test_suite.py` — parser, dispatcher,
  guard, run_suite ordering, substring-collision case.
- `phase1-pablo/tests/eval/test_slug_accuracy_determinism.py`
  (new) — runs the suite twice in one pytest session, asserts
  identical outcomes + per-topic passes + post-stats KG counts.
- `phase1-pablo/tests/eval/test_suite_integration.py` —
  `live_infra` fixture sets `LABTFG_EVAL_KG=1`.
- `.env.example` — documents `LABTFG_EVAL_KG`.

### Decisions

- **Token-boundary regex for the URI / database marker.** Loose
  substring matching would let a hostname like
  `evaluation-prod.internal` pass the guard, authorising a wipe on
  a production graph. The reviewer flagged the collision risk; the
  fix tightens the check to require `eval` bounded by
  non-alphanumeric characters.
- **AC5 deferred.** The harness change is fully exercised by the
  determinism integration test (which proves the reset+seed cycle
  is repeatable). The "≥7/8 hit rate" rerun depends on real
  Researcher LLM calls and is queued for the phase-0 wrap-up rerun.
