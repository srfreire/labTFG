# Knowledge Backbone — Phase Breakdown

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-14
> References: [general.md](general.md)

## Phases

- [x] **Phase 1: Infrastructure & Storage Layer** — Neo4j schema, Qdrant collections, Postgres memories table, Voyage AI client, Docker Compose integration. No agents yet — just the data layer and Python clients.
  - Dependencies: none
  - Issues: P1-001, P1-002, P1-003, P1-004, P1-005
  - Heats: data-model (P1-001→P1-002), vector (P1-003→P1-004), infra (P1-005)

- [x] **Phase 2: Memory Agent & Knowledge Extraction** — The Memory Agent that runs after each pipeline stage: entity/relation extraction (Haiku), KG population (Neo4j writes), embedding + indexing (Qdrant writes), importance scoring, mem0-style conflict resolution (Sonnet), provenance edge creation.
  - Dependencies: Phase 1
  - Issues: P2-001, P2-002, P2-003, P2-004, P2-005
  - Heats: extraction (P2-001), kg-write (P2-002, after P2-001), indexing (P2-003, after P2-001), resolution (P2-004, after P2-001+P2-003), agent (P2-005, after P2-002+P2-003+P2-004)

- [x] **Phase 3: 3-Layer Retrieval & CRAG** — The read path: parallel KG traversal (HippoRAG PPR), dense vector search, sparse BM25 search, RRF fusion, Voyage AI reranking, CRAG evaluator (Haiku) with web search fallback. Exposes retrieval as tools for pipeline agents.
  - Dependencies: Phase 1
  - Issues: P3-001, P3-002, P3-003, P3-004, P3-005
  - Heats: retrieval (P3-001 ∥ P3-002), fusion (P3-003, after P3-001+P3-002), crag (P3-004, after P3-003), tool (P3-005, after P3-003+P3-004)

- [x] **Phase 4: Pipeline Integration** — Wire retrieval tools into existing agents (Researcher, Formalizer, Reasoner, Builder). Wire Memory Agent into Router's stage transitions. Graceful degradation when infra is unavailable.
  - Dependencies: Phase 2, Phase 3
  - Issues: P4-001, P4-002, P4-003, P4-004, P4-005
  - Heats: agent-tools (P4-001→P4-002), router (P4-003), resilience (P4-004 after P4-001+P4-003, P4-005 after P4-003)

- [x] **Phase 5: Cross-Run Memory & Consolidation** — Persistent memory across runs: cross-run retrieval scoping, confidence evolution (corroboration/contradiction tracking), post-run consolidation (clustering, reflection generation, pruning), temporal validity management.
  - Dependencies: Phase 4
  - Issues: P5-001, P5-002, P5-003, P5-004
  - Heats: cross-run (P5-001→P5-002), consolidation (P5-003 after P5-002, P5-004 after P5-001)

- [ ] **Phase 6: Schema Cleanse** — Simplify and clean up the KG schema, extraction prompts, and retrieval logic based on lessons learned. Remove unnecessary node types, consolidate properties, fix naming inconsistencies.
  - Dependencies: Phase 5
  - Issues: P6-001
  - Heats: schema (P6-001)

- [ ] **Phase 7: Frontend Knowledge Visualization** — Interactive knowledge graph explorer in Phase 2's web UI, provenance trail viewer, memory inspector, cross-run knowledge diff.
  - Dependencies: Phase 6
  - Estimated issues: ~5 (future phase, not forged now)

## Parallelism

```
Phase 1 ──────────────────┐
                          ├──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6 ──▶ Phase 7
Phase 2 (after Phase 1) ──┤
Phase 3 (after Phase 1) ──┘

Phases 2 and 3 can run in PARALLEL (write path vs read path, independent code).
Phase 4 merges them.
```
