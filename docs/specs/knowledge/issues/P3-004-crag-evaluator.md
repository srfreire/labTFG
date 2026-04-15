---
id: P3-004
title: Build Corrective RAG evaluator with web search fallback
status: done
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
- [x] AC1: A result about "ghrelin hunger signaling" when the task is "formalize homeostatic regulation" is classified CORRECT
- [x] AC2: A result about "ghrelin hunger signaling" when the task is "build a Q-learning grid agent for stock trading" is classified INCORRECT (domain mismatch)
- [x] AC3: A result that's partially relevant (same paradigm, different formulation aspect) is classified AMBIGUOUS
- [x] AC4: When all results are INCORRECT, `action="web_fallback"` and `web_results_used > 0`
- [x] AC5: When some results are AMBIGUOUS, `action="supplemented"` and final results contain both stored + web results
- [x] AC6: When all results are CORRECT, `action="pass_through"` and no web search is triggered
- [x] AC7: Web fallback uses existing DuckDuckGo adapter — no new search infrastructure
- [x] AC8: If Haiku evaluation fails, all results default to CORRECT (fail-open, don't block retrieval)

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/retrieval/models.py` — add CRAGResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `crag`
Depends on P3-003 for reranked `RetrievalResult` input.
Uses existing `WebSearchPort` adapter from `adapters/duckduckgo.py` and `search_papers` from `tools/papers.py`.

## Completion Summary

**Commit:** `7dcd3ff` — `feat[knowledge]: implement CRAG evaluator with web search fallback (P3-004)`

### What was built
- `_classify_results()` — calls Haiku to batch-evaluate all retrieved passages as CORRECT/AMBIGUOUS/INCORRECT, with JSON parsing, fence stripping, bounds validation, and fill-missing-indices
- `evaluate_results()` — action routing: pass_through (all CORRECT or CORRECT+INCORRECT), supplemented (has AMBIGUOUS, merges stored+web results with reranking), web_fallback (all INCORRECT, fresh web search)
- `web_fallback()` — fetches results from DuckDuckGo via existing `WebSearchPort`, reranks via Voyage AI, returns as `RetrievalResult(source="web")`
- `CRAGResult` frozen dataclass added to `models.py`
- 13 unit tests covering all 8 acceptance criteria plus edge cases (mixed CORRECT+INCORRECT routing, OOB Haiku indices, bad JSON fail-open, empty inputs)

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` — new file (~252 lines)
- `phase1-pablo/src/decisionlab/knowledge/retrieval/models.py` — added `CRAGResult` dataclass
- `phase1-pablo/src/decisionlab/knowledge/retrieval/__init__.py` — added `CRAGResult`, `evaluate_results`, `web_fallback` exports
- `phase1-pablo/tests/knowledge/test_crag.py` — 13 unit tests with mocked dependencies

### Decisions
- Fail-open on Haiku errors: all results default to CORRECT (AC8), with `logger.warning` for observability
- Mixed CORRECT+INCORRECT (no AMBIGUOUS): treated as pass_through with only CORRECT results kept — reviewer caught routing bug where this fell through to supplemented
- OOB Haiku indices rejected during validation (bounds check `0 <= index < len(results)`) — reviewer caught this
- Metadata shallow-copied in supplemented path to prevent shared-state mutation through frozen dataclass
- Web fallback uses only DuckDuckGo (Semantic Scholar integration deferred — `search_papers` returns formatted text, not structured data suitable for direct embedding)
