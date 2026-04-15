---
id: P2-002
title: Wire TrackerMemoryWriter into orchestrator observe_simulation
status: todo
kind: strike
phase: 2
heat: integration
priority: 2
blocked_by: [P2-001]
created: 2026-04-15
updated: 2026-04-15
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

- [ ] AC1: Tras un `run_simulation` exitoso con N modelos y M agentes por modelo, `state["agent_to_model"]` tiene N*M entradas con los campos correctos (`model_id`, `class_name`, `paradigm`, `formulation`, `phase1_run_id`).
- [ ] AC2: Tras `run_simulation`, `state["seed"]` refleja el seed pasado en params (o `None` si no se pasó).
- [ ] AC3: Con `shared.sim_memory_writer=None`, `observe_simulation` no intenta escribir y no añade overhead.
- [ ] AC4: Con writer mockeado, `observe_simulation` lo invoca exactamente una vez con un `SimulationContext` que tiene `phase2_experiment_id`, `environment="grid_WxH"` correcto, `steps`, `seed`, y `agent_to_model` poblado.
- [ ] AC5: Una excepción inesperada del writer es capturada (`logger.exception`) y `observe_simulation` devuelve el tracker_output normalmente como si el writer no existiese.
- [ ] AC6: Los 111 tests de phase2 siguen verdes (incluidos los del orchestrator si los hay).

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — capturar state en `run_simulation` + llamada desde `observe_simulation` + helper `_write_memories` + helper `_to_knowledge_model_info`.

## Context

Phase spec: `docs/specs/sim-memory/phase-2-integration.md` (R3, R4)
General spec: `docs/specs/sim-memory/general.md`
Heat: `integration`
Depende de P2-001 para `shared.sim_memory_writer` existente y funcional.
