---
id: P2-005
title: Create Memory Agent orchestrator and wire into Router stage transitions
status: todo
kind: strike
phase: 2
heat: agent
priority: 4
blocked_by: [P2-002, P2-003, P2-004]
created: 2026-04-14
updated: 2026-04-14
---

# P2-005: Create Memory Agent orchestrator and wire into Router stage transitions

## Objective
Build the `MemoryAgent` class that ties extraction, KG population, embedding, and conflict resolution into a single `run()` method, and integrate it into the Router's stage transition logic as a post-hook.

## Requirements
- `MemoryAgent` class in `phase1-pablo/src/decisionlab/agents/memory_agent.py`
  - Follows existing agent file organization (lives alongside researcher.py, builder.py, etc.)
  - NOT an agentic-loop agent — no `runtime/loop.py` usage. It's a deterministic pipeline.

- Constructor: `__init__(client: AsyncAnthropic, kg: KnowledgeGraph | None, vector_store: VectorStore | None, embedding_service: EmbeddingService | None, db_session_factory)`
  - All knowledge infrastructure params are optional (None = skip that subsystem)

- Main method: `async run(stage: str, stage_output: str, run_id: str, emit: Callable | None = None) -> MemoryAgentResult`
  - Flow:
    1. Emit status: `agent_status: memory_agent working` (if emit callback provided)
    2. **Extract:** call `extract(stage, stage_output, run_id, self.client)` → `ExtractionResult`
    3. **Parallel write:** `asyncio.gather(populate_kg(...), index_stage_output(...))`
       - Skip KG population if `self.kg is None`
       - Skip indexing if `self.vector_store is None` or `self.embedding_service is None`
    4. **Resolve:** call `resolve_and_store(extraction, ...)` → `ResolutionResult`
       - Skip if vector_store or db_session unavailable
    5. Emit status: `agent_status: memory_agent done`
    6. Return `MemoryAgentResult`

- `MemoryAgentResult` dataclass:
  ```python
  @dataclass
  class MemoryAgentResult:
      nodes_created: int
      nodes_merged: int
      relations_created: int
      facts_stored: int
      duplicates_skipped: int
      conflicts_resolved: int
      duration_ms: int
  ```

- **Router integration** in `phase1-pablo/src/decisionlab/router.py`:
  - Add `memory_agent: MemoryAgent | None` attribute to Router
  - Initialize in Router constructor: create MemoryAgent if knowledge infra is available (check `shared.knowledge_graph`, `shared.vector_store`, etc.), otherwise set to None
  - After each stage handler completes (RESEARCH, FORMALIZE, REASON, BUILD) and before transitioning to the review stage: call `self.memory_agent.run(stage, output, run_id, emit)` if memory_agent is not None
  - The Memory Agent runs between the stage and its review — so extracted knowledge is available before the user sees the review
  - Log MemoryAgentResult summary at INFO level
  - If MemoryAgent.run() raises an exception: catch, log at ERROR, continue pipeline (never block pipeline on memory failure)

- **WebSocket integration** in `server.py` or via the existing emit pattern:
  - The `emit` callback passed to MemoryAgent sends `agent_status` messages to the frontend
  - The frontend already handles `agent_status` messages — no frontend changes needed in this phase

- **Stage output collection:**
  - Each stage handler already produces its output (research report, formulation text, reasoner JSON, builder code)
  - The Router needs to capture this output text and pass it to MemoryAgent
  - For Researcher: the `report.md` content from S3
  - For Formalizer: concatenation of all `formulations/{slug}.md` files
  - For Reasoner: concatenation of all `reasoner/{fid}.json` files
  - For Builder: concatenation of all `builder/{fid}_model.py` files + test results

## Acceptance Criteria
- [ ] AC1: After a full pipeline run (RESEARCH through BUILD), the MemoryAgent has been called 4 times (once per non-review stage)
- [ ] AC2: MemoryAgentResult for each call shows non-zero nodes_created and facts_stored
- [ ] AC3: WebSocket clients receive `agent_status: memory_agent working` and `agent_status: memory_agent done` messages between each stage and its review
- [ ] AC4: If Neo4j is down, MemoryAgent still runs extraction and indexing (partial execution), and logs a warning for KG skip
- [ ] AC5: If MemoryAgent.run() throws an unexpected exception, the pipeline continues to the review stage without interruption
- [ ] AC6: Pipeline execution time increases by <5 seconds per stage (Memory Agent overhead)
- [ ] AC7: A complete pipeline run populates Neo4j with a connected graph: Paradigm nodes linked to Variables, Papers, Postulates, with provenance chains through Formulations to Parameters

## Files Likely Affected
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — new file, MemoryAgent class
- `phase1-pablo/src/decisionlab/router.py` — add memory_agent attribute, call after stage handlers
- `phase1-pablo/src/decisionlab/knowledge/models.py` — add MemoryAgentResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-2-memory-agent.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `agent`
Depends on all other Phase 2 issues: P2-001 (extraction), P2-002 (KG population), P2-003 (indexing), P2-004 (conflict resolution).
This is the capstone issue that wires everything together.
