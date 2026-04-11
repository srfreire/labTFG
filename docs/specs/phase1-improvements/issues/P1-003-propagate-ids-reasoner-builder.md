---
id: P1-003
title: Propagación de IDs a Reasoner y Builder
status: in-progress
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
- [ ] JSON specs se nombran con el ID del registry (e.g., `T01-P01-F01.json`)
- [ ] Modelos Python se nombran con el ID del registry (e.g., `T01-P01-F01_model.py`)
- [ ] approved_specs contiene IDs del registry
- [ ] build_results usa IDs del registry como keys
- [ ] ReasonerSubAgent no construye formulation_id — lo recibe como parámetro

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
