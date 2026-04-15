# Phase 4: Pipeline Integration

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Wire the Memory Agent (Phase 2) and the retrieval tool (Phase 3) into the existing pipeline agents and Router. Each agent gains a `retrieve_knowledge` tool. The Router calls the Memory Agent after each stage. Graceful degradation when knowledge infrastructure is unavailable.

## Requirements

### R1: Add retrieve_knowledge Tool to Pipeline Agents
- Researcher, DeepResearcher, Formalizer(Sub), Reasoner(Sub), and Builder(Sub) each gain the `retrieve_knowledge` tool in their tool lists.
- Tool is created via `create_retrieve_knowledge(...)` factory from P3-005, with stage-specific parameters (stage name, run_id).
- Each agent's system prompt is extended with a short instruction on when to use the tool (e.g., "Before generating formulations, query the knowledge backbone for existing formulations of similar paradigms").
- Tool is optional — if `create_retrieve_knowledge` returns None (no infrastructure), the agent's tool list is unchanged.

### R2: Wire Memory Agent into Router Stage Transitions
- After each stage handler (RESEARCH, FORMALIZE, REASON, BUILD) completes and before transitioning to the review stage, the Router calls `memory_agent.run(stage, output, run_id, emit)`.
- Stage output collection: Router captures the text output from each stage to pass to the Memory Agent:
  - RESEARCH: read `report.md` + all `deep/{slug}.md` from S3
  - FORMALIZE: read all `formulations/{slug}.md` from S3
  - REASON: read all `reasoner/{fid}.json` from S3
  - BUILD: read all `builder/{fid}_model.py` from S3 + test results
- Memory Agent result is logged at INFO level but not shown to the user in the review stage.

### R3: System Prompt Augmentation for Each Agent
- Each agent's system prompt gains a brief section explaining the knowledge backbone:
  - Researcher: "Use retrieve_knowledge to check if this problem domain has been researched in past pipeline runs. Avoid redundant web searches for paradigms already in the knowledge base."
  - DeepResearcher: "Use retrieve_knowledge to find existing deep research on this paradigm from past runs. Build on existing knowledge rather than starting from scratch."
  - Formalizer: "Use retrieve_knowledge to find formulation patterns that have worked for similar paradigms. Reference existing equations and parameter sources."
  - Reasoner: "Use retrieve_knowledge to find validated parameter ranges and env_mapping patterns from past runs."
  - Builder: "Use retrieve_knowledge to find working code patterns and test strategies from past model builds."

### R4: Graceful Degradation
- If Neo4j, Qdrant, or Voyage AI are unavailable at pipeline start:
  - Router logs a warning: "Knowledge infrastructure partially/fully unavailable. Running in degraded mode."
  - Memory Agent is set to None — no knowledge extraction after stages
  - retrieve_knowledge tool is excluded from agent tool lists
  - Pipeline runs exactly as before (pre-knowledge-backbone behavior)
- If infrastructure becomes unavailable mid-run (e.g., Neo4j crashes):
  - Memory Agent catches the exception, logs error, returns empty result
  - retrieve_knowledge tool catches the exception, returns "Knowledge backbone temporarily unavailable"
  - Pipeline continues without interruption

### R5: WebSocket Status Updates
- Memory Agent emits `agent_status: memory_agent working/done` via the existing emit callback
- The frontend's agent status panel shows the Memory Agent alongside Researcher, Formalizer, etc.
- Agent tool calls from Memory Agent (if any) are emitted via `on_agent_tool_call` pattern

## Acceptance Criteria
- [x] AC1: A full pipeline run with knowledge infrastructure available shows retrieve_knowledge in each agent's tool list
- [ ] AC2: The Formalizer actually calls retrieve_knowledge when formulating a paradigm that was researched in a prior run (verified via tool call logs)
- [x] AC3: The Memory Agent runs after RESEARCH, FORMALIZE, REASON, and BUILD stages — verified via MemoryAgentResult logs (4 calls total)
- [ ] AC4: After a pipeline run, Neo4j contains a connected knowledge graph with Paradigm→Variable→BrainRegion→Paper chains
- [ ] AC5: A second pipeline run on a related topic retrieves knowledge from the first run's memories via retrieve_knowledge
- [ ] AC6: Pipeline runs successfully when Docker services for Neo4j/Qdrant are stopped — no errors, degraded mode warning logged
- [x] AC7: WebSocket clients see memory_agent status updates in the agent panel

## Technical Notes
- The retrieve_knowledge tool integration follows the exact same pattern as `create_read_file` and `create_write_file` in `tools/files.py` — factory function, closure handler, registration in the agent's tool list via dispatcher
- System prompt additions should be minimal (2-3 sentences per agent) to avoid bloating context
- The Router already has an `emit` callback pattern — pass the same callback to Memory Agent

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool per agent vs shared tool | Per-agent instances with stage-specific context | CRAG evaluator needs to know the downstream task context, which differs per stage |
| Prompt augmentation style | Brief instruction, not detailed examples | Agents are already good at using tools; a 2-sentence instruction is sufficient |
| Memory Agent visibility | Logged but not shown in review | Users review stage output, not memory extraction. Showing it would add noise. |
