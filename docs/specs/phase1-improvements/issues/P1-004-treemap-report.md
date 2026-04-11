---
id: P1-004
title: Tree map en report.md
status: in-progress
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
- [ ] report.md contiene sección `## Research Tree Map` con la jerarquía completa
- [ ] Tree map muestra IDs y nombres descriptivos para cada nivel
- [ ] Tree map se genera por código, no por LLM
- [ ] Tree map se actualiza si hay reruns que añaden/cambian formulaciones

## Files Likely Affected
- `src/decisionlab/tools/reports.py` — nueva función generate_tree_map()
- `src/decisionlab/router.py` — _review_formalize() llama a generate_tree_map()

## Context
Phase spec: `docs/specs/phase1-improvements/phase-1-ids-treemap.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `treemap`
