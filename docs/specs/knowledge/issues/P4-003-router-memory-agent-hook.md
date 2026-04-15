---
id: P4-003
title: Wire Memory Agent into Router stage transitions as post-hook
status: done
kind: strike
phase: 4
heat: router
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-15
---

# P4-003: Wire Memory Agent into Router stage transitions as post-hook

## Objective
Integrate the Memory Agent into the Router's stage transition logic so it automatically runs after each pipeline stage (RESEARCH, FORMALIZE, REASON, BUILD), extracting knowledge before the review stage begins.

## Requirements
- Add `memory_agent: MemoryAgent | None` attribute to `Router.__init__`
- Initialize: if `shared.knowledge_graph` and `shared.vector_store` and `shared.embedding_service` are available, create `MemoryAgent(client, kg, vector_store, embedding_service, db_session_factory)`. Otherwise set to None.

- After each stage handler completes, before transitioning to the corresponding REVIEW stage:
  ```python
  if self.memory_agent:
      stage_output = await self._collect_stage_output(stage)
      result = await self.memory_agent.run(stage, stage_output, self.run_id, self.emit)
      logger.info(f"Memory Agent: {result}")
  ```

- **Stage output collection** — `async _collect_stage_output(stage: str) -> str`:
  - RESEARCH: read `report.md` + concatenate all `deep/{slug}.md` from S3
  - FORMALIZE: concatenate all `formulations/{slug}.md` from S3
  - REASON: concatenate all `reasoner/{fid}.json` from S3
  - BUILD: concatenate all `builder/{fid}_model.py` from S3 + append test result summaries
  - Use existing `shared.storage.get_text()` for S3 reads
  - The Router already knows the file keys from the stage handlers — collect them from `PipelineState`

- **Error handling**: if `memory_agent.run()` raises any exception, catch it, log at ERROR level, and continue to the review stage. The Memory Agent must never block the pipeline.

- **WebSocket integration**: pass `self.emit` to `memory_agent.run()` so it can send `agent_status` updates. The `emit` function is already available in Router for WebSocket mode.

## Acceptance Criteria
- [x] AC1: A full pipeline run with knowledge infra calls Memory Agent 4 times (after RESEARCH, FORMALIZE, REASON, BUILD)
- [x] AC2: Memory Agent results are logged at INFO level with nodes_created, facts_stored, conflicts_resolved counts
- [x] AC3: If Memory Agent throws, the pipeline continues to REVIEW_RESEARCH (etc.) without interruption — error logged at ERROR level
- [x] AC4: If knowledge infra is unavailable, Router.memory_agent is None and no Memory Agent calls are made
- [x] AC5: Stage output collection reads the correct S3 files for each stage — verified by checking Memory Agent receives non-empty text
- [x] AC6: WebSocket clients receive `agent_status: memory_agent working/done` between stage completion and review

## Files Likely Affected
- `phase1-pablo/src/decisionlab/router.py` — memory_agent attribute, post-hook calls, _collect_stage_output method

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `router`
Can run in parallel with P4-001/P4-002 (agent-tools heat) since it modifies Router while those modify individual agents.

## Completion Summary

**Commit:** `d5b6606` — `feat[knowledge]: MemoryAgent orchestrator with Router integration (P2-005)`

### What was built
- `memory_agent` attribute on `Router.__init__`, auto-initialized via `_init_memory_agent()` from shared infra
- `_MEMORY_STAGES` dict mapping RESEARCH/FORMALIZE/REASON/BUILD to stage names
- Post-hook in `Router.run()` loop calling `_run_memory_agent()` after each successful work stage
- `_collect_stage_output()` reading correct S3 artifacts per stage (report.md, formulations, reasoner specs, builder models)
- Error handling: all exceptions caught and logged at ERROR level, pipeline continues unblocked
- WebSocket integration: `emit` passed to `memory_agent.run()`, emits `agent_status: working/done`
- Graceful degradation: `memory_agent` is `None` when shared.db is unavailable

### Files created/modified
- `phase1-pablo/src/decisionlab/router.py` — `_init_memory_agent`, `_run_memory_agent`, `_collect_stage_output`, post-hook in `run()` loop
- `phase1-pablo/tests/knowledge/test_router_memory.py` — 8 integration tests covering all ACs

### Decisions
- Feature was implemented as part of P2-005 (MemoryAgent orchestrator). All P4-003 requirements were already satisfied by that commit. Verified via test suite (8/8 passing).
