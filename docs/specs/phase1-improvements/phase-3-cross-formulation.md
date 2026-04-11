# Phase 3: Cross-formulation table

> Status: current | Created: 2026-04-10 | Last updated: 2026-04-11
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective
El Formalizer genera una tabla comparativa al final de cada archivo de formulaciones que compare las 2-3 formulaciones del mismo paradigma entre sí.

## Requirements

### R1: Cross-formulation comparison table
Al final de cada `formulations/{slug}.md`, el FormalizerSubAgent genera una sección `## Cross-formulation comparison` con una tabla que muestre qué variables, funciones/ecuaciones, y lógica de decisión cambia entre las formulaciones.

Formato esperado:
```
## Cross-formulation comparison

| Aspect | F01: {name} | F02: {name} | F03: {name} |
|--------|-------------|-------------|-------------|
| Variables | ... | ... | ... |
| Key equation | ... | ... | ... |
| Decision mechanism | ... | ... | ... |
| Framework | ODE | Algebraic | Probabilistic |
```

## Acceptance Criteria
- [x] AC1: Cada formulations/{slug}.md contiene sección ## Cross-formulation comparison al final
- [x] AC2: La tabla compara variables, ecuaciones, mecanismo de decisión y framework entre formulaciones
- [ ] AC3: Usa IDs de formulación (F01, F02...) del registry en los headers

## Technical Notes
- FormalizerSubAgent prompt en `formalizer_sub.py:18`
- La instrucción se añade al `FORMALIZER_SUB_SYSTEM_PROMPT`
- El LLM genera la tabla como parte de su output — no es programático
- Los IDs de formulación se pasan como contexto al FormalizerSubAgent (viene de Phase 1)

## Decisions
- La tabla la genera el LLM del Formalizer, no código — porque requiere comprensión semántica de las diferencias
- Se incluye al final de cada .md de formulaciones, no en un archivo separado
