---
id: P1-001
title: Load canonical-paradigms.json at runtime and inject into extraction prompts
status: done
kind: strike
phase: 1
heat: extraction
priority: 1
blocked_by: [P0-001, P0-002, P0-003, P0-004, P0-005]
created: 2026-05-08
updated: 2026-05-08
---

# P1-001: Load canonicals into extraction prompts

## Objective

Move `canonical-paradigms.json` from `evals/fixtures/` to a runtime
location, load it at module import, and embed the `{slug, name,
definition}` triples into the Researcher / Formalizer / Reasoner
extraction prompts as a "reuse-or-mark-NEW" directive.

## Requirements

Per phase spec R1:

1. Move file: `phase1-pablo/evals/fixtures/canonical-paradigms.json`
   → `phase1-pablo/src/decisionlab/data/canonical-paradigms.json`.
   Add it to `package-data` in `phase1-pablo/pyproject.toml` so it
   ships with installs.
2. Update the eval seeding code path
   (`decisionlab/knowledge/seed.py`) to read from the new location.
3. In `decisionlab/knowledge/prompts.py`, add a module-level
   `_CANONICAL` constant loaded at import time via
   `importlib.resources` (idiomatic Python 3.11+ packaged-data).
4. Inject the canonical list into `RESEARCHER_SYSTEM`,
   `FORMALIZER_SYSTEM`, `REASONER_SYSTEM` as a numbered list with a
   "reuse verbatim or emit `__NEW__`" directive. Builder prompt
   unchanged.
5. The injection must be deterministic — the order of the list
   matters for prompt caching.

## Acceptance Criteria

- [x] AC1: `canonical-paradigms.json` lives at
      `phase1-pablo/src/decisionlab/data/canonical-paradigms.json`
      and is reachable via `importlib.resources`.
- [x] AC2: `_CANONICAL` is loaded once at module import; subsequent
      reads are no-cost.
- [x] AC3: `RESEARCHER_SYSTEM`, `FORMALIZER_SYSTEM`, `REASONER_SYSTEM`
      contain the canonical list verbatim with a deterministic order.
      Snapshot test asserts the exact prompt string.
- [x] AC4: `seed_canonical_paradigms` reads from the new location
      without breaking. Existing P0-003 setup hook still works.
- [ ] AC5: Eval suite `cumulative-growth` runs green after the
      change (no regression — slugs still emitted as expected, just
      now the LLM has a candidate list). *(deferred: live-eval AC,
      verified via 885 passing unit tests; gated by P1-002+P1-003+P1-004)*

## Files Likely Affected

- `phase1-pablo/evals/fixtures/canonical-paradigms.json` → moved.
- `phase1-pablo/src/decisionlab/data/canonical-paradigms.json` —
  new location.
- `phase1-pablo/src/decisionlab/data/__init__.py` — new (empty,
  marks the package).
- `phase1-pablo/pyproject.toml` — `package-data` entry.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — update path.
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — add
  `_CANONICAL`, render into 3 stage prompts.

## Context

Phase spec: `docs/specs/memory-refactor/phase-1-canonical-ids.md` (R1)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A1
Heat: `extraction`

## Completion Summary

**Commit:** `116350c` — `feat[knowledge]: load canonical paradigms into extraction prompts (P1-001)`

### What was built
- Moved `canonical-paradigms.json` into the `decisionlab` package at
  `phase1-pablo/src/decisionlab/data/canonical-paradigms.json` with a
  new `decisionlab.data` sub-package marker.
- Loaded the JSON once at import time via
  `importlib.resources.files()` into a module-level `_CANONICAL`
  constant in `decisionlab.knowledge.prompts`.
- Rendered `_CANONICAL` into a deterministic numbered
  `_CANONICAL_LIST` and a `_CANONICAL_DIRECTIVE` with the
  "reuse-verbatim-or-emit-`__NEW__`" instruction; injected the
  directive into `RESEARCHER_SYSTEM`, `FORMALIZER_SYSTEM`,
  `REASONER_SYSTEM` (Builder unchanged — emits
  `Model.formulation_id`, not paradigm slugs).
- Reworked `seed.py::_load_fixture` so the default branch reads from
  the packaged data via `importlib.resources` while still accepting an
  explicit `path` override for tests.
- Dropped the now-redundant `fixture_path` arg from
  `evals/suites/slug-accuracy.yaml`; updated `test_phase_f_artifacts`
  to resolve the canonical fixture via `importlib.resources` too.

### Files created/modified
- `phase1-pablo/src/decisionlab/data/__init__.py` — new package marker.
- `phase1-pablo/src/decisionlab/data/canonical-paradigms.json` —
  moved from `phase1-pablo/evals/fixtures/canonical-paradigms.json`.
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — added
  `_CANONICAL`, `_CANONICAL_LIST`, `_CANONICAL_DIRECTIVE`; injected
  the directive into the 3 stage prompts.
- `phase1-pablo/src/decisionlab/knowledge/seed.py` — switched the
  default fixture path to `importlib.resources`.
- `phase1-pablo/evals/suites/slug-accuracy.yaml` — removed
  `fixture_path` override (uses packaged default now).
- `phase1-pablo/tests/eval/test_phase_f_artifacts.py` — fixture path
  via `importlib.resources`.
- `phase1-pablo/tests/eval/test_slug_accuracy_determinism.py` —
  comment updated to reflect the new resolution path.
- `phase1-pablo/tests/knowledge/test_canonical_injection.py` — new
  6-test snapshot covering AC1/AC2/AC3 (load, deterministic order,
  directive content, presence in 3 prompts, builder absence, slug
  coverage).

### Decisions
- No explicit `[tool.uv.build-backend]` or `package-data` entry was
  added to `pyproject.toml` because `uv_build` ships every non-Python
  file under the module root by default — empirically verified by
  inspecting the built wheel (`canonical-paradigms.json` present at
  `decisionlab/data/`). The `decisionlab.data.__init__` docstring was
  updated to document this behaviour rather than claim a manifest
  entry that doesn't exist.
- AC5 (live `cumulative-growth` eval green) is deferred — it depends
  on P1-002 (Literal slug validation) and P1-003 (`__NEW__` routing)
  before the suite signal becomes meaningful. All 885 phase-1 unit
  tests pass with the changes; ruff check + format clean.
