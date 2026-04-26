---
id: P1-002
title: Wire prefetch_knowledge into orchestrator analyze_results and generate_report
status: todo
kind: strike
phase: 1
heat: prefetch
priority: 2
blocked_by: [P1-001, P1-003]
created: 2026-04-26
updated: 2026-04-26
---

# P1-002: Wire prefetch_knowledge into orchestrator analyze_results and generate_report

## Objective

Call `prefetch_knowledge` inside the `analyze_results` and `generate_report`
closures in `_build_tools`, passing the result as `knowledge_context` to
the Analyst and Reporter `run()` calls.

## Requirements

### R1: Resolve paradigm name from state

Extract the paradigm name from the orchestrator's discovered models.
The paradigm is available in `self._discovered_models` — use the paradigm
field from the first model in the simulation's `model_ids`, or fall back
to the first discovered model's paradigm. Store in `state["paradigm"]`
during `run_simulation` so it is available later.

### R2: Wire analyze_results

Inside the `analyze_results` closure in `_build_tools`:
1. Before creating the Analyst, call `await prefetch_knowledge(paradigm, "analyst", on_warning)`
2. Pass result as `knowledge_context=knowledge_ctx` to `analyst.run(...)`
3. The `on_warning` callback should use `self.on_agent_tool_call` or a
   similar mechanism to surface warnings to the frontend.

### R3: Wire generate_report

Inside the `generate_report` closure in `_build_tools`:
1. Before creating the Reporter, call `await prefetch_knowledge(paradigm, "reporter", on_warning)`
2. Pass result as `knowledge_context=knowledge_ctx` to `reporter.run(...)`

### R4: Warning callback

Create a small `on_warning` closure that emits the warning via the
orchestrator's existing callback mechanism (same pattern as
`_make_tool_callback`). If no callback is set, warnings are log-only.

## Acceptance Criteria

- [ ] `analyze_results` calls `prefetch_knowledge` before invoking Analyst
- [ ] `generate_report` calls `prefetch_knowledge` before invoking Reporter
- [ ] Paradigm name is resolved from discovered models / state
- [ ] When `ENABLE_KNOWLEDGE_READ=False`, no prefetch call is attempted (function returns "" immediately)
- [ ] Warnings are surfaced via the orchestrator's callback mechanism

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — modify `analyze_results` and `generate_report` closures in `_build_tools` (~lines 810-870), add paradigm resolution in `run_simulation`

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `prefetch`
