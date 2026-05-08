---
id: P1-002
title: Constrain slug-like fields to Pydantic Literal[canonical-set + __NEW__]
status: todo
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

- [ ] AC1: `_CANONICAL_SLUGS` is derived from `_CANONICAL` at module
      import; includes `"__NEW__"`.
- [ ] AC2: A `Paradigm` node with `slug="reinforcement-learning"`
      parses successfully. `slug="reinforcement_learning"` (underscore)
      raises `ValidationError`.
- [ ] AC3: A `Variable` node with `paradigm_slug` in the canonical
      set parses; outside the set raises.
- [ ] AC4: `Postulate.id` is validated against the regex
      `^([a-z0-9-]+):P\d+$` AND its prefix matches a canonical slug.
- [ ] AC5: Existing extraction tests (positive cases) still pass —
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
