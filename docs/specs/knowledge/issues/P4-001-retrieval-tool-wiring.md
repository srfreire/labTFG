---
id: P4-001
title: Add retrieve_knowledge tool to all pipeline agents
status: in-progress
kind: strike
phase: 4
heat: agent-tools
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-15
---

# P4-001: Add retrieve_knowledge tool to all pipeline agents

## Objective
Wire the `retrieve_knowledge` tool from P3-005 into the tool lists of Researcher, DeepResearcher, FormalizerSubAgent, ReasonerSubAgent, and BuilderSubAgent so each agent can query the knowledge backbone during its agentic loop.

## Requirements
- For each agent, call `create_retrieve_knowledge(...)` with stage-specific parameters (stage name, run_id) and add the returned tool definition + handler to the agent's tool list
- Tool is created in the Router or orchestrator before launching each agent, alongside the existing `create_read_file`, `create_write_file` calls
- If `create_retrieve_knowledge` returns None (no knowledge infra), the tool is simply not added — agent runs as before

- **Researcher** (`agents/researcher.py`):
  - Add tool alongside existing `web_search`, `launch_deep_research`, `read_report`
  - Stage: "researcher"

- **DeepResearcher** (`agents/deep_researcher.py`):
  - Add tool alongside existing `search_papers`, `web_search`
  - Stage: "deep_researcher"

- **FormalizerSubAgent** (`agents/formalizer_sub.py`):
  - Add tool alongside existing `read_file`, `write_file`
  - Stage: "formalizer"

- **ReasonerSubAgent** (`agents/reasoner_sub.py`):
  - Add tool alongside existing `read_file`, `write_file`
  - Stage: "reasoner"

- **BuilderSubAgent** (`agents/builder_sub.py`):
  - Add tool alongside existing `read_file`, `write_file`, `run_tests`
  - Stage: "builder"

- Tool dispatch: add `"retrieve_knowledge"` case to each agent's tool dispatch map in their orchestrator or in the shared `runtime/dispatcher.py`

## Acceptance Criteria
- [ ] AC1: Each agent's tool list includes `retrieve_knowledge` when knowledge infrastructure is available
- [ ] AC2: Each agent's tool list does NOT include `retrieve_knowledge` when infrastructure is unavailable
- [ ] AC3: The Researcher can call `retrieve_knowledge` during its agentic loop and receives formatted results
- [ ] AC4: The BuilderSubAgent can call `retrieve_knowledge` to find code patterns and receives formatted results with code snippets
- [ ] AC5: Tool dispatch works through the existing `runtime/dispatcher.py` — retrieve_knowledge calls are dispatched like any other tool

## Files Likely Affected
- `phase1-pablo/src/decisionlab/router.py` — tool creation before each stage
- `phase1-pablo/src/decisionlab/agents/researcher.py` — tool list update
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — tool list update
- `phase1-pablo/src/decisionlab/agents/formalizer.py` — pass tool to sub-agents
- `phase1-pablo/src/decisionlab/agents/reasoner.py` — pass tool to sub-agents
- `phase1-pablo/src/decisionlab/agents/builder.py` — pass tool to sub-agents

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `agent-tools`
