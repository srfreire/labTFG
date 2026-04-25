---
id: P1-003
title: Agent prompt hooks and conditional tool injection (Architect, Analyst, Reporter)
status: done
kind: strike
phase: 1
heat: prompts
priority: 2
blocked_by: [P1-001]
created: 2026-04-17
updated: 2026-04-25
---

# P1-003: Agent prompt hooks and conditional tool injection (Architect, Analyst, Reporter)

## Objective

Permitir que Architect, Analyst y Reporter inviten a `retrieve_context` en su razonamiento. La tool se inyecta solo si `ENABLE_KNOWLEDGE_READ=True`; los prompts ganan una sección condicional que menciona cuándo consultar el KG.

## Requirements

- **Architect** (`phase2-juan/simlab/architect.py`):
  - Cuando `ENABLE_KNOWLEDGE_READ=True`, añadir la tool a la lista que el agent loop expone.
  - Ampliar `ARCHITECT_SYSTEM_PROMPT` con una sección condicional (string concatenation con un suffix cuando flag ON):
    ```
    ## Knowledge Backbone access
    If the user describes a scientific paradigm (e.g. "homeostatic regulation",
    "hedonic control", "reinforcement learning with drive reduction"), call
    `retrieve_context(query="<paradigm name + key concepts>", namespace="paradigm")`
    BEFORE generating the spec. Use the returned facts (variables, postulates,
    observed ranges) to propose an environment that is scientifically grounded.
    ```
  - Typical query: `retrieve_context(query=f"environments and variables for paradigm X", namespace="paradigm")`.

- **Analyst** (`phase2-juan/simlab/analyst.py`):
  - Misma estrategia: tool + prompt extension.
  - Sección del prompt:
    ```
    ## Postulate cross-check
    After identifying behavioural patterns, call
    `retrieve_context(query="postulates for paradigm <name>", namespace="paradigm")`
    and verify whether observations match known postulates. Cite the Postulate
    ID (P1, P2, ...) when reporting a match or mismatch.
    ```

- **Reporter** (`phase2-juan/simlab/reporter.py`):
  - Misma estrategia.
  - Sección del prompt:
    ```
    ## References grounding
    Before writing the "References" LaTeX section, call
    `retrieve_context(query="papers and authors for paradigm <name>", top_k=10)`
    and use the returned Paper nodes (title, year, DOI, citation_count) to build
    real citations. Fall back to generic references only if the retrieval returns
    zero results.
    ```

- **Tool injection pattern** (compartido entre los 3):
  - Cada agent actualmente construye su propia lista de tools. Añadir parámetro `extra_tools: list[dict] | None = None` al constructor (o al `run()` method, según cómo esté la clase) — cuando el caller pasa `retrieve_context` tool, se append a la lista.
  - El Orchestrator, al construir cada agent, decide pasar o no la tool según el flag (toma la decisión en un solo punto).
  - El tool handler también se inyecta: el agent loop necesita saber cómo llamar a `retrieve_context` — reutilizar el mismo handler del Orchestrator (P1-002) o registrar uno por agent. **Recomendación**: registrar una sola vez en un helper compartido `simlab/recall/agent_tools.py` que retorna `(tools, registry)` listos para consumir.

- **Backward compat**: con `ENABLE_KNOWLEDGE_READ=False`, el constructor de cada agent se llama con `extra_tools=None` (o no se pasa el kw arg) y el prompt ORIGINAL se usa sin la sección condicional.

## Acceptance Criteria

- [x] AC1: Con flag OFF, Architect/Analyst/Reporter exponen exactamente la misma lista de tools y prompts que antes (snapshot test).
- [x] AC2: Con flag ON, la tool `retrieve_context` aparece en la lista de cada uno de los 3 agentes y el prompt efectivo incluye la sección condicional correspondiente.
- [x] AC3: Cada agente llama al mismo handler central (el que define `simlab/recall/agent_tools.py` o el del Orchestrator), no reimplementa.
- [x] AC4: La sección del prompt por agente menciona explícitamente la query típica (namespace y topic).
- [x] AC5: 115+27 tests siguen verdes.

## Files Likely Affected

- `phase2-juan/simlab/architect.py` — prompt + tool injection path.
- `phase2-juan/simlab/analyst.py` — idem.
- `phase2-juan/simlab/reporter.py` — idem.
- `phase2-juan/simlab/recall/agent_tools.py` — nuevo helper compartido (opcional según diseño).
- `phase2-juan/simlab/orchestrator.py` — posiblemente pasa `extra_tools` al construir cada agent; no toca su propia tool (eso es P1-002).

## Context

Phase spec: `docs/specs/sim-recall/phase-1-context-retrieval.md` (R4, R5, R6)
General spec: `docs/specs/sim-recall/general.md`
Heat: `prompts`
Depende de P1-001 (wrapper + schema). Paralelizable con P1-002.

## Completion Summary

**Commit:** `7eb54a1` — feat[sim-recall]: P1-003 agent prompt hooks and conditional tool injection

### What was built
- `simlab/recall/agent_tools.py` — shared `build_recall_extras(stage)` returning `(tools, registry, prompt_section)` per agent
- Per-agent prompt sections: Architect queries paradigms, Analyst cross-checks postulates, Reporter grounds references
- Architect/Analyst/Reporter gain `extra_tools`, `extra_registry`, `prompt_suffix` on `run()` — zero-cost when flag off
- Orchestrator pre-builds extras via `_recall_kwargs()` helper, passes to all 3 agent calls
- 10 tests covering helper API, flag on/off per agent, handler stage prefix

### Files created/modified
- `phase2-juan/simlab/recall/agent_tools.py` — new shared helper
- `phase2-juan/simlab/recall/__init__.py` — added `build_recall_extras` export
- `phase2-juan/simlab/architect.py` — `extra_tools`/`extra_registry`/`prompt_suffix` on `run()`
- `phase2-juan/simlab/analyst.py` — same
- `phase2-juan/simlab/reporter.py` — same
- `phase2-juan/simlab/orchestrator.py` — `_recall` dict + `_recall_kwargs()` + try/except guard
- `phase2-juan/tests/recall/test_agent_wiring.py` — 10 new tests

### Decisions
- Used `prompt_suffix` string concat instead of template — simpler, safe default `""`
- Import wrapped in try/except in orchestrator (reviewer suggestion) — flag ON with broken infra degrades gracefully
- Handler per-agent uses `stage=f"phase2-{stage}"` so Pablo's CRAG context is agent-specific
