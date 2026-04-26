# KG-Enrichment: Analyst & Reporter Knowledge Graph Pre-fetch

## Overview

Enrich the Analyst and Reporter agents with knowledge from the Knowledge Graph
(KG) by pre-fetching relevant context in the Orchestrator before invoking each
agent. The pre-fetched context is injected into the agent's user message so
the agent starts with a baseline of KG knowledge without relying on tool calls.

Each agent retains `retrieve_context` as an ad-hoc tool for follow-up queries.

## Motivation

Today Analyst and Reporter receive `retrieve_context` as a tool (via
sim-recall wiring) with prompt suffixes instructing them to call it. In
practice the LLM does not always follow the instruction, producing analyses
and reports that miss postulate cross-checks, historical comparisons, and real
paper citations. A deterministic pre-fetch eliminates that unreliability.

## Architecture

```
Orchestrator._build_tools()
  │
  ├─ analyze_results closure:
  │    1. knowledge_ctx = await prefetch_knowledge(paradigm, "analyst", notify)
  │    2. Analyst.run(..., knowledge_context=knowledge_ctx)
  │
  └─ generate_report closure:
       1. knowledge_ctx = await prefetch_knowledge(paradigm, "reporter", notify)
       2. Reporter.run(..., knowledge_context=knowledge_ctx)
```

### prefetch_knowledge

```
async def prefetch_knowledge(
    paradigm: str,
    stage: str,            # "analyst" | "reporter"
    notify: Callable,      # ws event emitter
) -> str
```

**Behaviour by stage:**

| Stage    | Queries (parallel via asyncio.gather)                          |
|----------|----------------------------------------------------------------|
| analyst  | `retrieve_context(query="postulates for {paradigm}", namespace="paradigm")` |
|          | `retrieve_context(query="previous simulation results for {paradigm}", namespace="simulation")` |
| reporter | `retrieve_context(query="papers and authors for {paradigm}", namespace="meta", top_k=10)` |

**Return value:** Markdown string with sections per query result:

```markdown
## Knowledge context

### Postulates
{paradigm_result}

### Historical simulations
{simulation_result}
```

If a query returns empty, its subsection is omitted.
If all queries return empty, returns `""`.

### Paradigm name resolution

The `paradigm` string comes from the Orchestrator's `state["paradigm"]`, which
is set during the Architect stage when the environment spec is generated. It
contains the paradigm name as identified by Phase 1 (e.g., "prospect_theory",
"iowa_gambling_task"). If `state["paradigm"]` is not set (e.g., free-form
simulation without a named paradigm), `prefetch_knowledge` returns `""`
without warning — there is nothing meaningful to query.

### Guard: ENABLE_KNOWLEDGE_READ

If `settings.ENABLE_KNOWLEDGE_READ is False`, `prefetch_knowledge` returns
`""` immediately — no queries, no logs, no warnings. This is intentional
configuration, not a failure.

## User message injection

New parameter `knowledge_context: str = ""` in both `Analyst.run()` and
`Reporter.run()`. Injected before the tracker output:

**Analyst:**
```
{focus}

{knowledge_context}

## Tracker observation log

{tracker_output}
```

**Reporter:**
```
{focus}

{knowledge_context}

## Tracker observation log

{tracker_output}

## Analyst findings

{analyst_output}
```

When `knowledge_context` is `""`, the message is identical to today
(backwards-compatible).

## Prompt suffixes

The existing prompt suffixes from sim-recall `agent_tools.py` are **unchanged**.
They still instruct the agent to call `retrieve_context` for ad-hoc queries
during reasoning. The pre-fetch provides guaranteed baseline context; the tool
provides optional depth.

## Resiliencia and notifications

| Scenario                        | Behaviour                                      |
|---------------------------------|------------------------------------------------|
| Query fails (exception)         | `logger.warning(...)` + WebSocket `knowledge_warning` event. Agent runs without that section. |
| Query returns empty             | Silent — valid case (new paradigm, no data).   |
| `ENABLE_KNOWLEDGE_READ = False` | Returns `""` immediately. No log, no warning.  |
| Partial failure (1 of 2 fails)  | Warning for the failed one, include the successful one. |

WebSocket event payload:
```json
{
  "type": "knowledge_warning",
  "stage": "analyst",
  "message": "Knowledge pre-fetch failed: connection refused"
}
```

Frontend shows this as a toast/badge in the agent status panel.

## Pre-fetch distribution rationale

| Namespace     | Analyst | Reporter | Reason                                              |
|---------------|---------|----------|-----------------------------------------------------|
| `paradigm`    | ✅      | ❌       | Reporter inherits postulate refs via analyst_output  |
| `simulation`  | ✅      | ❌       | Reporter inherits historical context via analyst_output |
| `formulation` | ❌      | ❌       | Analyst has events; Reporter has `read_research` tool |
| `meta`        | ❌      | ✅       | Only Reporter needs papers/DOIs for References       |

## Files to modify

| File | Change |
|------|--------|
| `phase2-juan/simlab/orchestrator.py` | Add `prefetch_knowledge()`. Modify `analyze_results` and `generate_report` closures to call it and pass `knowledge_context`. |
| `phase2-juan/simlab/analyst.py` | Add `knowledge_context: str = ""` param to `run()`. Inject in user message. |
| `phase2-juan/simlab/reporter.py` | Add `knowledge_context: str = ""` param to `run()`. Inject in user message. |

## Testing

### Unit tests

| Test | Verifies |
|------|----------|
| `test_prefetch_analyst_parallel` | 2 queries in parallel (paradigm + simulation), returns markdown with both sections |
| `test_prefetch_reporter` | 1 query (meta), returns references section |
| `test_prefetch_partial_failure` | One query fails → warning emitted, successful result returned |
| `test_prefetch_total_failure` | All queries fail → returns `""`, warning emitted |
| `test_prefetch_disabled` | `ENABLE_KNOWLEDGE_READ=False` → returns `""`, no calls to `retrieve_context` |
| `test_analyst_knowledge_context_injected` | User message includes `## Knowledge context` before tracker output |
| `test_reporter_knowledge_context_injected` | User message includes `## Knowledge context` before tracker output |

### Integration test

| Test | Verifies |
|------|----------|
| `test_prefetch_roundtrip` | Write data to KG, then verify `prefetch_knowledge` retrieves and formats it correctly |

## Out of scope

- Changing the Analyst output JSON schema
- Adding pre-fetch to Tracker or Architect (future work)
- Mandatory `retrieve_context` calls enforced in code (agents keep optional ad-hoc usage)
