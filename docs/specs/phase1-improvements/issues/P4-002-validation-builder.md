---
id: P4-002
title: Validación de specs en Builder
status: in-progress
kind: strike
phase: 4
heat: validation
priority: 1
blocked_by: [P4-001]
created: 2026-04-10
updated: 2026-04-11
---

# P4-002: Validación de specs en Builder

## Objective
El BuilderSubAgent valida críticamente el JSON spec recibido del Reasoner antes de generar código Python, detectando lógica no implementable.

## Requirements
- Modificar `BUILDER_SUB_SYSTEM_PROMPT` para añadir paso de validación previo:
  1. Leer el JSON spec
  2. Verificar: decision_logic es implementable (pasos concretos, no ambiguos), variables del env_mapping existen en la perception, expected_behaviors son testeables
  3. Si OK → proceder a generar código
  4. Si problemas → generar validation report con `"status": "invalid"` y problemas, en vez del código
- El Router (`_review_build`) debe detectar builds inválidos y mostrarlo al usuario
- El usuario puede decidir: rerun Reasoner para ese spec, o skip

## Acceptance Criteria
- [ ] BuilderSubAgent detecta specs con lógica ambigua o no implementable
- [ ] Genera report con `"status": "invalid"` cuando detecta problemas
- [ ] El Router maneja builds inválidos en review_build sin crashear
- [ ] El usuario puede triggear rerun del Reasoner desde la review

## Files Likely Affected
- `src/decisionlab/agents/builder_sub.py` — BUILDER_SUB_SYSTEM_PROMPT
- `src/decisionlab/router.py` — _review_build() manejo de status invalid
- `src/decisionlab/feedback.py` — review_build() opción de rerun reasoner
- `src/decisionlab/web_feedback.py` — same for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `validation`
