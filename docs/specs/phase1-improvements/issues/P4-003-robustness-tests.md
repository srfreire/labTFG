---
id: P4-003
title: Tests de robustez con input absurdo
status: done
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
- [x] Tests de robustez para cada agente con input absurdo
- [x] Ningún test crashea — todos manejan el error gracefully
- [x] Los agentes con validación (P4-001/P4-002) reportan problemas claros
- [x] Tests pasan en CI sin API calls reales (mocked)

## Files Likely Affected
- `tests/test_robustness.py` — nuevo archivo de tests
- Posiblemente `tests/conftest.py` — fixtures para mocked LLM client

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `tests`

## Completion Summary

**Commit:** `893075a` — `feat[tests]: robustness tests with absurd input for all agents (P4-003)`

### What was built
- 22 robustness tests covering all 4 agents (Researcher, FormalizerSubAgent, ReasonerSubAgent, BuilderSubAgent)
- Tests send absurd input (gibberish, emojis, empty strings, 10K chars, path traversal) and verify graceful handling
- Reasoner tests verify `{"status": "invalid"}` validation reports with problem lists (P4-001)
- Builder tests verify validation reports AND absence of model/test files for invalid specs (P4-002)
- Max-iterations safety tests verify `RuntimeError` instead of infinite hang
- Deep research sub-agent path tested with gibberish paradigm
- All tests use mocked LLM client — zero API calls

### Files created/modified
- `tests/test_robustness.py` — 22 tests across 5 test classes (TestResearcherRobustness, TestFormalizerSubRobustness, TestReasonerSubRobustness, TestBuilderSubRobustness, TestMaxIterationsRobustness)

### Decisions
- Tests placed at `tests/test_robustness.py` (top-level) per issue spec, with local mock helpers instead of importing from `tests/agents/conftest.py` to avoid coupling
- Mock helpers (`_mock_client`, `_assert_invalid_report`) extracted to reduce duplication across test classes
- Max-iterations tests parametrized across all 3 sub-agents for conciseness
