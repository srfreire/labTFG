---
id: P1-003
title: Wire query_experiments tool into orchestrator
status: todo
kind: strike
phase: 1
heat: wiring
blocked_by: [P1-002]
---

# P1-003: Wire query_experiments tool into orchestrator

## Objective

Add the `query_experiments` tool to the Orchestrator so users can query
experiments via natural language in the chat.

## Requirements

### Tool schema

Add `QUERY_EXPERIMENTS_TOOL` constant to `orchestrator.py`:
```python
{
  "name": "query_experiments",
  "description": "Query the experiment database using natural language. Answers questions about past experiments, models, results, patterns, and cross-experiment comparisons.",
  "input_schema": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "Natural language question about experiments"
      }
    },
    "required": ["question"]
  }
}
```

### ALL_TOOLS

Add `QUERY_EXPERIMENTS_TOOL` to the `ALL_TOOLS` list.

### _build_tools closure

Add a `query_experiments` closure that calls `nlsql.query_experiments(params["question"])`.

### System prompt

Add to the numbered tools list:
```
8. **query_experiments** — queries the experiment database with natural language.
   Use when the user asks about past experiments, comparisons between runs,
   historical results, or anything that requires searching experiment data.
```

## Acceptance Criteria

- [ ] `QUERY_EXPERIMENTS_TOOL` in `ALL_TOOLS`
- [ ] Closure in `_build_tools` calls `nlsql.query_experiments`
- [ ] System prompt mentions `query_experiments` with usage guidance
- [ ] Tool is available in the Orchestrator's tool list

## Files Likely Affected

- `phase2-juan/simlab/orchestrator.py` — tool schema, ALL_TOOLS, closure, system prompt
