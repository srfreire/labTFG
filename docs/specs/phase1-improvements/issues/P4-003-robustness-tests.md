---
id: P4-003
title: Tests de robustez con input absurdo
status: in-progress
kind: strike
phase: 4
heat: tests
priority: 2
blocked_by: [P4-001, P4-002]
created: 2026-04-10
updated: 2026-04-11
---

# P4-003: Tests de robustez con input absurdo

## Objective
Tests automatizados que envían input absurdo/sin sentido a cada agente y verifican que manejan la situación sin crashear.

## Requirements
- Tests en `tests/` que:
  - Envían un problema sin sentido al Researcher (e.g., "asdfghjkl", "🎉🎉🎉")
  - Envían un deep report incoherente al FormalizerSubAgent
  - Envían formulaciones sin sentido lógico al ReasonerSubAgent
  - Envían un JSON spec roto/absurdo al BuilderSubAgent
- Cada test verifica que:
  - El agente no crashea (no exceptions no capturadas)
  - El agente detecta el input inválido (gracias a P4-001/P4-002)
  - El output indica claramente que algo está mal
- Se pueden usar mocks del LLM client para controlar las respuestas y no gastar API calls en tests

## Acceptance Criteria
- [ ] Tests de robustez para cada agente con input absurdo
- [ ] Ningún test crashea — todos manejan el error gracefully
- [ ] Los agentes con validación (P4-001/P4-002) reportan problemas claros
- [ ] Tests pasan en CI sin API calls reales (mocked)

## Files Likely Affected
- `tests/test_robustness.py` — nuevo archivo de tests
- Posiblemente `tests/conftest.py` — fixtures para mocked LLM client

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `tests`
