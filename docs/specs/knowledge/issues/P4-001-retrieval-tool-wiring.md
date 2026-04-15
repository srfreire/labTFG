---
id: P4-001
title: Add retrieve_knowledge tool to all pipeline agents
status: done
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
- [x] AC1: Each agent's tool list includes `retrieve_knowledge` when knowledge infrastructure is available
- [x] AC2: Each agent's tool list does NOT include `retrieve_knowledge` when infrastructure is unavailable
- [x] AC3: The Researcher can call `retrieve_knowledge` during its agentic loop and receives formatted results
- [x] AC4: The BuilderSubAgent can call `retrieve_knowledge` to find code patterns and receives formatted results with code snippets
- [x] AC5: Tool dispatch works through the existing `runtime/dispatcher.py` — retrieve_knowledge calls are dispatched like any other tool

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

## Completion Summary

**Commit:** `1bc9eaa` — `feat[knowledge]: wire retrieve_knowledge tool into all pipeline agents (P4-001)`

### What was built
- Each pipeline agent (Researcher, DeepResearcher, FormalizerSubAgent, ReasonerSubAgent, BuilderSubAgent) conditionally receives the `retrieve_knowledge` tool when knowledge infrastructure is available
- Router creates per-stage tool handlers via `_knowledge_tool_kwargs()` helper using `create_retrieve_knowledge()` factory from P3-005
- Each agent's system prompt is augmented with a stage-specific instruction on when to use the knowledge backbone
- Graceful degradation: when `shared.kg`, `shared.vectors`, and `shared.embeddings` are all None, no tool is added and agents run as before
- Orchestrators (Formalizer, Reasoner, Builder) accept and forward knowledge deps to their sub-agents
- All 16 agent instantiation sites in Router updated

### Files created/modified
- `phase1-pablo/src/decisionlab/router.py` — added `_knowledge_tool_kwargs()` helper, wired into all agent instantiation sites
- `phase1-pablo/src/decisionlab/agents/researcher.py` — optional knowledge tool in constructor + system prompt augmentation
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — optional knowledge tool in constructor + system prompt augmentation
- `phase1-pablo/src/decisionlab/agents/formalizer.py` — accepts and forwards knowledge deps to sub-agents
- `phase1-pablo/src/decisionlab/agents/formalizer_sub.py` — optional knowledge tool in constructor + system prompt augmentation
- `phase1-pablo/src/decisionlab/agents/reasoner.py` — accepts and forwards knowledge deps to sub-agents
- `phase1-pablo/src/decisionlab/agents/reasoner_sub.py` — optional knowledge tool in constructor + system prompt augmentation
- `phase1-pablo/src/decisionlab/agents/builder.py` — accepts and forwards knowledge deps to sub-agents
- `phase1-pablo/src/decisionlab/agents/builder_sub.py` — optional knowledge tool in constructor + system prompt augmentation
- `phase1-pablo/tests/knowledge/test_tool_wiring.py` — 26 unit tests covering AC1-AC5, prompt augmentation, orchestrator forwarding, Router kwargs

### Decisions
- Used `**kwargs` unpacking pattern in Router for clean optional injection rather than passing individual params
- Each agent stores `_has_knowledge` flag to conditionally augment system prompt at run time (not constructor time)
- Knowledge tool schema is shared (RETRIEVE_KNOWLEDGE_SCHEMA constant); handler is per-stage (closure captures stage name and run_id)
- `memory_agent.py` received only formatting changes (ruff auto-format)
