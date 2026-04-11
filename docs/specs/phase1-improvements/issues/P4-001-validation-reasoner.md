---
id: P4-001
title: Validación de formulaciones en Reasoner
status: in-progress
kind: strike
phase: 4
heat: validation
priority: 1
blocked_by: []
created: 2026-04-10
updated: 2026-04-11
---

# P4-001: Validación de formulaciones en Reasoner

## Objective
El ReasonerSubAgent valida críticamente las formulaciones recibidas del Formalizer antes de generar el JSON spec, detectando incoherencias lógicas.

## Requirements
- Modificar `REASONER_SUB_SYSTEM_PROMPT` para añadir un paso de validación previo:
  1. Leer la formulación
  2. Verificar coherencia: variables definidas que se usan, ecuaciones no circulares, decision logic referencia ecuaciones existentes, parámetros con defaults razonables
  3. Si OK → proceder a generar spec
  4. Si problemas → generar validation report en JSON con `"status": "invalid"` y lista de problemas, en vez del spec
- El Router (`_review_reason`) debe detectar status "invalid" y mostrarlo al usuario en la review
- El usuario puede decidir: rerun Formalizer para ese paradigma, o skip

## Acceptance Criteria
- [ ] ReasonerSubAgent detecta formulaciones con ecuaciones incoherentes
- [ ] Genera JSON con `"status": "invalid"` y problemas listados cuando detecta issues
- [ ] El Router maneja specs inválidos en review_reason sin crashear
- [ ] El usuario puede triggear rerun del Formalizer desde la review

## Files Likely Affected
- `src/decisionlab/agents/reasoner_sub.py` — REASONER_SUB_SYSTEM_PROMPT
- `src/decisionlab/router.py` — _review_reason() manejo de status invalid
- `src/decisionlab/feedback.py` — review_reason() opción de rerun formalizer
- `src/decisionlab/web_feedback.py` — same for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `validation`
