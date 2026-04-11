---
id: P2-003
title: Key concepts en deep reports
status: in-progress
kind: strike
phase: 2
heat: deep-report
priority: 2
blocked_by: [P2-002]
created: 2026-04-10
updated: 2026-04-11
---

# P2-003: Key concepts en deep reports

## Objective
Añadir sección `## Key Concepts` al output format del DeepResearcher — un glosario breve de términos/conceptos que aparecen recurrentemente en los papers del paradigma.

## Requirements
- Modificar `DEEP_RESEARCHER_SYSTEM_PROMPT` en `deep_researcher.py` para incluir:
  ```
  ## Key Concepts
  - **{Term}**: {brief definition as used in this paradigm's literature}
  ```
- Posicionar después de `## Primary Locus` y antes de `## Identified variables`
- Los conceptos deben ser términos técnicos específicos del paradigma, no genéricos

## Acceptance Criteria
- [ ] DEEP_RESEARCHER_SYSTEM_PROMPT incluye sección ## Key Concepts en el output format
- [ ] Deep reports generados contienen glosario de términos técnicos del paradigma

## Files Likely Affected
- `src/decisionlab/agents/deep_researcher.py` — DEEP_RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `deep-report`
