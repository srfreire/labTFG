---
id: P2-005
title: Cross-paradigm table reformateada (zonas x paradigmas)
status: done
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
- [x] RESEARCHER_SYSTEM_PROMPT contiene instrucciones para la tabla matriz
- [x] report.md tiene cross-paradigm table con zonas como columnas y paradigmas como filas
- [x] Celdas usan ✓/✗ para indicar relevancia
- [x] Todas las zonas de todos los deep reports aparecen como columnas

## Files Likely Affected
- `src/decisionlab/agents/researcher.py` — RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `summary-report`

## Completion Summary

**Commit:** `5c41656` — `feat[researcher]: add cross-paradigm interaction map matrix to report format (P2-005)`

### What was built
- Added `## Cross-paradigm interaction map` section to `RESEARCHER_SYSTEM_PROMPT` output format
- Instructions tell the LLM to collect all brain regions from `## Primary Locus` sections of deep reports, use them as columns, paradigms as rows, and mark ✓/✗ relevance
- Updated process step 5 to also extract `## Primary Locus` from deep reports (not just References)

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/researcher.py` — added matrix table instructions to RESEARCHER_SYSTEM_PROMPT
- `phase1-pablo/tests/agents/test_researcher.py` — added test verifying prompt contains cross-paradigm matrix instructions

### Decisions
- No deviations from spec
