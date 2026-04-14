---
id: P5-003
title: Build post-run consolidation with clustering, reflections, and pruning
status: todo
kind: strike
phase: 5
heat: consolidation
priority: 3
blocked_by: [P5-002]
created: 2026-04-14
updated: 2026-04-14
---

# P5-003: Build post-run consolidation with clustering, reflections, and pruning

## Objective
Implement the consolidation pipeline that runs after each pipeline run completes: cluster related memories, generate higher-level reflections, apply time decay, and prune stale knowledge.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/consolidation.py`

- `async consolidate(db_session, embedding_service, vector_store, client) -> ConsolidationResult`
  - Called from Router after the BUILD stage + Memory Agent completes

- **Step 1: Cluster related memories**
  - Load all memories from the completed run (filter by run_id, valid_to IS NULL)
  - Embed all memory contents (or re-use existing Qdrant embeddings via search-by-id)
  - Pairwise cosine similarity matrix
  - Single-linkage clustering with threshold > 0.80
  - Group memories into clusters of related facts

- **Step 2: Generate reflections (Generative Agents pattern)**
  - For each cluster with >=3 memories:
    - Build prompt: "Given these related facts from a research pipeline run, synthesize 1-2 higher-level insights that capture the key pattern or finding. Be specific and scientific."
    - Present all cluster members as numbered facts
    - Call Haiku → get reflection text
    - Store as new memory: `memory_type="reflection"`, `namespace="meta"`, `importance=8.0` (reflections are inherently high-importance), `confidence=0.7`
    - Store cluster member IDs in `metadata.source_memories`
  - Compare new reflections against existing reflections (from past runs) via embedding similarity:
    - Similarity > 0.85 to existing reflection → corroborate existing reflection
    - Similarity > 0.85 but contradictory content (detected via Haiku) → log contradiction

- **Step 3: Apply time decay**
  - Query all memories where `last_accessed_at < now - 30 days` AND `valid_to IS NULL` AND `memory_type != "reflection"`
  - Apply confidence decay: `confidence *= 0.95 ** periods` where `periods = days_since_access // 30`
  - Update confidence in Postgres AND in Qdrant payload (to keep them in sync)

- **Step 4: Prune stale memories**
  - Query memories where: `confidence < 0.2` AND `access_count == 0` AND `created_at < now - 90 days` AND `valid_to IS NULL`
  - Set `valid_to = now` (soft delete)
  - Do NOT delete from Qdrant (vectors remain for historical queries)
  - Log pruned memory count

- `ConsolidationResult` dataclass:
  ```python
  @dataclass
  class ConsolidationResult:
      clusters_found: int
      reflections_generated: int
      reflections_corroborated: int
      memories_decayed: int
      memories_pruned: int
      duration_ms: int
  ```

## Acceptance Criteria
- [ ] AC1: After a run that produced 30 facts, consolidation finds >=3 clusters of related memories
- [ ] AC2: At least 1 reflection is generated from a cluster of >=3 facts, stored with memory_type="reflection" and namespace="meta"
- [ ] AC3: A reflection similar to an existing one from a past run corroborates it (corroborations counter increases)
- [ ] AC4: Memories untouched for 60 days have their confidence reduced by ~10% (0.95^2)
- [ ] AC5: A 120-day-old memory with confidence 0.15 and access_count=0 is pruned (valid_to set)
- [ ] AC6: A 120-day-old memory with confidence 0.15 but access_count=5 is NOT pruned (access_count > 0)
- [ ] AC7: Consolidation completes in <10 seconds for a typical run with ~50 memories

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/consolidation.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/models.py` — add ConsolidationResult dataclass
- `phase1-pablo/src/decisionlab/router.py` — call consolidation after BUILD + Memory Agent

## Context
Phase spec: `docs/specs/knowledge/phase-5-cross-run-memory.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `consolidation`
Depends on P5-002 for the confidence evolution mechanics it applies during time decay.
