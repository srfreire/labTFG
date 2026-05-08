---
id: P1-002
title: Constrain slug-like fields to Pydantic Literal[canonical-set + __NEW__]
status: done
kind: strike
phase: 1
heat: extraction
priority: 1
blocked_by: [P1-001]
created: 2026-05-08
updated: 2026-05-08
---

# P1-002: Pydantic Literal validation for slug-like fields

## Objective

Replace the free-form `properties: dict[str, Any]` in the extraction
schema with typed sub-schemas that lock slug-like fields to the
canonical set + `__NEW__` escape. The forced tool-use path validates
at parse time; malformed slugs raise `StructuredOutputError` instead
of silently entering the KG.

## Requirements

Per phase spec R2:

1. In `decisionlab/knowledge/extraction.py`, derive the Literal type
   from `_CANONICAL` (loaded by P1-001):
   ```python
   _CANONICAL_SLUGS = tuple(p["slug"] for p in _CANONICAL) + ("__NEW__",)
   ParadigmSlug = Literal[_CANONICAL_SLUGS]  # via TypeAlias
   ```
   Mypy may complain about runtime-built Literals — use
   `typing.Literal[_CANONICAL_SLUGS]` with a `# type: ignore`
   comment if needed, or use `typing_extensions.Literal` that
   accepts a tuple.
2. Add typed property models for `Paradigm`, `Variable`, `Postulate`:
   ```python
   class _ParadigmProps(BaseModel):
       slug: ParadigmSlug
       name: str
       description: str = ""

   class _VariableProps(BaseModel):
       name: str
       paradigm_slug: ParadigmSlug
       type: str | None = None
       range: str | None = None
       unit: str | None = None

   class _PostulateProps(BaseModel):
       id: str  # validated by paradigm-slug-prefix regex
       statement: str
       falsifiable: bool
       paradigm_slug: ParadigmSlug
   ```
3. Update `_NodeRaw` to dispatch the `properties` validator by
   `label`. Use a Pydantic discriminated union or a custom
   validator.
4. Add unit tests: valid slug passes, invalid slug raises
   `ValidationError` (which `call_structured` translates to a retry
   then `StructuredOutputError`).

## Acceptance Criteria

- [x] AC1: `_CANONICAL_SLUGS` is derived from `_CANONICAL` at module
      import; includes `"__NEW__"`.
- [x] AC2: A `Paradigm` node with `slug="reinforcement-learning"`
      parses successfully. `slug="reinforcement_learning"` (underscore)
      raises `ValidationError`.
- [x] AC3: A `Variable` node with `paradigm_slug` in the canonical
      set parses; outside the set raises.
- [x] AC4: `Postulate.id` is validated against the regex
      `^([a-z0-9-]+):P\d+$` AND its prefix matches a canonical slug.
- [x] AC5: Existing extraction tests (positive cases) still pass —
      the schema is stricter but accepts every valid extraction the
      eval fixtures produce.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — add
  Literal, typed props, dispatch.
- `phase1-pablo/tests/knowledge/test_extraction.py` — add the
  positive + negative validation cases.
- `phase1-pablo/tests/knowledge/test_extraction_canonical.py` — new
  file dedicated to slug-Literal validation.

## Context

Phase spec: `docs/specs/memory-refactor/phase-1-canonical-ids.md` (R2)
Heat: `extraction` (depends on P1-001)

## Completion Summary

**Commit:** `4e61f7c` — `feat[knowledge]: lock slug-bearing extraction fields to canonical Literal (P1-002)`

### What was built
- Built `_CANONICAL_SLUGS` at module import as
  `tuple(p["slug"] for p in _CANONICAL) + ("__NEW__",)`, then unpacked
  into `ParadigmSlug = Literal[_CANONICAL_SLUGS]` so Pydantic enforces
  membership without enumerating slugs in static type-checker syntax.
- Added typed property models `_ParadigmProps`, `_VariableProps`,
  `_PostulateProps` with `paradigm_slug: ParadigmSlug` (required on
  Variable and Postulate; the LLM can no longer silently drop it).
- `_PostulateProps.id` runs a two-gate `field_validator`: regex
  `^(__NEW__|[a-z0-9-]+):P\d+$` enforces shape; membership in
  `_CANONICAL_SLUGS` rejects shape-valid-but-fabricated prefixes
  (e.g. `q-learning:P1`).
- Added a `model_validator(mode="after")` on `_NodeRaw` that dispatches
  the `properties` dict to the right typed sub-validator based on
  `label`. Other labels (Author, Paper, BrainRegion, Equation,
  Parameter, Formulation, Model) keep their free-form dict.
- Updated existing fixtures in `tests/knowledge/test_extraction.py`:
  `RESEARCHER_RESPONSE` Variables now carry `paradigm_slug`,
  Postulates use scoped ids (`homeostatic-regulation:P1` etc.) plus
  `paradigm_slug`; relations referencing those Postulates updated to
  match. `FORMALIZER_RESPONSE` Variables likewise scoped.
- New `tests/knowledge/test_extraction_canonical.py` (26 cases) covers
  AC1–AC4 directly: canonical-set membership, underscore variant
  rejection, invented-variant rejection, `__NEW__` escape acceptance,
  Variable required-paradigm-slug behavior, Postulate id shape +
  prefix-canonical, dispatch on `_NodeRaw` for each slug-bearing
  label.

### Decisions
- **Allow `__NEW__:P<num>` as a Postulate id prefix** — the issue text
  shows the regex as `^([a-z0-9-]+):P\d+$` (no `__NEW__`), but
  validation runs in `call_structured` *before* P1-003's verify-merge
  router can canonicalize a `__NEW__` paradigm. Without this allowance,
  every brand-new paradigm extraction would raise
  `StructuredOutputError`. The membership check still rejects
  fabricated kebab-case prefixes, so the looser regex doesn't widen
  the silent-failure surface.
- **Kept `_build_result`'s defensive paradigm_slug-on-Variable fill
  and the `_is_garbage_paradigm_slug` filter** — both are now
  unreachable from the live `extract()` path (Pydantic catches first),
  but they still guard direct calls to `_build_result` in tests and
  any future caller that bypasses the structured wrapper. Removing
  them was out of scope for this issue.
- **Test fixtures updated rather than schema relaxed** — AC5 ("existing
  positive cases pass") is satisfied by bringing fixtures into
  compliance with the stricter schema, not by making `paradigm_slug`
  optional. This matches the spec's "no silent fallback" stance.

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — added
  `_CANONICAL_SLUGS`, `ParadigmSlug`, `_POSTULATE_ID_RE`,
  `_ParadigmProps`, `_VariableProps`, `_PostulateProps`,
  `_LABEL_TO_PROPS`, and the `_NodeRaw.model_validator` dispatch.
- `phase1-pablo/tests/knowledge/test_extraction.py` — fixtures updated
  to scope Variables and Postulates by canonical paradigm slug.
- `phase1-pablo/tests/knowledge/test_extraction_canonical.py` — new
  26-test suite for AC1–AC4.
