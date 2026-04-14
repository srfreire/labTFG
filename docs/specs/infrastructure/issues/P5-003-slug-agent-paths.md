---
id: P5-003
title: Switch Reasoner + Builder to slug-based S3 paths
status: done
kind: strike
phase: 5
heat: agents
priority: 2
blocked_by: [P5-002]
created: 2026-04-14
updated: 2026-04-14
---

# P5-003: Switch Reasoner + Builder to slug-based S3 paths

## Objective
Update Reasoner and Builder agents to use `{paradigm_slug}/{formulation_slug}` S3 paths instead of T-P-F IDs. Add filename validation in the Router after agent writes.

## Requirements

### Reasoner changes
- `reasoner_sub.py` system prompt: change `reasoner/{formulation_id}.json` to `reasoner/{paradigm}/{formulation}.json`
- Remove "Formulation IDs" section from system prompt (lines 89-98); replace with slug-based naming instructions
- User message injection: pass `(paradigm_slug, formulation_slug)` pairs instead of T-P-F IDs
- `reasoner.py`: pass slug-based formulation identifiers to sub-agent (receives `{slug: [formulation_slug]}` from PipelineState)

### Builder changes
- `builder.py`: construct S3 keys as `reasoner/{paradigm}/{formulation}.json` for reading specs
- Discovery fallback: list `{models_prefix}/reasoner/{paradigm}/` directories, then files within
- `builder_sub.py` system prompt: change to `builder/{paradigm}/{formulation}_model.py` and `builder/{paradigm}/test_{formulation}.py`
- Validation report path: `builder/{paradigm}/{formulation}_validation.json`

### Router filename validation
- After Reasoner runs, verify expected files exist at `reasoner/{paradigm}/{formulation}.json`
- After Builder runs, verify expected files exist at `builder/{paradigm}/{formulation}_model.py`
- On mismatch: attempt to find the file (list S3 prefix), rename to expected path, log warning

### Router re-run logic
- `_review_build`: replace `startswith(paradigm_id + "-")` filtering with `approved_specs[paradigm_slug]` dict lookup
- `_execute_rerun_cascade`: same replacement
- Delete stale validation at `builder/{paradigm}/{formulation}_validation.json`
- Pass `{paradigm_slug: [formulation_slug]}` to Reasoner/Builder on re-runs

## Acceptance Criteria
- [x] Reasoner writes specs to `models/{run_id}/reasoner/{paradigm}/{formulation}.json`
- [x] Builder reads specs from that path and writes to `models/{run_id}/builder/{paradigm}/{formulation}_model.py`
- [x] No T-P-F IDs appear in any agent system prompt or user message
- [x] Router validates expected files after each agent run
- [x] Re-run logic uses dict key lookup, not string prefix matching
- [x] Builder re-runs correctly clean up stale validation reports at new paths

## Files Likely Affected
- `src/decisionlab/agents/reasoner.py` — slug-based formulation passing
- `src/decisionlab/agents/reasoner_sub.py` — system prompt + user message rewrite
- `src/decisionlab/agents/builder.py` — S3 key construction, discovery logic
- `src/decisionlab/agents/builder_sub.py` — system prompt rewrite
- `src/decisionlab/router.py` — _review_build, _execute_rerun_cascade, validation logic

## Context
Phase spec: `docs/specs/infrastructure/phase-5-slug-wiring.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `agents`

## Completion Summary

**Commit:** `ef5098a` — `feat[agents]: switch Reasoner + Builder to slug-based S3 paths (P5-003)`

### What was built
- Reasoner system prompt rewritten: writes specs to `reasoner/{paradigm}/{formulation}.json`
- Builder system prompt rewritten: writes to `builder/{paradigm}/{formulation}_model.py` and `builder/{paradigm}/test_{formulation}.py`
- Builder.run() API changed from `spec_ids: list[str]` to `approved_specs: dict[str, list[str]]` with nested S3 discovery
- Router: all agent constructions fixed to use S3 prefix params (`research_prefix`, `models_prefix`, `run_id`)
- Router: added `_validate_reasoner_files()` and `_validate_builder_files()` — verify expected files exist after agent runs, auto-rename mismatches
- Router: stale validation cleanup uses nested paths `builder/{paradigm}/{formulation}_validation.json`
- `files.py`: artifact type inference updated for nested `builder/{paradigm}/test_*` paths

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/reasoner_sub.py` — system prompt + user message rewrite (formulation_ids → formulation_slugs)
- `phase1-pablo/src/decisionlab/agents/reasoner.py` — pass formulation_slugs to sub-agent
- `phase1-pablo/src/decisionlab/agents/builder_sub.py` — system prompt rewrite for nested paths
- `phase1-pablo/src/decisionlab/agents/builder.py` — run() accepts dict, nested S3 key construction + discovery
- `phase1-pablo/src/decisionlab/router.py` — fix all agent constructions, add validation methods, update re-run logic
- `phase1-pablo/src/decisionlab/tools/files.py` — nested test path inference
- 13 test files updated for new S3 prefix constructor APIs (218 passed, 0 failed)

### Decisions
- `build_results` keys remain as formulation slugs (not `paradigm/formulation`) for backward compatibility with feedback functions
- Feedback functions (`feedback.py`, `web_feedback.py`) still use local filesystem via `reports_dir` — separate migration scope
- Also fixed pre-existing test failures for Researcher, DeepResearcher, Formalizer, and tools that had stale `reports_dir` constructors
