---
id: P2-002
title: Primary locus en deep reports
status: done
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
- [x] DEEP_RESEARCHER_SYSTEM_PROMPT incluye sección ## Primary Locus en el output format
- [x] Deep reports generados contienen la sección con regiones cerebrales citadas

## Files Likely Affected
- `src/decisionlab/agents/deep_researcher.py` — DEEP_RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `deep-report`

## Completion Summary

**Commit:** `488d68a` — `feat[deep-researcher]: add Primary Locus section to deep report output format (P2-002)`

### What was built
- Added `## Primary Locus` section to `DEEP_RESEARCHER_SYSTEM_PROMPT` output format template
- Section instructs the LLM to list brain regions / neural substrates relevant to the paradigm, with citations

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — added Primary Locus section between Predictions and Identified variables in the prompt template

### Decisions
- No deviations from spec
