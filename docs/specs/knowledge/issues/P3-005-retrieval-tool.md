---
id: P3-005
title: Create unified retrieve_knowledge tool for pipeline agents
status: todo
kind: strike
phase: 3
heat: tool
priority: 4
blocked_by: [P3-003, P3-004]
created: 2026-04-14
updated: 2026-04-14
---

# P3-005: Create unified retrieve_knowledge tool for pipeline agents

## Objective
Expose the full 3-layer retrieval + CRAG pipeline as a single tool function that any pipeline agent can call to query the knowledge backbone. Follow the existing tool factory pattern (`create_read_file`, `create_write_file`, etc.).

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py`

- **Tool factory:**
  ```python
  def create_retrieve_knowledge(
      kg: KnowledgeGraph | None,
      vector_store: VectorStore | None,
      embedding_service: EmbeddingService | None,
      search_adapter: WebSearchPort | None,
      client: AsyncAnthropic,
      run_id: str,
      stage: str,
  ) -> dict:
  ```
  - Returns a tool definition dict compatible with the Anthropic API tool schema:
    ```python
    {
        "name": "retrieve_knowledge",
        "description": "Query the knowledge backbone for relevant research, formulations, model patterns, and scientific facts from past pipeline runs and the current knowledge graph. Use this to find existing knowledge before generating new content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query describing what knowledge you need"},
                "namespace": {"type": "string", "enum": ["paradigm", "formulation", "model", "simulation", "meta"], "description": "Optional: restrict search to a specific knowledge namespace"},
                "top_k": {"type": "integer", "description": "Number of results to return (default: 5)", "default": 5}
            },
            "required": ["query"]
        }
    }
    ```

  - The tool handler function (closure):
    ```python
    async def handle_retrieve_knowledge(query: str, namespace: str | None = None, top_k: int = 5) -> str:
    ```
    - Runs the full pipeline:
      1. KG retrieval (P3-001) — skip if `kg is None`
      2. Dense + sparse retrieval (P3-002) — skip if `vector_store is None`
      3. RRF fusion (P3-003)
      4. Reranking (P3-003)
      5. CRAG evaluation (P3-004) — task_context auto-generated from `stage` parameter
    - Builds filters: `namespace` if provided, `exclude_run_id=run_id` (avoid self-retrieval)
    - Formats output as a structured text block:
      ```
      ## Retrieved Knowledge (N results)

      ### Result 1 [source: kg | confidence: 0.92]
      <passage text>
      — Source: "Paper Title" (Author, Year) | Stage: researcher | Run: abc123

      ### Result 2 [source: dense | confidence: 0.87]
      <passage text>
      — Source: formulation/hedonic-regulation | Stage: formalizer | Run: def456

      ...

      ### Result N [source: web | fresh search]
      <passage text>
      — Source: DuckDuckGo search result
      ```
    - If all infrastructure is None (no knowledge backbone): return "Knowledge backbone not available. Proceeding without retrieved context."
    - Auto-generates `task_context` for CRAG from stage: "The {stage} agent is working on {stage_description}" where stage_description maps from stage name

- **Tool registration pattern:**
  - Follow the existing pattern in `tools/files.py`: factory function returns `(tool_definition, handler_function)` tuple
  - The tool is added to each agent's tool list in `router.py` alongside `read_file`, `write_file`, etc.
  - The tool dispatcher in `runtime/dispatcher.py` handles it like any other tool

- **Memory access tracking:**
  - When results are returned, call `touch_memory(memory_id)` for each Postgres-backed result to update `last_accessed_at` and `access_count`
  - This enables future consolidation to know which memories are frequently used

## Acceptance Criteria
- [ ] AC1: `create_retrieve_knowledge(...)` returns a valid Anthropic tool definition with correct schema
- [ ] AC2: An agent calling `retrieve_knowledge(query="Q-learning convergence")` gets formatted results with source attributions
- [ ] AC3: `namespace="paradigm"` restricts results to paradigm-namespace content only
- [ ] AC4: Self-retrieval prevention: results from the current `run_id` are excluded
- [ ] AC5: When knowledge infrastructure is unavailable (all None), the tool returns a graceful message instead of failing
- [ ] AC6: `top_k=3` returns at most 3 results
- [ ] AC7: Accessed memories have their `last_accessed_at` and `access_count` updated in Postgres
- [ ] AC8: The tool integrates with the existing dispatcher — can be called by any agent via the standard tool_use mechanism

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/retrieval/__init__.py` — export create_retrieve_knowledge

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `tool`
Depends on P3-003 (fusion + reranking) and P3-004 (CRAG evaluator) — this is the capstone that assembles the full retrieval pipeline into a single tool.
The tool will be wired into pipeline agents in Phase 4 (pipeline integration).
