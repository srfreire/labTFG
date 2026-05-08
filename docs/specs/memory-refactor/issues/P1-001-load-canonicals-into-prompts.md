---
id: P1-001
title: Load canonical-paradigms.json at runtime and inject into extraction prompts
status: todo
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

- [ ] AC1: `canonical-paradigms.json` lives at
      `phase1-pablo/src/decisionlab/data/canonical-paradigms.json`
      and is reachable via `importlib.resources`.
- [ ] AC2: `_CANONICAL` is loaded once at module import; subsequent
      reads are no-cost.
- [ ] AC3: `RESEARCHER_SYSTEM`, `FORMALIZER_SYSTEM`, `REASONER_SYSTEM`
      contain the canonical list verbatim with a deterministic order.
      Snapshot test asserts the exact prompt string.
- [ ] AC4: `seed_canonical_paradigms` reads from the new location
      without breaking. Existing P0-003 setup hook still works.
- [ ] AC5: Eval suite `cumulative-growth` runs green after the
      change (no regression — slugs still emitted as expected, just
      now the LLM has a candidate list).

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
