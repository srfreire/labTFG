---
id: P5-005
title: Update Phase 2 model_loader for new schema
status: todo
kind: strike
phase: 5
heat: phase2
priority: 3
blocked_by: [P5-004]
created: 2026-04-14
updated: 2026-04-14
---

# P5-005: Update Phase 2 model_loader for new schema

## Objective
Update Phase 2's model discovery to work with the restructured `models` table (UUID PK, paradigm + formulation slug columns).

## Requirements

### model_loader.py
- `discover_models()`: query `models` table using new columns
- Return type: keyed by UUID `id` or by compound `"{paradigm}/{formulation}"` string
- `ModelInfo` dataclass: replace `formulation_id: str` with `id: str` (UUID), `paradigm: str`, `formulation: str`
- Keep `class_name`, `description`, `s3_model_key`, `run_id`

### orchestrator.py
- `list_available_models` tool: present models with paradigm + formulation info
- `run_id` extraction: read from `ModelInfo.run_id` (same as before)
- `read_predictions`: construct S3 key using paradigm slug (same `deep/{slug}.md` pattern)
- Model display: show `"{paradigm} / {formulation}"` instead of raw formulation_id

### Edge cases
- Multiple runs produce same paradigm/formulation: `discover_models` should return models from all runs (or latest only — decide based on Phase 2 behavior)
- Model with no run_id: handle gracefully (migration-era data)

## Acceptance Criteria
- [ ] `discover_models()` returns models from live pipeline runs (P5-004)
- [ ] `ModelInfo` has `paradigm` and `formulation` fields
- [ ] Orchestrator presents models with readable paradigm/formulation names
- [ ] `read_predictions` still correctly reads deep reports from S3
- [ ] Models from multiple runs are discoverable

## Files Likely Affected
- `phase2-juan/simlab/model_loader.py` — discover_models, ModelInfo
- `phase2-juan/simlab/orchestrator.py` — list_available_models, read_predictions, model display

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `phase2`
