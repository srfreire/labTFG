---
id: P0-001
title: Tier extraction model selection per stage (Sonnet for Researcher/Reasoner, Haiku for Formalizer/Builder/importance)
status: todo
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
