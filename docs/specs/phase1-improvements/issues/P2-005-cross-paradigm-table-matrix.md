---
id: P2-005
title: Cross-paradigm table reformateada (zonas x paradigmas)
status: in-progress
kind: strike
phase: 2
heat: summary-report
priority: 2
blocked_by: [P2-002]
created: 2026-04-10
updated: 2026-04-11
---

# P2-005: Cross-paradigm table reformateada (zonas x paradigmas)

## Objective
Reformatear la cross-paradigm interaction table en report.md para que las columnas sean todas las zonas/regiones cerebrales encontradas y las filas sean paradigmas, con marcas ✓/✗.

## Requirements
- Modificar `RESEARCHER_SYSTEM_PROMPT` en `researcher.py` para instruir al Researcher a generar la tabla en formato matriz:
  ```
  ## Cross-paradigm interaction map

  | Paradigm | Hypothalamus | VTA | Prefrontal cortex | Amygdala | ... |
  |----------|:---:|:---:|:---:|:---:|
  | Homeostatic | ✓ | ✗ | ✗ | ✗ |
  | Hedonic | ✗ | ✓ | ✓ | ✗ |
  ```
- Las columnas se derivan de todos los `## Primary Locus` de los deep reports (requiere P2-002)
- El Researcher lee los deep reports para extraer las zonas y construir la tabla

## Acceptance Criteria
- [ ] RESEARCHER_SYSTEM_PROMPT contiene instrucciones para la tabla matriz
- [ ] report.md tiene cross-paradigm table con zonas como columnas y paradigmas como filas
- [ ] Celdas usan ✓/✗ para indicar relevancia
- [ ] Todas las zonas de todos los deep reports aparecen como columnas

## Files Likely Affected
- `src/decisionlab/agents/researcher.py` — RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `summary-report`
