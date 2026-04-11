---
id: P3-001
title: Cross-formulation comparison table en Formalizer
status: done
kind: strike
phase: 3
heat: formulation
priority: 1
blocked_by: []
created: 2026-04-10
updated: 2026-04-11
---

# P3-001: Cross-formulation comparison table en Formalizer

## Objective
El FormalizerSubAgent genera una tabla comparativa al final de cada `formulations/{slug}.md` que compare las 2-3 formulaciones del mismo paradigma entre sí.

## Requirements
- Modificar `FORMALIZER_SUB_SYSTEM_PROMPT` en `formalizer_sub.py` para añadir al output format:
  ```
  ## Cross-formulation comparison

  | Aspect | Formulation 1: {name} | Formulation 2: {name} | Formulation 3: {name} |
  |--------|----------------------|----------------------|----------------------|
  | Framework | {e.g., ODE / Algebraic / Probabilistic} | ... | ... |
  | Key variables | {list} | {list} | {list} |
  | Core equation | {main equation} | ... | ... |
  | Decision mechanism | {how action is selected} | ... | ... |
  | Strengths | {brief} | ... | ... |
  | Limitations | {brief} | ... | ... |
  ```
- La tabla se genera al final del archivo, después de todas las formulaciones
- Usa IDs de formulación (F01, F02...) si disponibles del registry (Phase 1)
- La comparación debe ser sustantiva: diferencias reales en enfoque, no superficiales

## Acceptance Criteria
- [x] FORMALIZER_SUB_SYSTEM_PROMPT incluye instrucciones para cross-formulation comparison
- [x] Cada formulations/{slug}.md generado contiene la tabla al final
- [x] La tabla compara framework, variables, ecuaciones, mecanismo de decisión, strengths/limitations
- [x] La comparación refleja diferencias reales entre formulaciones

## Files Likely Affected
- `src/decisionlab/agents/formalizer_sub.py` — FORMALIZER_SUB_SYSTEM_PROMPT

## Context
Phase spec: `docs/specs/phase1-improvements/phase-3-cross-formulation.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `formulation`

## Completion Summary

**Commit:** `06237a8` — `feat[formalizer]: cross-formulation comparison table in output format (P3-001)`

### What was built
- Added `## Cross-formulation comparison` section to `FORMALIZER_SUB_SYSTEM_PROMPT` output format
- Table compares Framework, Key variables, Core equation, Decision mechanism, Strengths, Limitations
- Instruction to drop third column when only 2 formulations are generated
- Explicit instruction that comparison must be substantive, not superficial

### Files created/modified
- `phase1-pablo/src/decisionlab/agents/formalizer_sub.py` — extended output format in system prompt
- `phase1-pablo/tests/agents/test_formalizer_sub.py` — added `test_system_prompt_includes_cross_formulation_comparison`

### Decisions
- Used formulation numbers (Formulation 1, 2, 3) instead of F-IDs in column headers because F-IDs are assigned post-hoc by the router, not available to FormalizerSubAgent at generation time (AC3 in phase spec left unchecked)
