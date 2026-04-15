---
id: P3-004
title: Build Corrective RAG evaluator with web search fallback
status: in-progress
kind: strike
phase: 3
heat: crag
priority: 3
blocked_by: [P3-003]
created: 2026-04-14
updated: 2026-04-15
---

# P3-004: Build Corrective RAG evaluator with web search fallback

## Objective
Implement the CRAG evaluation layer that classifies each reranked result as CORRECT/AMBIGUOUS/INCORRECT, and falls back to web search when stored knowledge is insufficient.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py`

- **CRAG Evaluator:**
  `async evaluate_results(query: str, task_context: str, results: list[RetrievalResult], client: AsyncAnthropic) -> CRAGResult`

  - `task_context`: describes what the downstream agent needs (e.g., "The Formalizer is writing mathematical formulations for reward-based paradigms"). Helps Haiku judge relevance beyond surface similarity.
  - Single Haiku call evaluates ALL results at once (batch, not per-result):
    - Prompt: "Given this query and task context, classify each retrieved passage as CORRECT (relevant and useful for the task), AMBIGUOUS (partially relevant or uncertain), or INCORRECT (not useful, stale, or from wrong domain). Return JSON: {evaluations: [{index, classification, reasoning}]}"
  - Parse response, classify each result

- **Action routing:**
  - Count classifications: n_correct, n_ambiguous, n_incorrect
  - If n_correct > 0 and n_incorrect == 0: return CORRECT results only (pass-through)
  - If n_ambiguous > 0: keep CORRECT + AMBIGUOUS results, trigger web supplement
  - If all INCORRECT (n_correct == 0 and n_ambiguous == 0): discard all, trigger full web fallback

- **Web search fallback:**
  `async web_fallback(query: str, search_adapter: WebSearchPort, embedding_service: EmbeddingService, top_k: int = 5) -> list[RetrievalResult]`
  - Run DuckDuckGo search via existing `WebSearchPort` adapter
  - Run Semantic Scholar search via existing `search_papers` function (if query looks academic — contains author names, DOIs, or paradigm terms)
  - Combine results, embed via Voyage AI, score by cosine similarity to query embedding
  - Return top_k as `RetrievalResult(source="web")`

- **Combined CRAG output:**
  ```python
  @dataclass
  class CRAGResult:
      results: list[RetrievalResult]     # final validated context
      action: str                         # "pass_through", "supplemented", "web_fallback"
      evaluations: list[dict]             # per-result classification + reasoning
      web_results_used: int               # how many web results were added
  ```

- **Fallback integration:**
  - When supplementing: merge stored CORRECT/AMBIGUOUS results with web results, rerank the combined set via Voyage AI reranker, return top_k
  - When full fallback: web results only, reranked, returned as final context

## Acceptance Criteria
- [ ] AC1: A result about "ghrelin hunger signaling" when the task is "formalize homeostatic regulation" is classified CORRECT
- [ ] AC2: A result about "ghrelin hunger signaling" when the task is "build a Q-learning grid agent for stock trading" is classified INCORRECT (domain mismatch)
- [ ] AC3: A result that's partially relevant (same paradigm, different formulation aspect) is classified AMBIGUOUS
- [ ] AC4: When all results are INCORRECT, `action="web_fallback"` and `web_results_used > 0`
- [ ] AC5: When some results are AMBIGUOUS, `action="supplemented"` and final results contain both stored + web results
- [ ] AC6: When all results are CORRECT, `action="pass_through"` and no web search is triggered
- [ ] AC7: Web fallback uses existing DuckDuckGo adapter — no new search infrastructure
- [ ] AC8: If Haiku evaluation fails, all results default to CORRECT (fail-open, don't block retrieval)

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/retrieval/models.py` — add CRAGResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `crag`
Depends on P3-003 for reranked `RetrievalResult` input.
Uses existing `WebSearchPort` adapter from `adapters/duckduckgo.py` and `search_papers` from `tools/papers.py`.
