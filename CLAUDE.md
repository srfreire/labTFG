# CLAUDE.md

## Project Overview

**TFG** (Trabajo de Fin de Grado, Computer Engineering, USC) by **Juan Freire Alvarez** and **Pablo Pazos Parada**, supervised by Eduardo Manuel Sanchez Vila.

**Title**: Virtual laboratory for simulation and analysis of human decision-making paradigms using intelligent agents.

- **Phase 1 (Pablo Pazos Parada)** — Agent pipeline (Researcher → Reasoner → Builder) that generates decision-making model code from paradigm descriptions.
- **Phase 2 (Juan Freire Alvarez)** — Infrastructure to simulate, observe, analyze and report on those agents.

## Repository Structure

```
phase1-pablo/                              — Phase 1: agent pipeline
  src/decisionlab/agents/                  — Researcher, Reasoner, Builder agents
  examples/sample-run/builder/             — Generated model files (*_model.py + tests)
phase2-juan/                               — Phase 2: virtual lab
  simlab/                                  — Python package (environment, agents, API, CLI)
  web/                                     — React frontend (dashboard + chat)
  docs/DESIGN.md                           — Virtual lab design doc
docs/                                      — Reference documents (Denis Yamunaque's TFM)
```

## Phase 2 Agents

1. **Architect** — generates environment specs from natural language
2. **Tracker** — records events, episodes, decision trajectories
3. **Analyst** — identifies behavior-objective patterns
4. **Reporter** — generates PDF reports via LaTeX
5. **Orchestrator** — coordinates the pipeline, interactive chat

## DecisionModel Contract

Both phases share this interface (duck typing, no adapter needed):

```python
def decide(self, perception: dict) -> Action      # read-only, pick action
def update(self, action, reward, new_perception)   # mutate state
def get_state(self) -> dict                        # expose internals
```

Perception keys: `x, y, grid_width, grid_height, step, resources, last_action_result`.

## Running

```bash
# CLI chat
cd phase2-juan && uv run simlab

# Web UI
uvicorn simlab.api:app --port 8000    # backend
cd web && npm run dev                  # frontend (Vite → localhost:5173)
```

Requires: `.env` in `phase2-juan/` with `OPENROUTER_API_KEY`.

## Current Status

- All 5 agents implemented and working (CLI + Web)
- Phase 1 Builder operational — generates self-contained Python models
- Models in `phase1-pablo/examples/sample-run/builder/` are compatible with Phase 2 Environment
- Web UI: functional but needs polish (grid visualization, data cards, responsive)

## Next Steps

- [ ] Dynamic model loader: discover + load Phase 1 models from `builder/`
- [ ] Orchestrator: present available models to user before simulation
- [ ] Web UI: simulation grid with animated replay
- [ ] Web UI: richer data cards (tracker metrics, analyst patterns)
- [ ] Web UI: responsive layout, animation polish
- [ ] Future: real-time WebSocket streaming during simulation
