---
id: P4-001
title: Add formulation namespace query to architect prefetch
status: done
kind: strike
phase: 4
heat: queries
blocked_by: []
---

# P4-001: Add formulation namespace query to architect prefetch

## What

Add `("Formulations", "mathematical formulations for {paradigm}", "formulation", 3)` to `_PREFETCH_QUERIES["architect"]` in `orchestrator.py`.

## Acceptance criteria

- `_PREFETCH_QUERIES["architect"]` has 3 entries (paradigm, simulation, formulation)
