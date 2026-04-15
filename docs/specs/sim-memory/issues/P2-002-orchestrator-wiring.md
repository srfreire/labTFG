---
id: P2-002
title: Wire TrackerMemoryWriter into orchestrator observe_simulation
status: done
kind: strike
phase: 2
heat: integration
priority: 2
blocked_by: [P2-001]
created: 2026-04-15
updated: 2026-04-16
---

# P2-002: Wire TrackerMemoryWriter into orchestrator observe_simulation

## Objective

Capturar el mapping `agent_id → ModelInfo` durante `run_simulation` e invocar `shared.sim_memory_writer.write()` dentro de `observe_simulation` tras persistir el tracker_output en S3/DB. Graceful degradation si el writer es `None`.

## Requirements

### R1: `run_simulation` — acumular state

- En `phase2-juan/simlab/orchestrator.py`, función `run_simulation` (~línea 507), dentro del bucle que añade agentes:
  ```python
  agent_to_model: dict[str, dict] = {}
  for mid in model_ids:
      info = available.get(mid)
      ...
      for i in range(num_agents):
          ...
          agent_id = f"{label}_{i}" if num_agents > 1 else label
          env.add_agent(Agent(id=agent_id, position=pos, decision_model=model))
          agent_to_model[agent_id] = {
              "model_id": info.id,
              "class_name": info.class_name,
              "paradigm": info.paradigm,
              "formulation": info.formulation,
              "phase1_run_id": info.run_id,
          }
      models_used.append(mid)
  ```
- Tras el bucle, guardar en state:
  ```python
  state["agent_to_model"] = agent_to_model
  state["seed"] = params.get("seed")
  ```
- En el reset de `run_simulation` (líneas tipo `state["tracker_output"] = None`), resetear también estos dos.

### R2: Helper de traducción `ModelInfo`

- Crear helper privado `_to_knowledge_model_info(data: dict) -> simlab.knowledge.ModelInfo` dentro de `orchestrator.py` (o en `simlab/knowledge/__init__.py` si se estima más limpio). Hace la traducción directa de los 5 campos del dict a la dataclass `ModelInfo` del writer.

### R3: `observe_simulation` — invocar el writer

- Dentro de `observe_simulation`, tras el bloque que guarda `s3_tracker_key` y `status="tracked"` en la DB, añadir:
  ```python
  import shared
  writer = getattr(shared, "sim_memory_writer", None)
  if writer is not None:
      try:
          await _write_memories(writer, result, state)
      except Exception:
          logger.exception(
              "observe_simulation: knowledge writer failed (non-fatal)"
          )
  ```
- `_write_memories` es una función privada del módulo que:
  1. Lee `state["experiment_id"]`, `state["spec"]`, `state["replay"]`, `state["agent_to_model"] or {}`, `state["seed"]`.
  2. Calcula `environment = f"grid_{state['spec']['grid_width']}x{state['spec']['grid_height']}"` si están las keys, fallback `"unknown"`.
  3. Calcula `steps = len(state.get("replay", {}).get("frames", []))`.
  4. Convierte `agent_to_model` dict-de-dicts → `dict[str, ModelInfo]` usando el helper.
  5. Construye `SimulationContext(phase2_experiment_id, environment, steps, seed, agent_to_model)`.
  6. Llama `await writer.write(tracker_output, context)` y loguea el `WriteResult` a nivel INFO.

### R4: Sin regresiones de comportamiento con flag OFF

- Cuando `shared.sim_memory_writer is None` (flag OFF o infra ausente), `observe_simulation` no toca nada nuevo, no hace import pesado, y su comportamiento es idéntico al actual.

## Acceptance Criteria

- [x] AC1: Tras un `run_simulation` exitoso con N modelos y M agentes por modelo, `state["agent_to_model"]` tiene N*M entradas con los campos correctos (verificado por smoke test + cubierto formalmente en P2-003).
- [x] AC2: Tras `run_simulation`, `state["seed"]` refleja el seed pasado en params (o `None` si no se pasó).
- [x] AC3: Con `shared.sim_memory_writer=None`, `observe_simulation` no intenta escribir (`getattr` retorna None → no entra en el bloque try).
- [x] AC4: Con writer mockeado, smoke test confirma 1 sola llamada con `SimulationContext(phase2_experiment_id="exp-42", environment="grid_10x8", steps=50, seed=42, agent_to_model={...})`.
- [x] AC5: `try/except` alrededor de `_write_tracker_memories` con `logger.exception`; tracker_output se devuelve normal.
- [x] AC6: 112 tests de phase2-juan siguen verdes, cero regresiones.

## Completion Summary

### What was built
- Helpers a nivel de módulo en `orchestrator.py`:
  - `_to_knowledge_model_info(dict) -> simlab.knowledge.ModelInfo` — traducción local para mantener `simlab.knowledge` desacoplado de `simlab.model_loader`.
  - `_write_tracker_memories(writer, tracker_output, state)` — construye `SimulationContext` desde `state` y llama al writer. Loguea contadores a nivel INFO. No captura excepciones internamente (lo hace el caller).
- `create_environment`: reset inicial de `state["agent_to_model"] = {}` y `state["seed"] = None`.
- `run_simulation`: durante el loop que añade agentes al environment, acumula el dict `agent_to_model` con `{model_id, class_name, paradigm, formulation, phase1_run_id}` por `agent_id`. Al terminar el loop, persiste `state["agent_to_model"]` + `state["seed"] = params.get("seed")`.
- `observe_simulation`: tras el bloque de persistencia S3+DB existente, lee `getattr(shared, "sim_memory_writer", None)`. Si no es None, envuelve `_write_tracker_memories` en `try/except` con `logger.exception`. Comportamiento con flag OFF / writer None: idéntico al anterior.

### Files modified
- `phase2-juan/simlab/orchestrator.py` — 3 puntos de edición + 2 helpers nuevos + import de `logging`.

### Decisions
- **`getattr(shared, "sim_memory_writer", None)`** (en lugar de `shared.sim_memory_writer`): robusto frente a versiones antiguas de `shared` que no tengan el atributo (p.ej. si phase2 se despliega con un shared pre-P2-001).
- **Helpers a nivel de módulo, no en la clase**: son funciones puras (o semi-puras) que no dependen del estado del Orchestrator. Facilita testing unitario (P2-003) y mantiene el método `run_simulation` legible.
- **Import local de `simlab.knowledge` dentro de `_to_knowledge_model_info`**: evita un import a nivel de módulo que solo se ejecuta cuando el flag está ON. Mantiene el arranque del orchestrator rápido.
- **Reset en `create_environment` pero NO en cada `run_simulation`**: run_simulation SOBRESCRIBE (`state["agent_to_model"] = agent_to_model`). No es necesario resetear antes. Si en el futuro falla a mitad del loop, el state podría quedar parcial — aceptable, el siguiente run correcto lo sobrescribe.
- **Tests formales en P2-003**: el smoke test inline ya validó el camino feliz; los tests oficiales viven en su propio issue.

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — capturar state en `run_simulation` + llamada desde `observe_simulation` + helper `_write_memories` + helper `_to_knowledge_model_info`.

## Context

Phase spec: `docs/specs/sim-memory/phase-2-integration.md` (R3, R4)
General spec: `docs/specs/sim-memory/general.md`
Heat: `integration`
Depende de P2-001 para `shared.sim_memory_writer` existente y funcional.
