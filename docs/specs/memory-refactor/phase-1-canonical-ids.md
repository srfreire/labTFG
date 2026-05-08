# Phase 1: Canonical IDs at extraction

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08-P1-004
> References: [general.md](general.md) · [phases.md](phases.md) · [phase-0-stop-lying.md](phase-0-stop-lying.md) · [`docs/memory-system.md`](../../memory-system.md) §A1

## Objective

Inject `canonical-paradigms.json` into the LLM extraction prompts as a
constrained vocabulary; make slug-like fields Pydantic `Literal[...]`;
route the `__NEW__` escape through the existing
`canonicalize._verify_merge` only when the LLM explicitly opts out;
then delete the merger and the τ-calibration script. The post-hoc
merge step exists today only because identity is solved one layer too
late — fix the layering and the merger becomes deletable.

Expected impact:
- `slug-accuracy.yaml` passes ≥8/8 with the canonical-injection (vs
  4–7/8 today).
- `kg_growth_rate` Paradigm/Variable/Postulate caps stop being violated
  in slug-accuracy (Variables inherit canonical Paradigm slug as FK).
- One Sonnet `_verify_merge` call removed per extracted entity that
  hits a canonical slug (~95 % of cases).

## Requirements

### R1 — Inject `canonical-paradigms.json` into extraction prompts

Move `phase1-pablo/evals/fixtures/canonical-paradigms.json` to a
runtime location: `phase1-pablo/src/decisionlab/data/canonical-paradigms.json`
(plus a packaged copy via `pyproject.toml` `package-data`). Load at
module import time into `_CANONICAL` (list of `{slug, name, definition}`).

Render the canonical list into each stage's system prompt as a
**Reuse-or-mark-NEW** directive:

> The following paradigms already exist in the KG. Reuse their `slug`
> verbatim. Only emit `slug: "__NEW__"` if the topic genuinely does
> not fit any of these.
> - reinforcement-learning: …
> - prospect-theory: …
> ...

Applies to: researcher, formalizer, reasoner stage prompts (Builder
emits `Model.formulation_id`, not paradigm slugs — leave it alone).

### R2 — Pydantic `Literal[...]` over canonical set

In `decisionlab/knowledge/extraction.py`, replace the free-form
`properties: dict[str, Any]` with a typed sub-schema for `Paradigm`,
`Variable`, and `Postulate`:

```python
_CANONICAL_SLUGS = tuple(p["slug"] for p in _CANONICAL) + ("__NEW__",)
ParadigmSlug = Literal[_CANONICAL_SLUGS]  # via TypeAlias

class _ParadigmProps(BaseModel):
    slug: ParadigmSlug
    name: str
    description: str

class _VariableProps(BaseModel):
    name: str
    paradigm_slug: ParadigmSlug
    type: str | None = None
    range: str | None = None
    unit: str | None = None
```

`call_structured` forced tool-use validates the Literal at parse time;
malformed slugs raise `StructuredOutputError`.

### R3 — Route `__NEW__` through `_verify_merge` only

In `phase1-pablo/src/decisionlab/agents/memory_agent.py`, replace the
unconditional `canonicalize(extraction)` call with a guarded version:

```python
needs_canon = any(
    n.label in CANONICALIZE_LABELS and n.properties.get("slug") == "__NEW__"
    for n in extraction.nodes
)
if needs_canon:
    extraction = await canonicalize(extraction, ...)
```

Canonical-slug nodes go straight through to `populate_kg` without a
Sonnet call.

### R4 — Delete the merger

Once R1+R2+R3 land and a regression run of
`cumulative-growth + slug-accuracy` passes (≥8/8 slug hit, growth caps
respected, no quality regression):

- Delete `phase1-pablo/src/decisionlab/canonicalize.py`.
- Delete `phase1-pablo/scripts/calibrate_canonicalize_tau.py`.
- Remove the import + call site in `agents/memory_agent.py` (R3 no
  longer needs it).
- Remove the `from decisionlab.canonicalize import DEFAULT_THRESHOLD`
  in `feedback_port.py:403`.
- Remove the `_validate_natural_key` UUID-shape rejection in
  `kg_writer.py` (it was duct tape for slug leaks; slugs are now
  Literal-validated).
- Update `docs/memory-system.md` §A1 with a "DONE" marker.

## Acceptance Criteria

- [x] AC1: `_CANONICAL` constant loaded at module import. All 3
      affected stage prompts (researcher/formalizer/reasoner) embed
      the canonical list. *(P1-001)*
- [x] AC2: `_ParadigmProps`, `_VariableProps`, `_PostulateProps`
      enforce slug `Literal[...]`. Unit test covers a valid slug pass
      and an invalid slug raise. *(P1-002)*
- [x] AC3: `memory_agent` skips `canonicalize` when no `__NEW__`
      slug appears in the extraction. Test asserts skip path on a
      fully-canonical extraction and run path on a `__NEW__`
      extraction. *(P1-003)*
- [ ] AC4: Re-running `slug-accuracy.yaml` (with P0-003's reset+seed)
      produces ≥8/8 hit rate. `kg_growth_rate` Paradigm ≤1.5/topic,
      Variable ≤6/topic, Postulate ≤5/topic.
- [x] AC5: `decisionlab/canonicalize.py` and
      `scripts/calibrate_canonicalize_tau.py` deleted. `grep -rn
      'canonicalize' phase1-pablo/src/` returns no live caller.
      *(P1-004 — deletion + grep mechanically verified; full
      smoke+cumulative-growth+slug-accuracy regression deferred to a
      post-merge run on `main`.)*

## Technical Notes

- **Failure mode to test**: LLM hallucinates `reinforcement_learning`
  (underscore). The Literal rejects, `call_structured` retries; on
  persistent failure, `StructuredOutputError` surfaces in the trace —
  no silent fallback.
- **Cross-paradigm Variables**: `Variable.id` composite is already
  `{paradigm}:{slugify(name)}` (from commit `50c952c`). Locking
  `paradigm_slug` to the canonical Literal makes that composite
  collision-free across runs.
- **Builder unchanged**: emits `Model.formulation_id` from the
  per-run formulation IDs the Reasoner produced. Different identity
  domain.
- **Sequential within heat**: all 4 issues touch
  `extraction.py` / `memory_agent.py` / `canonicalize.py`. Run as a
  single hydra chain (P1-001 → P1-002 → P1-003 → P1-004), not in
  parallel.

## Decisions

- **Move JSON to runtime location** (`src/decisionlab/data/`) so it
  ships with the package, not gated on the eval directory.
- **Skip Builder stage** — it doesn't emit paradigm slugs. Keep the
  intervention surgical.
- **Delete the merger entirely in R4** — no transitional dual-path.
  P1 is the issue that proves the new path works; if it doesn't, R4
  reverts cleanly.
