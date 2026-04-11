---
id: P4-002
title: Validación de specs en Builder
status: done
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
- [x] BuilderSubAgent detecta specs con lógica ambigua o no implementable
- [x] Genera report con `"status": "invalid"` cuando detecta problemas
- [x] El Router maneja builds inválidos en review_build sin crashear
- [x] El usuario puede triggear rerun del Reasoner desde la review

## Files Likely Affected
- `src/decisionlab/agents/builder_sub.py` — BUILDER_SUB_SYSTEM_PROMPT
- `src/decisionlab/router.py` — _review_build() manejo de status invalid
- `src/decisionlab/feedback.py` — review_build() opción de rerun reasoner
- `src/decisionlab/web_feedback.py` — same for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `validation`

## Completion Summary

**Commit:** `6eb7f2e` — `feat[builder]: validation of specs in Builder (P4-002)`

### What was built
- Validation section added to `BUILDER_SUB_SYSTEM_PROMPT` — checks decision logic implementability, env_mapping perception keys, and expected_behaviors testability
- Invalid specs produce `builder/{fid}_validation.json` with `{"status": "invalid", "problems": [...]}` instead of model/test files
- CLI `review_build` reads validation reports, displays problems, offers "Rerun Reasoner?" prompt
- Web `review_build` sends invalid status + problems to frontend, handles `rerun_reasoner` decisions
- Router `_review_build` handles structured 3-tuple return with Reasoner→Builder cascade for invalid builds
- Stale validation files cleaned up after successful Reasoner→Builder rerun
- Mock server updated to include validation reports in REVIEW_BUILD data

### Files created/modified
- `src/decisionlab/agents/builder_sub.py` — added Validation section to system prompt with 3 implementability checks and validation report JSON schema
- `src/decisionlab/feedback.py` — `review_build()` returns 3-tuple `(approved, rejections, reasoner_reruns)`, handles invalid builds with problem display
- `src/decisionlab/web_feedback.py` — same 3-tuple return, sends `status`/`problems` to frontend, handles `rerun_reasoner` decision
- `src/decisionlab/router.py` — `_review_build()` runs Reasoner→Builder cascade for `reasoner_reruns`, cleans stale validation files
- `src/decisionlab/mock_server.py` — REVIEW_BUILD block includes validation reports
- `tests/agents/test_builder_sub.py` — 2 new tests (prompt validation content)
- `tests/test_feedback_helpers.py` — 4 new tests (CLI invalid build handling + dedup)
- `tests/test_web_feedback.py` — 3 new tests (web invalid build handling)
- `tests/test_router_review_build.py` — 4 new tests (router reasoner rerun cascade + validation cleanup)

### Decisions
- Validation is prompt-based (not hardcoded rules) per spec decision — problems are semantic
- Return type of `review_build()` changed from `str | None` to 3-tuple to match P4-001 pattern
- Validation reports written to `builder/{fid}_validation.json` (separate from model files)
- Stale validation files cleaned after successful rerun to prevent infinite loop
