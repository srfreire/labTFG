---
id: P4-005
title: Add Memory Agent status to WebSocket agent panel
status: in-progress
kind: strike
phase: 4
heat: resilience
priority: 4
blocked_by: [P4-003]
created: 2026-04-14
updated: 2026-04-15
---

# P4-005: Add Memory Agent status to WebSocket agent panel

## Objective
Make the Memory Agent visible in the frontend's agent status panel via WebSocket status messages, so users can see when knowledge extraction is happening between pipeline stages.

## Requirements
- The Memory Agent emits `agent_status` messages through the Router's `emit` callback:
  - `{"type": "agent_status", "agent": "memory_agent", "status": "working"}` — when extraction starts
  - `{"type": "agent_status", "agent": "memory_agent", "status": "done"}` — when extraction completes
  - `{"type": "agent_tool", "agent": "memory_agent", "tool": "<tool_name>"}` — for internal operations (extract, populate_kg, embed, resolve)

- The `api.py` patched tool builder includes Memory Agent in the pipeline agent list sent to the frontend
- The existing agent panel renders Memory Agent like any other agent — no frontend code changes needed if the message format matches the existing `agent_status` schema

- Memory Agent appears in the pipeline visualization between the main stage and its review:
  ```
  RESEARCH → [memory_agent] → REVIEW_RESEARCH → FORMALIZE → [memory_agent] → ...
  ```

- The `agents` message sent at connection time includes `memory_agent` in the agent list (if knowledge infra is available)

## Acceptance Criteria
- [ ] AC1: WebSocket clients receive `agent_status: memory_agent working` after each pipeline stage completes
- [ ] AC2: WebSocket clients receive `agent_status: memory_agent done` before the review stage begins
- [ ] AC3: Memory Agent does not appear in the agent panel when knowledge infrastructure is unavailable
- [ ] AC4: The `agents` initialization message includes `memory_agent` with appropriate metadata

## Files Likely Affected
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — emit calls in run()
- `phase1-pablo/src/decisionlab/server.py` or `api.py` equivalent — include memory_agent in agent list
- `phase1-pablo/src/decisionlab/router.py` — pass emit to memory_agent.run()

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `resilience`
Depends on P4-003 (Router hook) since that's where emit is passed to Memory Agent.
