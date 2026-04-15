# Phase 3: 3-Layer Retrieval & CRAG

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Build the read path of the knowledge backbone: parallel 3-layer retrieval (KG traversal + dense vector search + sparse BM25 search), Reciprocal Rank Fusion, Voyage AI reranking, and Corrective RAG evaluation with web search fallback. Expose the full retrieval pipeline as a tool callable by pipeline agents.

## Requirements

### R1: Knowledge Graph Retrieval (HippoRAG-style PPR)
- Given a query, extract entities via Haiku, link them to Neo4j nodes by embedding similarity, then run Personalized PageRank from matched nodes to discover related passages.
- Steps: query → entity extraction (Haiku NER) → entity linking (embed entity names, match against KG node name embeddings) → PPR traversal (spread activation 2 hops) → collect passages connected to high-activation nodes.
- Output: ranked list of `RetrievalResult(text, score, source, metadata)`.

### R2: Dense Vector Retrieval
- Embed query via Voyage AI (`input_type="query"`), search `artifacts_dense` + `memories_dense` collections in Qdrant.
- Support payload filters: namespace, min_confidence, run_id exclusion (avoid self-retrieval within same run).
- Output: ranked list of `RetrievalResult`.

### R3: Sparse/Lexical Retrieval
- Generate sparse query representation, search `artifacts_sparse` + `memories_sparse` collections in Qdrant.
- Catches exact matches that dense retrieval misses: DOIs, author surnames, variable names, equation symbols.
- Output: ranked list of `RetrievalResult`.

### R4: Reciprocal Rank Fusion
- Merge results from all 3 retrieval channels using RRF with k=60.
- `RRF_score(d) = Σ_r 1/(k + rank_r(d))` where r iterates over retrievers that returned document d.
- Deduplicate by text content (same passage from multiple channels → single entry with combined RRF score).
- Output: single ranked list, top-N (configurable, default 30).

### R5: Voyage AI Reranking
- Take top-N from RRF, rerank via `EmbeddingService.rerank(query, documents, top_k)`.
- Filters results below a relevance threshold (configurable, default 0.3).
- Output: reranked list, top-K (configurable, default 10).

### R6: Corrective RAG Evaluator
- Haiku classifies each reranked result as CORRECT, AMBIGUOUS, or INCORRECT given the query and the downstream task context.
- Action routing:
  - All CORRECT → use results as-is.
  - Any AMBIGUOUS → keep CORRECT + AMBIGUOUS results, supplement with web search results.
  - All INCORRECT → discard all, fallback to web search only.
- Web search fallback: use existing DuckDuckGo adapter (`WebSearchPort`) + Semantic Scholar (`search_papers` tool) to fetch fresh content. Embed and rerank fresh results the same way.
- Output: final `CRAGResult` with validated context ready for injection.

### R7: Retrieval Tool for Pipeline Agents
- A single tool function `retrieve_knowledge(query, namespace=None, top_k=10)` that runs the full pipeline (R1-R6) and returns formatted context.
- Designed to be added to any pipeline agent's tool set via the existing `create_*` tool factory pattern.
- Returns: formatted text block with source attributions (paper title, DOI, stage origin) suitable for direct injection into agent context.

## Acceptance Criteria
- [x] AC1: KG retrieval on "ghrelin hunger signaling" against a populated graph returns passages mentioning ghrelin's role in hunger, including multi-hop connections (ghrelin → hypothalamus → hunger)
- [x] AC2: Dense retrieval on "Q-learning convergence" returns relevant formulation and model chunks
- [x] AC3: Sparse retrieval on an exact DOI string returns the chunk containing that citation
- [x] AC4: RRF fusion combines results from all 3 channels — a document found by 2 channels scores higher than one found by 1
- [x] AC5: Reranking reorders RRF results — a semantically relevant but low-RRF-ranked result can move up
- [x] AC6: CRAG evaluator classifies a stale memory about an unrelated topic as INCORRECT and triggers web fallback
- [x] AC7: CRAG evaluator classifies a relevant, current memory as CORRECT and passes it through
- [ ] AC8: Full pipeline (KG + dense + sparse → RRF → rerank → CRAG) completes within 3 seconds on a warm knowledge base with ~500 memories
- [ ] AC9: `retrieve_knowledge` tool returns formatted text with source attributions that include paper titles and pipeline stage origin
- [x] AC10: Retrieval with empty knowledge base (cold start) returns empty result gracefully — no errors, no hallucinated results

## Technical Notes
- KG retrieval PPR: implement via Cypher `algo.pageRank` (APOC/GDS) or manual BFS with decay factor if GDS plugin is unavailable. Start simple: 2-hop BFS with exponential decay (0.85^hop) is a good approximation of PPR for small graphs.
- Sparse vectors: Qdrant supports sparse vectors natively. For generating sparse representations at query time, use the same tokenization as indexing (P2-003).
- The retrieval pipeline runs ~3 LLM calls: 1 Haiku for KG entity extraction, 1 Voyage rerank, 1 Haiku for CRAG evaluation. Total cost per retrieval: ~$0.002.
- All 3 retrieval channels should run via `asyncio.gather` for parallel execution.
- The web search fallback reuses existing infrastructure: `DuckDuckGoAdapter` from `adapters/duckduckgo.py` and `search_papers` from `tools/papers.py`.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| PPR vs full GraphRAG community search | PPR (HippoRAG-style) | Simpler, faster, better for entity-centric queries. GraphRAG's global search is overkill — the pipeline doesn't ask corpus-level questions. |
| 2-hop BFS vs Neo4j GDS PageRank | 2-hop BFS with decay | Avoids GDS plugin dependency. Graph is small enough (<1K nodes per run) that BFS is fast. Can upgrade later. |
| Single `retrieve_knowledge` tool vs per-layer tools | Single unified tool | Pipeline agents shouldn't care about retrieval internals. One tool, one query, one result. |
| CRAG web fallback sources | DuckDuckGo + Semantic Scholar | Already wired up in the pipeline. No new dependencies. |
| Reranker threshold 0.3 | 0.3 | Conservative — lets marginal results through for CRAG to evaluate. Better to over-retrieve and filter than miss useful context. |
