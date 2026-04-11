---
id: P2-004
title: Papers consolidados en report.md
status: done
kind: strike
phase: 2
heat: summary-report
priority: 2
blocked_by: []
created: 2026-04-10
updated: 2026-04-11
---

# P2-004: Papers consolidados en report.md

## Objective
El Researcher consolida en `report.md` una sección `## References` con todos los papers citados en todos los deep reports.

## Requirements
- Modificar `RESEARCHER_SYSTEM_PROMPT` en `researcher.py` para instruir al Researcher a:
  - Leer las secciones `## References` de todos los deep reports (ya tiene `read_report` tool)
  - Generar una sección `## References` al final de `report.md` con la lista consolidada y deduplicada
- No busca papers nuevos — solo agrega los existentes de los deep reports
- Formato de cada referencia: `- {Author (Year)} - {Title} — DOI: {doi}` (DOI si disponible)

## Acceptance Criteria
- [x] RESEARCHER_SYSTEM_PROMPT instruye a consolidar papers de deep reports
- [x] report.md contiene sección ## References con papers de todos los deep reports
- [x] Papers deduplicados (misma referencia en múltiples deep reports aparece una sola vez)

## Files Likely Affected
- `src/decisionlab/agents/researcher.py` — RESEARCHER_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `summary-report`

## Completion Summary

**Commit:** `9940cc4` — feat[researcher]: consolidate deep report references in report.md (P2-004)

### What was built
- Modified `RESEARCHER_SYSTEM_PROMPT` to instruct the Researcher to call `read_report` for every paradigm after deep research completes
- Added `## References` section to the output format with deduplication and DOI instructions
- References are sorted alphabetically by first author surname

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/researcher.py` — Updated RESEARCHER_SYSTEM_PROMPT (process steps 4-6 and output format)

### Decisions
- No code logic changes needed — the Researcher already has `read_report` tool access; only prompt instructions were missing
- Reference format follows spec: `- {Author (Year)} - {Title} — DOI: {doi}` with DOI omitted when unavailable
