# CLAUDE.md

## Project Overview

This is a **TFG** (Trabajo de Fin de Grado / Bachelor's Thesis, Computer Engineering, USC) by **Juan Freire Alvarez** and **Pablo Pazos Parada**, supervised by Eduardo Manuel Sanchez Vila.

**Title**: Virtual laboratory for simulation and analysis of human decision-making paradigms using intelligent agents.

The project is split into **two complementary parts**, one per author:

- **Phase 1 (Pablo Pazos Parada)** — Modeling autonomous agents based on decision-making paradigms. Designs the agent pipeline (Researcher, Reasoner, Builder) that builds the decision-making agents themselves.
- **Phase 2 (Juan Freire Alvarez)** — Building the infrastructure to simulate, observe, analyze and document the behavior of those agents.

## Repository Structure

```
CLAUDE.md
Acordo_TFG_JuanFreireAlvarez_firmado.pdf  — Official TFG agreement with objectives
docs/                                      — Reference documents
  TFM_v_FINAL.pdf                          — Reference paper (Denis Yamunaque's TFM, NOT Juan's thesis)
  RESUMEN_TFM_Denis.md                     — Summary of the reference paper
  survival_metabolicModel_behave_clean_Denis.py — Example script from the reference paper
phase1-pablo/                              — Pablo's work (Phase 1)
  docs/DESIGN.md                           — 3-agent pipeline design (Researcher, Reasoner, Builder)
phase2-juan/                               — Juan's work (Phase 2 / the TFG)
  acuerdo-tfg.md                           — TFG objectives extracted from the agreement
  docs/DESIGN.md                           — Virtual lab design (agents, environment, API, stack)
```

## TFG Objectives (Agentic AI paradigm)

1. **Simulation Platform Agent** — configurable environment (goals, resources, constraints)
2. **Observer Agent** — monitors agents, records events, episodes and decision trajectories
3. **Analytical Agent** — processes Observer data, identifies behavior-objective patterns
4. **Reporter Agent** — generates structured reports, conclusions and improvement proposals

## Running the Reference Script

```bash
python docs/survival_metabolicModel_behave_clean_Denis.py
```

Requires: Python 3 with `tkinter` (built-in), `matplotlib`, `numpy`.

### Known bug in reference script

Line 341: uses global `threshold_hungry` instead of `organism.threshold_hungry`.
