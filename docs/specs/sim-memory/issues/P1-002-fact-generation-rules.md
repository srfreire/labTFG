---
id: P1-002
title: Implement fact generation rules with pure helpers and tests
status: todo
kind: strike
phase: 1
heat: writer
priority: 2
blocked_by: [P1-001]
created: 2026-04-15
updated: 2026-04-15
---

# P1-002: Implement fact generation rules with pure helpers and tests

## Objective

Implementar las reglas deterministas que convierten el JSON del Tracker en una lista de facts (texto + importance + memory_type + metadata). Todo en funciones puras, sin I/O, completamente testables en aislamiento.

## Requirements

- Crear `phase2-juan/simlab/knowledge/facts.py` con:
  - Dataclass interno `FactSpec(text: str, importance: float, memory_type: str, metadata: dict)`.
  - `build_summary_fact(tracker: dict, context: SimulationContext) -> FactSpec | None` — retorna None si no hay `summary` o está vacío; en comparison run añade `metadata["models_compared"]`.
  - `build_trajectory_facts(tracker: dict, context: SimulationContext) -> list[FactSpec]` — itera `trajectories.items()`, resuelve `ModelInfo` por `agent_id`, formatea `top_3_actions`. Si `agent_id` no está en `context.agent_to_model`, skip + warning log.
  - `build_episode_facts(tracker: dict, context: SimulationContext) -> tuple[list[FactSpec], int]` — retorna `(kept_facts, filtered_count)`. Filtra `{foraging_success, exploration, exploitation}`. Maneja `step` como int o `[start, end]`. Importance por tipo (starvation=9, state_change=8, foraging_failure=7, default=6).
  - `build_all_facts(tracker: dict, context: SimulationContext) -> tuple[list[FactSpec], int]` — orquestador puro que llama a los 3 anteriores y concatena, devolviendo `(facts, episodes_filtered_count)`.
- Texto de los facts exactamente como en spec R4 (inglés, con prefijo de modelo/env, formato de acciones top-3).
- Metadata común construida por helper interno `_base_metadata(context, model_info) -> dict`.

- Tests en `phase2-juan/tests/knowledge/test_fact_rules.py`:
  - Caso 1 modelo / 2 agentes: 1 summary + 2 trajectories + mezcla de episodes (algunos filtrados, algunos no). Verificar textos exactos, importance, memory_type, metadata.
  - Caso comparison run (2 modelos, 2 agentes cada uno): verificar que cada fact lleva el `paradigm`/`formulation` del modelo correcto; que summary lleva `models_compared`.
  - Caso filtrado: episodes con types {foraging_success, exploration, exploitation} se descartan y suman a `filtered_count`.
  - Caso episode con step range `[100, 120]`: texto contiene `steps=100..120`, metadata contiene `step_start=100, step_end=120`.
  - Caso agent_id desconocido: trajectory/episode se skippean con warning, no crashea.
  - Caso tracker vacío (`{"summary": "", "trajectories": {}, "episodes": []}`): `build_all_facts` retorna `([], 0)`.
  - Caso summary en español: se prefija encabezado inglés, summary en crudo dentro de comillas.
  - Caso episode type desconocido (e.g. `"weird_behavior"`): se conserva con importance=6.

## Acceptance Criteria

- [ ] AC1: Las 4 funciones públicas existen y tienen las firmas exactas.
- [ ] AC2: Los textos generados siguen las plantillas del spec R4 al pie de la letra.
- [ ] AC3: Los 8 casos de test pasan.
- [ ] AC4: Ningún fact puro hace I/O ni llamadas async — todas son funciones síncronas puras.
- [ ] AC5: `build_all_facts` concatena en orden: [summary, trajectories..., episodes...].

## Files Likely Affected

- `phase2-juan/simlab/knowledge/facts.py` — nuevo.
- `phase2-juan/tests/knowledge/test_fact_rules.py` — nuevo.

## Context

Phase spec: `docs/specs/sim-memory/phase-1-core-writer.md` (R4, R7)
General spec: `docs/specs/sim-memory/general.md`
Heat: `writer`
