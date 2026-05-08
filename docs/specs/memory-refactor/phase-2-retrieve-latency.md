# Phase 2: Retrieve latency

> Status: current | Created: 2026-05-08 | Last updated: 2026-05-08 (P2-003 done)
> References: [general.md](general.md) · [phases.md](phases.md) · [`docs/memory-system.md`](../../memory-system.md) §A4, §A5

## Objective

Cut `retrieve_knowledge` p95 from 14–20s to ≤2.5s by removing
redundant LLM calls from the hot path. Three structural moves: skip
CRAG when the rerank is already confident; skip Haiku NER when the
dense retrieval is decisive; batch the per-result `touch_memory`
writes. One robustness fix: distinguish CRAG-grader **errors** from
genuine **AMBIGUOUS** verdicts so a Haiku outage doesn't trigger a
DuckDuckGo storm.

Expected impact (re-measured against the slug-accuracy
`p95_below: 2500` assertion):
- Confident queries (≥50 % of traffic) skip CRAG entirely → save one
  Haiku round-trip (~2-3s).
- Confident queries also skip NER → save another Haiku round-trip.
- `touch_memory` becomes one PG round-trip instead of N.
- LLM-outage path returns reranked results instead of going to web
  search.

## Requirements

### R1 — Conditional CRAG below high rerank threshold (A4 part 1)

In `decisionlab/knowledge/retrieval/tool.py:handle_retrieve_knowledge`,
after `fuse_and_rerank` returns:

```python
top_score = max((r.score for r in reranked[:top_k]), default=0.0)
if top_score >= CRAG_SKIP_THRESHOLD:  # default 0.5
    # Trust the rerank — pass through.
    crag_result = CRAGResult(
        results=reranked[:top_k * 2],
        action="rerank_pass_through",
        evaluations=[],
        web_results_used=0,
    )
else:
    crag_result = await evaluate_results(...)
```

`CRAG_SKIP_THRESHOLD` is configurable
(`SETTINGS.crag_skip_threshold`, default 0.5). Telemetry counter
records skip vs. evaluate decisions.

### R2 — Skip NER when dense top-1 is decisive (A4 part 2)

In `decisionlab/knowledge/retrieval/tool.py`, run `vector_retrieve`
first (it's fast — no LLM). If the dense top-1 score ≥
`NER_SKIP_THRESHOLD` (default 0.7), skip the parallel `kg_retrieve`
call entirely — KG traversal adds latency and the dense channel
already has a strong answer.

When NER is skipped, `kg_results = []` is passed to fusion, and the
RRF still merges sparse + dense as before.

### R3 — Batch `touch_memory` writes (A4 part 3)

In `_track_memory_access`, replace the per-id `for` loop with a
single batched UPDATE:

```python
async with shared.db.get_session() as session:
    await session.execute(
        update(Memory)
        .where(Memory.id.in_(memory_ids))
        .values(
            last_accessed_at=func.now(),
            access_count=Memory.access_count + 1,
            confidence=func.least(1.0, Memory.confidence + 0.02),
        )
    )
    await session.commit()
```

One PG round-trip regardless of how many results were Postgres-backed.

### R4 — Distinguish CRAG grader errors from AMBIGUOUS (A5)

`crag._classify_results` already detects the fail-closed sentinel
("Default (evaluation failed)") and sets `grading_failed=True` on the
returned `CRAGResult`. The routing code in `evaluate_results`
**ignores** this flag and treats every passage as AMBIGUOUS, which
forces a web fallback.

Change: when `grading_failed`, return the reranked results unchanged
with `action="grader_unavailable"` and **do not** invoke web search.
The agent receives a `[grader_unavailable]` marker in the response so
it knows the grade is provisional, but the caller doesn't burn a
DuckDuckGo budget on every retrieve while Haiku is rate-limited.

## Acceptance Criteria

- [ ] AC1: `CRAG_SKIP_THRESHOLD` is read from settings, default 0.5.
      Skip path is exercised when top rerank score ≥ threshold; full
      CRAG runs when below. Unit test covers both.
- [ ] AC2: `NER_SKIP_THRESHOLD` is read from settings, default 0.7.
      Skip path is exercised when dense top-1 ≥ threshold; KG
      retrieval runs when below. Unit test covers both.
- [x] AC3: `_track_memory_access` issues exactly one SQL UPDATE per
      retrieve call regardless of result count. Test asserts via
      mocked session.
- [ ] AC4: When CRAG grader errors, the routing returns reranked
      results with `action="grader_unavailable"` and
      `web_results_used=0`. No web fallback. Unit test exercises the
      Haiku-fail path.
- [ ] AC5: A re-run of `slug-accuracy.yaml` measures
      `p95_below: 2500` PASS for `retrieve_knowledge`. Manual probe
      query against a populated KG returns in ≤2.5s end-to-end at
      p95 over 20 calls.

## Technical Notes

- **Order of intervention**: R2 (NER skip) is the cheapest single
  win because dense retrieval is already running; R1 (CRAG skip)
  requires a tiny refactor of `handle_retrieve_knowledge`'s control
  flow. R3 is mechanical. R4 is one branch in the routing code.
- **Telemetry**: add `record_usage`-style counters for
  `crag.skipped`, `ner.skipped`, `crag.grader_failed`. Useful for
  proving impact in subsequent eval runs.
- **Heats**:
  - `crag-grader` (R1, R4) — sequential, both touch `crag.py` and
    `tool.py` routing.
  - `ner` (R2) — independent.
  - `db-batching` (R3) — independent.

## Decisions

- **Trust the rerank above 0.5**. ZeroEntropy `zerank-2` is calibrated
  enough that a 0.5 score is meaningful. Document the threshold as
  tunable.
- **Skip NER, don't skip KG** when dense is confident — the kg_retrieve
  call's own NER step is what's expensive (Haiku); the BFS itself
  is local and fast. So R2 specifically targets the NER call inside
  `kg_retrieve`, not the BFS.
- **Don't supplement with web on grader error**. Web fallback was
  designed for genuine AMBIGUOUS verdicts; using it as a fallback
  for a degraded Haiku just amplifies the outage.
