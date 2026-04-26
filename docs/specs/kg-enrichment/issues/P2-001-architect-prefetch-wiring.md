---
id: P2-001
title: Extend prefetch_knowledge for architect and wire into create_environment
status: done
kind: strike
phase: 2
heat: wiring
priority: 1
blocked_by: []
created: 2026-04-26
updated: 2026-04-26
---

# P2-001: Extend prefetch_knowledge for architect and wire into create_environment

## Objective

Add an `"architect"` stage to the prefetch query dispatch table, add
`knowledge_context` parameter to `Architect.run()`, and wire the pre-fetch
into the `create_environment` closure in the orchestrator.

## Requirements

### R1: Add architect queries to _PREFETCH_QUERIES

Add `"architect"` stage to the dispatch table:
- `("Paradigm facts", "postulates and key properties for {paradigm}", "paradigm", 5)`
- `("Previous environments", "environment specifications for {paradigm}", "simulation", 5)`

These give the Architect known paradigm properties (to design coherent
environments) and past environment configs (to avoid redundancy or build on
previous designs).

### R2: Add knowledge_context param to Architect.run()

Add `knowledge_context: str = ""` to `Architect.run()`. Inject into the
user message:

```python
# Before:
messages=[{"role": "user", "content": prompt}]

# After:
parts = [prompt]
if knowledge_context:
    parts.append(knowledge_context)
user_content = "\n\n".join(parts)
messages=[{"role": "user", "content": user_content}]
```

Backwards compatible — empty default produces identical message.

### R3: Wire into create_environment closure

The Architect is called before any simulation, so `state["paradigm"]` is
not yet set. Instead, extract the paradigm hint from the user's description
parameter. Use a simple heuristic: pass the full description as the
`paradigm` argument to `prefetch_knowledge`. The KG queries are
fuzzy-matched anyway, so "simulate prospect theory with 5 agents" will
match paradigm entries for "prospect_theory".

```python
async def create_environment(params: dict) -> str:
    knowledge_ctx = await prefetch_knowledge(
        params["description"], "architect", on_warning=_on_kg_warning,
    )
    arch = Architect(client=client)
    spec_json = await arch.run(
        params["description"],
        on_tool_call=self._make_tool_callback("Architect"),
        knowledge_context=knowledge_ctx,
        **_recall_kwargs("architect"),
    )
    ...
```

### R4: Prompt suffix unchanged

The existing architect prompt suffix from sim-recall `agent_tools.py`
remains unchanged. The pre-fetch provides baseline context; the tool
provides optional ad-hoc queries.

## Acceptance Criteria

- [ ] `_PREFETCH_QUERIES["architect"]` has 2 entries (paradigm + simulation)
- [ ] `Architect.run()` accepts `knowledge_context: str = ""`
- [ ] `Architect.run(prompt, knowledge_context="...")` injects context after prompt
- [ ] `Architect.run(prompt)` (no context) produces identical message to before
- [ ] `create_environment` calls `prefetch_knowledge` before invoking Architect
- [ ] Warning callback works on failure

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — add `"architect"` to `_PREFETCH_QUERIES`, modify `create_environment` closure
- `phase2-juan/simlab/architect.py` — add `knowledge_context` param to `run()`

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `wiring`
