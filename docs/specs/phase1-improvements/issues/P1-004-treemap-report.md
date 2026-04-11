---
id: P1-004
title: Tree map en report.md
status: done
kind: strike
phase: 1
heat: treemap
priority: 2
blocked_by: [P1-002]
created: 2026-04-10
updated: 2026-04-11
---

# P1-004: Tree map en report.md

## Objective
Generar programáticamente un tree map Markdown con la jerarquía T→P→F y sus IDs, insertándolo en report.md después de la fase de Formalizer.

## Requirements
- Nueva función `generate_tree_map(state: PipelineState, reports_dir: Path) -> str` en `tools/reports.py`
- Lee el `id_registry` del state para construir la jerarquía
- Lee los nombres descriptivos de los paradigmas (de los deep reports) y formulaciones (del heading del .md)
- Genera Markdown con tree characters (`├──`, `└──`, `│`)
- Se inserta en `report.md` como nueva sección `## Research Tree Map` al final del report
- Se ejecuta en `_review_formalize` (router.py) después de asignar IDs a formulaciones
- Se regenera si se añaden formulaciones nuevas (rerun)

## Acceptance Criteria
- [x] report.md contiene sección `## Research Tree Map` con la jerarquía completa
- [x] Tree map muestra IDs y nombres descriptivos para cada nivel
- [x] Tree map se genera por código, no por LLM
- [x] Tree map se actualiza si hay reruns que añaden/cambian formulaciones

## Files Likely Affected
- `src/decisionlab/tools/reports.py` — nueva función generate_tree_map()
- `src/decisionlab/router.py` — _review_formalize() llama a generate_tree_map()

## Context
Phase spec: `docs/specs/phase1-improvements/phase-1-ids-treemap.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `treemap`

## Completion Summary

**Commit:** `8e3a357` — `feat[phase1]: generate tree map in report.md after Formalizer (P1-004)`

### What was built
- `generate_tree_map(state)` in `tools/reports.py` — reads `id_registry` to build T→P→F hierarchy with tree characters
- Paradigm names extracted from deep report titles (`# Name — Deep Research`), falls back to slug
- Formulation names extracted from registry keys (`slug::name`)
- Tree map inserted/replaced as `## Research Tree Map` section in `report.md` (code block)
- Regex uses stop anchor (`(?=\n##|\Z)`) to avoid eating subsequent sections on replacement
- Called in `_review_formalize()` after `_convert_formulations_to_ids` + `state.save()`

### Files created/modified
- `phase1-pablo/src/decisionlab/tools/reports.py` — added `generate_tree_map()`, `_paradigm_name_from_deep_report()`, `_DEEP_TITLE_RE`, `_TREE_MAP_SECTION_RE`
- `phase1-pablo/src/decisionlab/router.py` — added `generate_tree_map()` call in `_review_formalize()`
- `phase1-pablo/tests/tools/test_reports.py` — 10 new tests covering: single/multi paradigm, formulations, insertion, replacement on rerun, tree characters, slug fallback, empty registry, missing report.md, section preservation

### Decisions
- Simplified `generate_tree_map` signature to take only `state` (derives `reports_dir` from `state.reports_dir`) per simplifier recommendation
- Single `report.md` read to avoid redundant I/O
- Topic label derived from `report.md` first heading (e.g. `T01: Decision-making paradigms...`)
