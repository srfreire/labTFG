---
id: P5-005
title: Update Phase 2 model_loader for new schema
status: done
kind: strike
phase: 5
heat: phase2
priority: 3
blocked_by: [P5-004]
created: 2026-04-14
updated: 2026-04-15
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
- [x] `discover_models()` returns models from live pipeline runs (P5-004)
- [x] `ModelInfo` has `paradigm` and `formulation` fields
- [x] Orchestrator presents models with readable paradigm/formulation names
- [x] `read_predictions` still correctly reads deep reports from S3
- [x] Models from multiple runs are discoverable

## Files Likely Affected
- `phase2-juan/simlab/model_loader.py` — discover_models, ModelInfo
- `phase2-juan/simlab/orchestrator.py` — list_available_models, read_predictions, model display

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `phase2`

## Completion Summary

**Commit:** `89eaf0d` — `feat[model_loader]: update Phase 2 model_loader for new schema (P5-005)`

### What was built
- `ModelInfo` dataclass: replaced `formulation_id: str` with `id: str` (UUID), `paradigm: str`, `formulation: str`
- `discover_models()`: keys results by `"{paradigm}/{formulation}"` compound string, queries UUID-based Model table
- Duplicate key collision warning: logs when multiple runs produce the same paradigm/formulation
- Orchestrator `list_available_models`: returns `key`, `paradigm`, `formulation`, `class_name`, `description`
- Orchestrator `run_simulation`: accepts `paradigm/formulation` keys via `model_ids`, uses `info.formulation` for agent labels
- System prompt and tool descriptions updated from `formulation_id` to `paradigm/formulation` key format

### Files created/modified
- `phase2-juan/simlab/model_loader.py` — ModelInfo, discover_models, load_model updated for new schema
- `phase2-juan/simlab/orchestrator.py` — tool schemas, system prompt, list_available_models, run_simulation
- `phase2-juan/tests/test_model_loader.py` — fully rewritten: 11 async tests with Postgres mocks
- `phase2-juan/pyproject.toml` — added pytest-asyncio, asyncio_mode=auto

### Decisions
- `discover_models` returns last-seen row per paradigm/formulation key with a warning on collision (not filtered by latest run)
- Model keys use compound `paradigm/formulation` string rather than UUID to keep orchestrator prompts human-readable
- Old filesystem-based tests replaced entirely with async mock-based tests
