---
id: P4-001
title: Validación de formulaciones en Reasoner
status: done
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
- [x] ReasonerSubAgent detecta formulaciones con ecuaciones incoherentes
- [x] Genera JSON con `"status": "invalid"` y problemas listados cuando detecta issues
- [x] El Router maneja specs inválidos en review_reason sin crashear
- [x] El usuario puede triggear rerun del Formalizer desde la review

## Files Likely Affected
- `src/decisionlab/agents/reasoner_sub.py` — REASONER_SUB_SYSTEM_PROMPT
- `src/decisionlab/router.py` — _review_reason() manejo de status invalid
- `src/decisionlab/feedback.py` — review_reason() opción de rerun formalizer
- `src/decisionlab/web_feedback.py` — same for web mode

## Context
Phase spec: `docs/specs/phase1-improvements/phase-4-agent-validation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `validation`

## Completion Summary

**Commit:** `63925c9` — `feat[reasoner]: validation of formulations in Reasoner (P4-001)`

### What was built
- Validation step added to `REASONER_SUB_SYSTEM_PROMPT` — checks variable definitions, circular equations, decision logic references, parameter defaults, and env mapping consistency
- Invalid formulations produce `{"status": "invalid", "problems": [...]}` JSON instead of a spec
- CLI `review_reason` detects invalid specs, displays problems, offers "Rerun Formalizer?" prompt
- Web `review_reason` sends invalid status + problems to frontend, handles `rerun_formalizer` decisions
- Router `_review_reason` orchestrates Formalizer→Reasoner cascade for paradigms with invalid formulations
- Mock server updated to forward invalid spec data to frontend

### Files created/modified
- `src/decisionlab/agents/reasoner_sub.py` — added Validation section to system prompt with 5 coherence checks and validation report JSON schema
- `src/decisionlab/feedback.py` — `review_reason()` returns 3-tuple `(approved, rejections, formalizer_reruns)`, handles invalid specs with problem display
- `src/decisionlab/web_feedback.py` — same 3-tuple return, sends `status`/`problems` to frontend, handles `rerun_formalizer` decision
- `src/decisionlab/router.py` — `_review_reason()` runs Formalizer→Reasoner cascade for `formalizer_reruns`
- `src/decisionlab/mock_server.py` — REVIEW_REASON block branches on `status == "invalid"`
- `tests/agents/test_reasoner_sub.py` — 2 new tests (prompt validation content)
- `tests/test_feedback_helpers.py` — 4 new tests (CLI invalid spec handling + dedup)
- `tests/test_web_feedback.py` — 3 new tests (web invalid spec handling)
- `tests/test_router_review_reason.py` — 3 new tests (router formalizer rerun cascade)

### Decisions
- Validation is prompt-based (not hardcoded rules) per spec decision — problems are semantic
- Return type of `review_reason()` changed from 2-tuple to 3-tuple to cleanly separate formalizer reruns from normal rejections
- Deduplication guard ensures same paradigm isn't rerun multiple times when multiple specs are invalid
