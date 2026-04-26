---
id: P1-001
title: Implement prefetch_knowledge function with warning notifications
status: todo
kind: strike
phase: 1
heat: prefetch
priority: 1
blocked_by: []
created: 2026-04-26
updated: 2026-04-26
---

# P1-001: Implement prefetch_knowledge function with warning notifications

## Objective

Create the `prefetch_knowledge` async function in the orchestrator that
pre-fetches relevant KG context for a given agent stage, with resilient
error handling and WebSocket warning notifications on failure.

## Requirements

### R1: Function signature and dispatch

```python
async def prefetch_knowledge(
    paradigm: str,
    stage: str,
    on_warning: Callable[[str, str], Awaitable[None]] | None = None,
) -> str
```

- `stage="analyst"` runs 2 queries in parallel via `asyncio.gather`:
  - `retrieve_context(query="postulates for {paradigm}", namespace="paradigm")`
  - `retrieve_context(query="previous simulation results for {paradigm}", namespace="simulation")`
- `stage="reporter"` runs 1 query:
  - `retrieve_context(query="papers and authors for {paradigm}", namespace="meta", top_k=10)`
- Returns a markdown string with `## Knowledge context` header and subsections
  per successful query. Omits subsections for empty results.
- Returns `""` if all results are empty or if the function is skipped.

### R2: Guard on ENABLE_KNOWLEDGE_READ

If `settings.ENABLE_KNOWLEDGE_READ is False`, return `""` immediately.
No queries, no logs, no warnings.

### R3: Paradigm guard

If `paradigm` is empty/None, return `""` immediately without warning.
This covers free-form simulations without a named paradigm.

### R4: Resilient error handling

- Each query is wrapped individually so one failure does not cancel the others.
- On failure: `logger.warning("Knowledge pre-fetch failed for %s: %s", stage, error)`
- On failure: call `on_warning(stage, short_error_message)` if provided.
- On partial failure: return whatever succeeded.
- On total failure: return `""`.

### R5: Markdown formatting

Analyst output format:
```markdown
## Knowledge context

### Postulates
{paradigm_result}

### Historical simulations
{simulation_result}
```

Reporter output format:
```markdown
## Knowledge context

### References
{meta_result}
```

Empty subsections (empty string from retrieve_context) are omitted entirely.

## Acceptance Criteria

- [ ] `prefetch_knowledge("prospect_theory", "analyst")` returns markdown with
      Postulates and Historical subsections when KG has data
- [ ] `prefetch_knowledge("prospect_theory", "reporter")` returns markdown with
      References subsection when KG has data
- [ ] Returns `""` when `ENABLE_KNOWLEDGE_READ=False`
- [ ] Returns `""` when `paradigm` is empty/None
- [ ] Partial failure returns successful results + emits warning
- [ ] Total failure returns `""` + emits warning
- [ ] Analyst queries run in parallel (asyncio.gather)

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — add `prefetch_knowledge` function (as module-level async or method, near `_build_tools`)

## Context

Phase spec: `docs/specs/kg-enrichment/design.md`
Heat: `prefetch`
