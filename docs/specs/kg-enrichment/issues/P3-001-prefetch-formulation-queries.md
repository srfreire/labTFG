---
id: P3-001
title: Add formulation namespace queries to analyst and reporter prefetch
status: done
kind: strike
phase: 3
heat: queries
blocked_by: []
---

# P3-001: Add formulation namespace queries to analyst and reporter prefetch

## What

Add `formulation` namespace queries to `_PREFETCH_QUERIES` in `orchestrator.py`:

- **analyst**: `("Formulations", "mathematical formulations and equations for {paradigm}", "formulation", 3)`
- **reporter**: `("Formulations", "mathematical formulations for {paradigm}", "formulation", 3)`

## Why

Analyst needs formulations to compare theoretical predictions vs observed behavior.
Reporter needs them to include real equations in LaTeX reports.

## Acceptance criteria

- `_PREFETCH_QUERIES["analyst"]` has 3 entries (paradigm, simulation, formulation)
- `_PREFETCH_QUERIES["reporter"]` has 2 entries (meta, formulation)
- No changes to `prefetch_knowledge` logic — only the config dict
