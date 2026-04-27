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

## Out of scope (Phases 1–2)

- Changing the Analyst output JSON schema
- Adding pre-fetch to Tracker or Architect (future work — Architect added in Phase 2)
- Mandatory `retrieve_context` calls enforced in code (agents keep optional ad-hoc usage)

---

# Phase 3: Prompt-level KG enrichment for Analyst & Reporter

## Overview

With the pre-fetch infrastructure (Phases 1–2) in place, this phase focuses on
making Analyst and Reporter *actually use* the injected knowledge effectively.
Two changes:

1. **Expand prefetch queries** — add `formulation` namespace for both agents.
2. **Improve system prompts** — explicit instructions on what to do with each
   knowledge section (postulate cross-checking, equation inclusion, citation
   formatting).

No new tools, no output schema changes, no Python logic changes beyond the
query config dict and prompt strings.

## 1. New prefetch queries

Current → proposed `_PREFETCH_QUERIES` in `orchestrator.py`:

```python
"analyst": [
    ("Postulates", "postulates for {paradigm}", "paradigm", 5),
    ("Historical simulations", "previous simulation results for {paradigm}", "simulation", 5),
    ("Formulations", "mathematical formulations and equations for {paradigm}", "formulation", 3),  # NEW
],
"reporter": [
    ("References", "papers and authors for {paradigm}", "meta", 10),
    ("Formulations", "mathematical formulations for {paradigm}", "formulation", 3),  # NEW
],
```

### Rationale

| Namespace     | Analyst | Reporter | Reason |
|---------------|---------|----------|--------|
| `paradigm`    | ✅ (existing) | ❌ | Reporter inherits postulate refs via analyst_output |
| `simulation`  | ✅ (existing) | ❌ | Reporter inherits historical context via analyst_output |
| `formulation` | ✅ **NEW** | ✅ **NEW** | Analyst: compare theoretical predictions vs observed behavior. Reporter: include real equations in LaTeX |
| `meta`        | ❌ | ✅ (existing) | Only Reporter needs papers/DOIs for references |

## 2. Analyst system prompt additions

Append after the existing "## Rules" section in `ANALYST_SYSTEM_PROMPT`:

```
## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it as
follows:

### Postulates
Cross-check each observed pattern against the listed postulates. For each
pattern in your output, state which postulate it confirms, refutes, or is
unrelated to. Use the postulate identifier (e.g., "P1", "Postulado 2") in the
evidence field. Example: "Confirma P2 (regulación homeostática): el agente
redujo su tasa de alimentación al alcanzar energía estable."

### Formulations
Compare the mathematical predictions (utility functions, discount rates,
update rules) against empirical behavior. If the model predicts
U(r) = √r but agents show linear reward sensitivity, flag the deviation
with specific values. Reference the equation name or number when available.

### Historical simulations
Compare key metrics (survival rate, resource efficiency, strategy
distribution) with previous runs. Note if the current result is consistent
with or diverges from historical trends.

If knowledge context is empty or absent, proceed normally — do not mention its
absence.
```

## 3. Reporter system prompt additions

Append after the existing "## LaTeX rules" section in `REPORTER_SYSTEM_PROMPT`:

```
## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it as
follows:

### References (meta)
Use the returned Paper nodes to build real citations in the report body.
Format: \textit{Title} (Author, Year). If a DOI is available, include it in
the References section. Do NOT fabricate citations — use only what was returned.
If zero results were returned, fall back to generic references from
read_research files.

### Formulations
Include the relevant equations in the "Modelo de Decisión" section using LaTeX
math environments (\begin{equation} or \begin{align}). Reference them by number
(\ref{eq:...}) when discussing model behavior in other sections. This gives the
report mathematical grounding beyond what read_research provides, since these
equations come from the Knowledge Graph's validated formulation nodes.

If knowledge context is empty or absent, proceed with read_research as the sole
source — do not mention knowledge context absence in the report.
```

## 4. Sim-recall prompt suffix adjustments

Update `_PROMPT_SECTIONS` in `recall/agent_tools.py` to reflect that pre-fetch
already provides baseline context:

**analyst:**
```
## Postulate cross-check

A "## Knowledge context" section with postulates, formulations, and historical
data is pre-injected in your input. Use it as your primary reference for
cross-checking. If you need deeper or more specific knowledge (e.g., a
particular postulate detail, a specific past experiment), call
`retrieve_context` with a targeted query.
```

**reporter:**
```
## References grounding

A "## Knowledge context" section with paper references and formulations is
pre-injected in your input. Use it for citations and equations. If you need
additional references or formulations not covered by the pre-fetch (e.g., a
related paradigm), call `retrieve_context` with a targeted query.
```

## Files to modify

| File | Change |
|------|--------|
| `phase2-juan/simlab/orchestrator.py` | Add 2 entries to `_PREFETCH_QUERIES` dict (analyst + reporter formulation queries) |
| `phase2-juan/simlab/analyst.py` | Append ~20 lines to `ANALYST_SYSTEM_PROMPT` (knowledge context usage section) |
| `phase2-juan/simlab/reporter.py` | Append ~20 lines to `REPORTER_SYSTEM_PROMPT` (knowledge context usage section) |
| `phase2-juan/simlab/recall/agent_tools.py` | Update `_PROMPT_SECTIONS["analyst"]` and `_PROMPT_SECTIONS["reporter"]` (~10 lines each) |
| `tests/test_kg_prefetch.py` | Update query count assertions for analyst (2→3) and reporter (1→2) |

## Testing

| Test | Change |
|------|--------|
| `test_prefetch_analyst_parallel` | Assert 3 queries (was 2): paradigm + simulation + formulation |
| `test_prefetch_reporter` | Assert 2 queries (was 1): meta + formulation |
| `test_prefetch_partial_failure` | Adapt for 3-query analyst (2 succeed, 1 fails) |
| `test_analyst_knowledge_context_injected` | Verify formulations subsection present |
| `test_reporter_knowledge_context_injected` | Verify formulations subsection present |

No new test files — all changes fit existing test structure.

## Out of scope (Phase 3)

- New tools for Analyst or Reporter
- Changes to Analyst JSON output schema (no new `citations` field, etc.)
- Mandatory LaTeX `\bibliography{}` — Reporter uses inline `\textit` citations
- Changes to prefetch_knowledge Python logic (only its config dict changes)
- Architect prompt changes (covered in Phase 4)

---

# Phase 4: Prompt-level KG enrichment for Architect

## Overview

Same pattern as Phase 3 but for the Architect agent. Add `formulation` query
and system prompt instructions so the Architect uses KG knowledge to design
scientifically grounded environments.

## 1. New prefetch query

Add formulation to `_PREFETCH_QUERIES["architect"]`:

```python
"architect": [
    ("Paradigm facts", "postulates and key properties for {paradigm}", "paradigm", 5),
    ("Previous environments", "environment specifications for {paradigm}", "simulation", 5),
    ("Formulations", "mathematical formulations for {paradigm}", "formulation", 3),  # NEW
],
```

## 2. Architect system prompt additions

Append after the examples in `ARCHITECT_SYSTEM_PROMPT`:

```
## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it
to generate a more scientifically grounded environment:

### Paradigm facts
Use postulates and key properties to choose appropriate resources, actions, and
grid dimensions. E.g., if the paradigm postulates homeostatic regulation with
multiple drives, include multiple resource types with varying palatability.

### Previous environments
Reuse grid dimensions, resource types, and action sets that worked in previous
simulations of the same paradigm. Adjust counts or properties as needed for the
current request, but maintain consistency with proven configurations.

### Formulations
Use the mathematical model to dimension rewards and resource properties. E.g.,
if the model uses logarithmic utility, provide a wide reward range; if it uses
binary signals, keep rewards at 0/1.

If knowledge context is empty or absent, generate the spec from scratch based
solely on the user description.
```

## 3. Sim-recall suffix update

Replace `_PROMPT_SECTIONS["architect"]`:

```
## Knowledge Backbone access

A "## Knowledge context" section with paradigm facts, previous environment specs,
and formulations is pre-injected in your input. Use it as your primary reference
for designing scientifically grounded environments. If you need additional detail
(e.g., a specific postulate or a related paradigm), call `retrieve_context` with
a targeted query.
```

## Files to modify

| File | Change |
|------|--------|
| `phase2-juan/simlab/orchestrator.py` | 1 line in `_PREFETCH_QUERIES["architect"]` |
| `phase2-juan/simlab/architect.py` | ~15 lines appended to system prompt |
| `phase2-juan/simlab/recall/agent_tools.py` | ~5 lines in `_PROMPT_SECTIONS["architect"]` |
| `phase2-juan/tests/test_kg_prefetch.py` | Update `test_prefetch_architect` (2→3 queries) |

## Testing

| Test | Change |
|------|--------|
| `test_prefetch_architect` | Assert 3 queries (was 2), verify "Formulations" subsection |

## Out of scope (Phase 4)

- New tools for Architect
- Changes to validate_spec logic
- Changes to prefetch_knowledge Python logic
