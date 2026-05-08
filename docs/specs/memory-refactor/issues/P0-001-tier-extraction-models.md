---
id: P0-001
title: Tier extraction model selection per stage (Sonnet for Researcher/Reasoner, Haiku for Formalizer/Builder/importance)
status: done
kind: strike
phase: 0
heat: extraction-model
priority: 1
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

# P0-001: Tier extraction model selection per stage

## Objective

Replace the blanket Sonnet 4.6 default for extraction with per-stage
tiering: Sonnet for judgment-heavy stages (Researcher, Reasoner +
`resolver._classify_conflict`), Haiku for mechanical stages
(Formalizer, Builder, `resolver._score_importance`). Align
documentation with code. Expected ≥40 % drop in Sonnet token spend on
extraction without quality regression.

## Requirements

Per the phase spec R1:

1. Introduce `_STAGE_MODELS` in
   `phase1-pablo/src/decisionlab/knowledge/extraction.py`:
   ```python
   _STAGE_MODELS = {
       "researcher": SETTINGS.knowledge_structured_model,  # Sonnet
       "formalizer": SETTINGS.knowledge_fast_model,        # Haiku
       "reasoner":   SETTINGS.knowledge_structured_model,  # Sonnet
       "builder":    SETTINGS.knowledge_fast_model,        # Haiku
   }
   ```
   Pass `model=_STAGE_MODELS[stage]` to `call_structured(...)`.

2. In `phase1-pablo/src/decisionlab/knowledge/resolver.py`, switch
   `_score_importance` to `SETTINGS.knowledge_fast_model` (Haiku).
   Leave `_classify_conflict` on the structured model.

3. Add `knowledge_structured_model` to `decisionlab.config` alongside
   the existing `knowledge_fast_model`. Default Sonnet 4.6, env
   override `DECISIONLAB_KNOWLEDGE_STRUCTURED_MODEL`.

4. Update `docs/knowledge-architecture.md` LLM-usage table and
   `docs/memory-system.md` §A8 to reflect per-stage tiering.

5. Unit tests assert the model resolution per stage and per resolver
   call site.

## Acceptance Criteria

- [ ] AC1: `extract(stage, ...)` resolves the correct model per stage
      from `_STAGE_MODELS`. Test asserts each of the 4 stage→model
      pairs.
- [ ] AC2: `resolver._score_importance` uses the fast model;
      `resolver._classify_conflict` uses the structured model. Tests
      cover both call sites.
- [ ] AC3: `decisionlab.config.SETTINGS` exposes both
      `knowledge_fast_model` and `knowledge_structured_model`. Env
      overrides documented.
- [ ] AC4: `docs/knowledge-architecture.md` and `docs/memory-system.md`
      reflect Haiku for Formalizer/Builder/importance and Sonnet for
      Researcher/Reasoner/conflict.
- [ ] AC5: Re-running `evals/suites/cumulative-growth.yaml` shows
      extraction Sonnet input+output token total ≥40 % below the
      `2026-05-08-cumulative-growth/report.json` baseline. KG growth
      (Paradigm/Variable/Postulate counts) within ±10 % of that
      baseline.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — add
  `_STAGE_MODELS`, thread per-stage model into `call_structured`.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — switch
  `_score_importance` to fast model.
- `phase1-pablo/src/decisionlab/config.py` — add
  `knowledge_structured_model` setting.
- `phase1-pablo/src/decisionlab/structured.py` — review whether
  `DEFAULT_MODEL` should remain (likely keep for back-compat, but
  `extraction.extract` no longer relies on it).
- `phase1-pablo/tests/knowledge/test_extraction.py` (new or extend) —
  assert `_STAGE_MODELS` resolution.
- `docs/knowledge-architecture.md` — update LLM usage table.
- `docs/memory-system.md` — update §A8 and the next-steps block.
- `phase1-pablo/README.md` — document new env var.

## Context

Phase spec: `docs/specs/memory-refactor/phase-0-stop-lying.md` (R1)
General spec: `docs/specs/memory-refactor/general.md`
Source critique: `docs/memory-system.md` §A8
Heat: `extraction-model`

## Completion Summary

**Commit:** `9423c32` — `feat[knowledge]: tier extraction model selection per stage (P0-001)`

### What was built
- `_STAGE_MODELS` dict in `phase1-pablo/src/decisionlab/knowledge/extraction.py`
  maps stage → model. Researcher and Reasoner resolve to
  `SETTINGS.knowledge_structured_model` (Sonnet 4.6); Formalizer and
  Builder resolve to `SETTINGS.knowledge_fast_model` (Haiku 4.5).
- `resolver._score_importance` switched to `SETTINGS.knowledge_fast_model`
  (mechanical 1–10 rating); `resolver._classify_conflict` switched to
  `SETTINGS.knowledge_structured_model` (was reading the hardcoded
  `structured.DEFAULT_MODEL`).
- Renamed `Settings.knowledge_heavy_model` → `Settings.knowledge_structured_model`
  (env: `DECISIONLAB_KNOWLEDGE_HEAVY_MODEL` →
  `DECISIONLAB_KNOWLEDGE_STRUCTURED_MODEL`). The `_heavy_` slot had no
  live callers outside `config.py`; the new name reflects what it
  controls (structured-output reasoning, not just "heavy").
- Reviewer-flagged extra: `consolidation.py` reflection generation also
  used the hardcoded `structured.DEFAULT_MODEL`; switched to
  `SETTINGS.knowledge_structured_model` so the env override works for
  every judgment-heavy structured call in the knowledge layer.
- Tests: parametrized `test_extract_resolves_model_per_stage`
  asserting the 4 stage→model pairs;
  `test_stage_models_dict_covers_all_stages` guarding key parity with
  `_STAGE_PROMPTS`; resolver tests rewritten to assert
  `SETTINGS.knowledge_fast_model` for importance and
  `SETTINGS.knowledge_structured_model` for classify-conflict.
- Docs: `docs/knowledge-architecture.md` LLM-usage table now itemises
  per-stage extraction model + slot. `docs/memory-system.md` §A8
  rewritten as resolved (2026-05-08); architecture diagram fixed to
  show tiered call_structured + Haiku importance scoring.

### Files created/modified
- `phase1-pablo/src/decisionlab/config.py` — rename slot, reword docstring.
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — add
  `_STAGE_MODELS`; thread per-stage model into `call_structured`.
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — wire fast/
  structured model from `SETTINGS`; drop `_STRUCTURED_MODEL` import.
- `phase1-pablo/src/decisionlab/knowledge/consolidation.py` — local
  `_STRUCTURED_MODEL = SETTINGS.knowledge_structured_model` so
  reflection generation honours the env override.
- `phase1-pablo/.env.example` — rename env var.
- `phase1-pablo/tests/knowledge/test_extraction.py` — add per-stage
  model resolution tests.
- `phase1-pablo/tests/knowledge/test_resolver.py` — assert
  fast/structured slots.
- `docs/knowledge-architecture.md`, `docs/memory-system.md` — per-stage
  tiering + §A8 resolved.

### Decisions
- **Renamed `knowledge_heavy_model` rather than adding alongside.** The
  P0-001 spec text says "Add `knowledge_structured_model` alongside the
  existing `knowledge_fast_model`" — implying the spec author didn't
  notice `knowledge_heavy_model` had been added in a prior commit. Since
  it had zero live callers, a rename produced a single canonical name
  with no migration burden.
- **`_STAGE_MODELS` is a module-level dict snapshot of `SETTINGS`,
  matching the `_FAST_MODEL = SETTINGS.knowledge_fast_model` idiom in
  `crag.py`, `kg_retrieval.py`, and `consolidation.py`.** Env overrides
  set after process start aren't picked up — same constraint that
  already governed every other knowledge-layer call site.
- **Acceptance: AC1–AC4 met by the diff. AC5 (≥40% Sonnet token drop on
  `cumulative-growth.yaml`) is an empirical claim that requires running
  the suite with API keys; the implementation is complete but the eval
  re-run is still pending.** Marked AC1 of the phase spec as `[x]` with
  a note flagging the eval re-run.
- **Reviewer caught one critical gap.** `consolidation.py` was using
  the hardcoded `structured.DEFAULT_MODEL` for reflection generation,
  bypassing the env override. Fixed in the same branch — outside the
  literal "Files Likely Affected" list but inside the spec's intent
  ("docs/code parity for every Sonnet call in the knowledge layer").
