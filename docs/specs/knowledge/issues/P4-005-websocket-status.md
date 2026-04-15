---
id: P4-005
title: Add Memory Agent status to WebSocket agent panel
status: done
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
- [x] AC1: WebSocket clients receive `agent_status: memory_agent working` after each pipeline stage completes
- [x] AC2: WebSocket clients receive `agent_status: memory_agent done` before the review stage begins
- [x] AC3: Memory Agent does not appear in the agent panel when knowledge infrastructure is unavailable
- [x] AC4: The `agents` initialization message includes `memory_agent` with appropriate metadata

## Files Likely Affected
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — emit calls in run()
- `phase1-pablo/src/decisionlab/server.py` or `api.py` equivalent — include memory_agent in agent list
- `phase1-pablo/src/decisionlab/router.py` — pass emit to memory_agent.run()

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `resilience`
Depends on P4-003 (Router hook) since that's where emit is passed to Memory Agent.

## Completion Summary

**Commits:** `e5ec5ed` — backend agents init message, `865fdc6` — frontend handling, `8236687` — review fixes

### What was built
- Router emits `{"type": "agents", "agents": [...]}` at pipeline start, including `memory_agent` only when knowledge infrastructure is available (AC3, AC4)
- Frontend `ServerMessage` union extended with `agent_status`, `agents`, and `agent_tool` message types
- `useWebSocket` reducer handles `agents` (populates agent list) and `agent_status` (updates individual agent status) messages, resets on cancel/restart
- Sidebar shows Memory Agent interstitials between work stages (RESEARCH, FORMALIZE, REASON, BUILD) and their REVIEW stages — cyan dot with pulse animation when working, faded when done
- AC1/AC2 were already satisfied by P4-003 (MemoryAgent emits working/done via emit callback between stages)

### Files created/modified
- `phase1-pablo/src/decisionlab/router.py` — `_emit_agents()` method, called at start of `run()`
- `phase1-pablo/tests/knowledge/test_router_memory.py` — 2 new tests for agents init message (with/without memory_agent)
- `phase1-pablo/web/src/types.ts` — `AgentState` interface, `ServerMessage` union extensions, `MEMORY_AGENT_STAGES`, `memory_agent` color
- `phase1-pablo/web/src/hooks/useWebSocket.ts` — `agents` state, `agents`/`agent_status` handlers, cancel reset
- `phase1-pablo/web/src/components/Sidebar.tsx` — `MemoryAgentDot` component, interstitial rendering in timeline
- `phase1-pablo/web/src/App.tsx` — pass `agents` to `Sidebar`

### Decisions
- Agents init message emitted from `Router.run()` (not `server.py`) because Router has knowledge of memory_agent availability
- Memory agent shown as timeline interstitial dots (not a separate panel) to match Phase 1's existing Sidebar stage-timeline design
- Cyan (#22d3ee) chosen for memory_agent color to distinguish it from pipeline agents
