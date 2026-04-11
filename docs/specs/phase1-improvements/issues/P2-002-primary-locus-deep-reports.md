---
id: P2-002
title: Primary locus en deep reports
status: in-progress
kind: strike
phase: 2
heat: deep-report
priority: 1
blocked_by: []
created: 2026-04-10
updated: 2026-04-11
---

# P2-002: Primary locus en deep reports

## Objective
Añadir sección `## Primary Locus` al output format del DeepResearcher para que cada deep report incluya las regiones cerebrales relevantes del paradigma.

## Requirements
- Modificar `DEEP_RESEARCHER_SYSTEM_PROMPT` en `deep_researcher.py` para incluir la sección:
  ```
  ## Primary Locus
  {Brain regions / neural substrates relevant to this paradigm, with citations}
  ```
- Posicionar después de `## Predictions` y antes de `## Identified variables`
- Las regiones deben estar respaldadas por los papers encontrados

## Acceptance Criteria
- [ ] DEEP_RESEARCHER_SYSTEM_PROMPT incluye sección ## Primary Locus en el output format
- [ ] Deep reports generados contienen la sección con regiones cerebrales citadas

## Files Likely Affected
- `src/decisionlab/agents/deep_researcher.py` — DEEP_RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `deep-report`
