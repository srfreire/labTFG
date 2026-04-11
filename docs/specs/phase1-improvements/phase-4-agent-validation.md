# Phase 4: Validación entre agentes

> Status: current | Created: 2026-04-10 | Last updated: 2026-04-11

> References: [general.md](general.md) | [phases.md](phases.md)

## Objective
Cada agente downstream valida críticamente el output del agente anterior antes de procesarlo, detectando incoherencias lógicas y reportándolas en vez de seguir ciegamente.

## Requirements

### R1: Validación en Reasoner
El ReasonerSubAgent, antes de generar el JSON spec, analiza críticamente las formulaciones recibidas:
- Ecuaciones coherentes entre sí (variables definidas que se usan, no hay circulares)
- Decision logic referencia ecuaciones que existen
- Parámetros con defaults razonables
- Si detecta problemas, genera un report de validación en vez del spec y marca el resultado como `"status": "invalid"`

### R2: Validación en Builder
El BuilderSubAgent, antes de generar código, analiza críticamente el JSON spec recibido:
- decision_logic es implementable (no hay pasos ambiguos)
- Variables del env_mapping existen en la perception
- expected_behaviors son testeables
- Si detecta problemas, genera un report de validación y marca como `"status": "invalid"`

### R3: Tests de robustez
Tests automatizados que mandan input absurdo/sin sentido a cada agente y verifican que:
- No crashean
- Detectan el input inválido
- Reportan el problema de forma clara

## Acceptance Criteria
- [x] AC1: Reasoner detecta formulaciones con ecuaciones incoherentes y reporta en vez de generar spec
- [x] AC2: Builder detecta specs con lógica no implementable y reporta en vez de generar código
- [ ] AC3: Tests de robustez pasan para cada agente con input absurdo
- [x] AC4: El pipeline maneja gracefully los status "invalid" (no crashea, informa al usuario)

## Technical Notes
- ReasonerSubAgent prompt en `reasoner_sub.py`
- BuilderSubAgent prompt en `builder_sub.py`
- La validación es parte del prompt del agente — se añaden instrucciones de "validar antes de procesar"
- El Router necesita manejar el status "invalid" en las review stages

## Decisions
- Validación es via prompt engineering, no reglas hardcoded — los problemas son semánticos
- Status "invalid" se propaga al review stage para que el usuario decida (rerun o skip)
