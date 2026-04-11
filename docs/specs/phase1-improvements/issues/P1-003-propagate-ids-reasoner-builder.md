---
id: P1-003
title: Propagación de IDs a Reasoner y Builder
status: done
kind: strike
phase: 1
heat: ids
priority: 2
blocked_by: [P1-002]
created: 2026-04-10
updated: 2026-04-11
---

# P1-003: Propagación de IDs a Reasoner y Builder

## Objective
Hacer que Reasoner y Builder usen los IDs del registry para nombrar sus artefactos en vez de construir formulation_ids ad-hoc.

## Requirements

### Reasoner
- `_do_reason` (router.py:304) pasa los IDs del registry al Reasoner
- ReasonerSubAgent recibe el ID (e.g., `T01-P01-F01`) y lo usa como nombre del JSON spec: `reasoner/T01-P01-F01.json`
- El JSON spec incluye un campo `"id"` con el ID del registry
- Eliminar la instrucción en REASONER_SUB_SYSTEM_PROMPT que dice al LLM construir el formulation_id — ahora viene dado

### Builder
- `_do_build` (router.py:365) pasa los IDs del registry al Builder
- BuilderSubAgent usa el ID para nombrar archivos: `builder/T01-P01-F01_model.py`, `builder/test_T01-P01-F01.py`
- `approved_specs` en PipelineState usa IDs del registry

### Review stages
- `_review_reason` (router.py:327) usa IDs del registry para mostrar specs al usuario
- `_review_build` (router.py:390) usa IDs del registry para mostrar resultados

## Acceptance Criteria
- [x] JSON specs se nombran con el ID del registry (e.g., `T01-P01-F01.json`)
- [x] Modelos Python se nombran con el ID del registry (e.g., `T01-P01-F01_model.py`)
- [x] approved_specs contiene IDs del registry
- [x] build_results usa IDs del registry como keys
- [x] ReasonerSubAgent no construye formulation_id — lo recibe como parámetro

## Files Likely Affected
- `src/decisionlab/router.py` — _do_reason(), _do_build(), _review_reason(), _review_build()
- `src/decisionlab/agents/reasoner.py` — Reasoner.run() acepta IDs
- `src/decisionlab/agents/reasoner_sub.py` — REASONER_SUB_SYSTEM_PROMPT, ReasonerSubAgent.run()
- `src/decisionlab/agents/builder.py` — Builder.run() acepta IDs
- `src/decisionlab/agents/builder_sub.py` — BUILDER_SUB_SYSTEM_PROMPT, BuilderSubAgent.run()
- `src/decisionlab/feedback.py` — review_reason(), review_build()
- `src/decisionlab/web_feedback.py` — same for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-1-ids-treemap.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `ids`

## Completion Summary

**Commit:** `3539b54` — `feat[phase1]: propagate registry IDs to Reasoner & Builder (P1-003)`

### What was built
- `ReasonerSubAgent.run` accepts `formulation_ids` parameter; includes IDs in user message so the LLM uses them for file naming (`reasoner/{id}.json`)
- System prompt "Deriving formulation_id" section replaced with "Formulation IDs" — uses provided IDs when available, falls back to slug derivation
- `Reasoner.run` accepts `dict[str, list[str]]` (selected_formulations) or `list[str]` (backward compat)
- `Builder.run` changed from per-paradigm to per-spec dispatch — one sub-agent per JSON spec; results keyed by formulation ID
- `BuilderSubAgent.run` takes `(spec_id, spec_path)` instead of `(paradigm_slug, spec_paths_list)`
- Router: `_do_reason` passes `selected_formulations`; `_do_build` passes `approved_specs`; cascade updated

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/reasoner.py` — `Reasoner.run` accepts dict or list
- `phase1-pablo/src/decisionlab/agents/reasoner_sub.py` — `formulation_ids` param, updated system prompt
- `phase1-pablo/src/decisionlab/agents/builder.py` — per-spec dispatch, `spec_ids` parameter
- `phase1-pablo/src/decisionlab/agents/builder_sub.py` — `(spec_id, spec_path)` signature
- `phase1-pablo/src/decisionlab/router.py` — `_do_reason`, `_do_build`, `_review_reason`, `_execute_rerun_cascade` updated
- `phase1-pablo/src/decisionlab/cli.py` — `build` command updated for new Builder API
- `phase1-pablo/tests/agents/test_reasoner.py` — 1 new test + updated mocks
- `phase1-pablo/tests/agents/test_reasoner_sub.py` — 2 new tests
- `phase1-pablo/tests/agents/test_builder.py` — 2 new tests + rewritten for per-spec API
- `phase1-pablo/tests/agents/test_builder_sub.py` — updated call signatures

### Decisions
- Builder changed from per-paradigm to per-spec dispatch — cleaner mapping to formulation IDs, each spec gets independent sub-agent
- `feedback.py` and `web_feedback.py` left unchanged — review_reason/review_build already work with string IDs from spec files
- Cascade Builder re-run filters approved_specs by paradigm ID prefix (e.g. `T01-P01-`) and merges results instead of overwriting
