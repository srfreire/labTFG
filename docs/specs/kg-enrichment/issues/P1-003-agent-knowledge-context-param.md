---
id: P1-003
title: Add knowledge_context parameter to Analyst and Reporter run()
status: done
kind: strike
phase: 1
heat: agents
priority: 1
blocked_by: []
created: 2026-04-26
updated: 2026-04-26
---

# P1-003: Add knowledge_context parameter to Analyst and Reporter run()

## Objective

Add `knowledge_context: str = ""` parameter to the `run()` method of both
Analyst and Reporter, injecting it into the user message before the tracker
observation log.

## Requirements

### R1: Analyst.run() — new parameter

Add `knowledge_context: str = ""` to the `run()` signature (after existing
params, before `**kwargs` if any).

Modify user message construction:
```python
# Before:
user_message = f"{prompt}\n\n## Tracker observation log\n\n{tracker_output}"

# After:
parts = [prompt]
if knowledge_context:
    parts.append(knowledge_context)
parts.append(f"## Tracker observation log\n\n{tracker_output}")
user_message = "\n\n".join(parts)
```

### R2: Reporter.run() — new parameter

Same pattern. Add `knowledge_context: str = ""` to `run()` signature.

Modify user message construction to inject `knowledge_context` between the
prompt and the tracker observation log section. The existing optional sections
(predictions, charts, interaction) remain after analyst findings.

### R3: Backwards compatibility

When `knowledge_context` is `""` (default), the user message is functionally
identical to today. No existing callers need to change.

## Acceptance Criteria

- [ ] `Analyst.run(prompt, tracker, events, knowledge_context="## Knowledge context\n...")` includes the context in the user message before tracker output
- [ ] `Reporter.run(prompt, tracker, analyst, ..., knowledge_context="## Knowledge context\n...")` includes the context in the user message before tracker output
- [ ] `Analyst.run(prompt, tracker, events)` (no knowledge_context) produces the same user message as today
- [ ] `Reporter.run(prompt, tracker, analyst, ...)` (no knowledge_context) produces the same user message as today

## Files Likely Affected

- `phase2-juan/simlab/analyst.py` — modify `run()` signature (~line 231) and user message construction
- `phase2-juan/simlab/reporter.py` — modify `run()` signature (~line 319) and user message construction

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `agents`

## Completion Summary

Added `knowledge_context: str = ""` keyword parameter to both `Analyst.run()` and `Reporter.run()`.

When non-empty, the knowledge context is injected between the user prompt and the `## Tracker observation log` section using a `parts` list joined by `"\n\n"`. When empty (default), the resulting user message is functionally identical to the previous behavior.

Files changed:
- `phase2-juan/simlab/analyst.py` — new param + parts-based message construction
- `phase2-juan/simlab/reporter.py` — new param + parts-based message construction
