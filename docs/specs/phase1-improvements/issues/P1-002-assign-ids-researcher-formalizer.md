---
id: P1-002
title: Asignación de IDs en Researcher y Formalizer
status: in-progress
kind: strike
phase: 1
heat: ids
priority: 1
blocked_by: [P1-001]
created: 2026-04-10
updated: 2026-04-10
---

# P1-002: Asignación de IDs en Researcher y Formalizer

## Objective
Integrar el ID registry en las fases de Research y Formalize para que paradigmas y formulaciones reciban IDs automáticos al ser descubiertos/generados.

## Requirements

### Researcher → Paradigm IDs
- En `_review_research` (router.py:210), cuando el usuario aprueba paradigmas, llamar `state.assign_paradigm_id(slug)` para cada paradigma aprobado
- Resolver el TODO de `researcher.py:112`: parsear los paradigm slugs del summary del Researcher para que `approved_paradigms` tenga slugs consistentes con los de los deep reports
- Los IDs se asignan en el orden en que aparecen en `approved_paradigms`

### Formalizer → Formulation IDs
- En `_review_formalize` (router.py:268), cuando el usuario selecciona formulaciones, llamar `state.assign_formulation_id(paradigm_slug, formulation_name)` para cada formulación seleccionada
- Parsear el heading `## Formulation N: {name}` del .md para extraer el nombre descriptivo
- `selected_formulations` pasa de `{slug: [int]}` a `{slug: [formulation_id]}` donde `formulation_id` es el ID del registry (e.g., `T01-P01-F01`)

## Acceptance Criteria
- [ ] Cada paradigma aprobado tiene un ID `T01-P{NN}` en el registry
- [ ] Cada formulación seleccionada tiene un ID `T01-P{NN}-F{NN}` en el registry
- [ ] selected_formulations usa IDs del registry en vez de ints
- [ ] IDs se persisten en pipeline_state.json después de cada review

## Files Likely Affected
- `src/decisionlab/router.py` — _review_research(), _review_formalize()
- `src/decisionlab/feedback.py` — review_research(), review_formalize() (return types may change)
- `src/decisionlab/web_feedback.py` — same as above for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-1-ids-treemap.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `ids`
