# Memory system accuracy refactor — design

**Author:** Pablo Pazos Parada (with assistant)
**Date:** 2026-05-08
**Phase:** 1 (Researcher → Canonicalizer → KG/Vector backbone, shared library)
**Status:** Draft, awaiting user review

## Goal

Lift the memory subsystem from the current Phase F regression baseline (slug
reuse rate ≈ 50%, KG growth ≈ 84 nodes/topic, no continuous accuracy metric)
to a measurable, instrumented state:

- **Slug reuse rate ≥ 80%** on `paradigm-canonicalization.yaml` topics.
- **Merge precision ≥ 0.95, recall ≥ 0.90** on `canonicalize-pairs.json`.
- **KG growth ≤ 30 nodes/topic** on `cumulative-growth.yaml`.
- **Retrieval p95 ≤ 2.5s** on `retrieve_knowledge` (currently uncovered).
- **Continuous metrics** (precision, recall, hit rate, latency) emitted to
  every report — not just binary pass/fail.

## Non-goals

- New paradigms / new agents (Phase 1 scope only).
- Reflection prompt redesign (separate work).
- Multi-tenant or auth concerns.
- Migrating to a different vector store or KG.
- DeepResearcher max-iter exhaustion (separate, see status doc).

## Background

The memory system spans `phase1-pablo/src/decisionlab/knowledge/` and
`shared/shared/`. Three stores:

- **Neo4j** — Paradigm/Postulate/Variable/Equation/etc. nodes, slug-keyed.
- **Qdrant** — `artifacts_dense`, `artifacts_sparse`, `memories_dense`,
  `memories_sparse` (1024-dim Voyage + native BM25).
- **Postgres** — `memories` table (full-text, namespace-scoped, temporal).

Pipeline: extract → resolver (text-based dedup on facts) → canonicalize
(cosine + LLM verify) → kg_writer → vector indexer. Retrieval: vector
(dense+sparse, RRF k=60) + KG (NER → entity link → 2-hop PPR) → fuse →
Voyage rerank → CRAG self-grade → truncate.

Baseline numbers are from the 2026-05-07 reports under
`evals/reports/2026-05-07-paradigm-canonicalization/` and
`evals/reports/2026-05-07-cumulative-growth/`.

## Bottlenecks identified (file:line citations)

| # | Where | Symptom |
|---|-------|---------|
| **B1** | `agents/researcher.py:201-242` | `_parse_known_slugs` regex requires markdown bullet+bold format; on miss, every paradigm becomes `__NEW__`. |
| **B2** | `agents/researcher.py:196-198` | `_slug_from_proposal` returns literal `"paradigm"` when slugify yields empty → silent collisions across unrelated paradigms. |
| **B3** | `tools/reports.py:34-37` | `slugify` non-idempotent: keeps `()`, `_`, accents → fragmentation across surface variations. |
| **B4** | `canonicalize.py:165-182` | Single best-neighbor merge; no ancestor expansion → Q-learning can mis-merge with policy-gradient. |
| **B5** | `canonicalize.py:53-54` | One τ=0.85 across Paradigm/Variable/Postulate; under-tuned per label. |
| **B6** | `retrieval/tool.py:300+` | No query rewriting; multi-sentence prompts dilute embedding signal. |
| **B7** | `retrieval/vector_retrieval.py:54-55` | `exclude_run_id` applied post-query in Python → effective recall shrunk. |
| **B8** | `retrieval/kg_retrieval.py:189-191` | Entity linking does Cypher table scan + Python cosine when exact match misses (O(N)). |
| **B9** | `retrieval/kg_retrieval.py:289-308` | PPR is undirected, untyped, no IDF → hub nodes leak everywhere. |
| **B10** | `retrieval/crag.py:53-60, 125-127` | CRAG fail-open: any Haiku error → all results pass through unverified. |
| **B11** | `retrieval/tool.py:374` | Top-k truncation post-CRAG drops web-supplemented results. |
| **B12** | `shared/knowledge_graph.py:17` | `Variable.name` globally unique → cross-paradigm collisions. |
| **B13** | `knowledge/resolver.py:126, 278` | Conflict classifier sees `text_preview[:200]` only → ENRICHMENT fired when DUPLICATE was correct. |
| **B14** | `knowledge/consolidation.py:514-545` | Pruned memories never deleted from Qdrant. |
| **B15** | `knowledge/consolidation.py:339` | `Reflection` uses bare CREATE; consolidation retry → duplicates. |
| **B16** | `knowledge/resolver.py:178-184, 354-367` | UNKNOWN classification → fail-open store as new memory. |
| **B17** | (eval-wide) | No continuous metric: predicates are binary pass/fail; no latency. |

## Architecture: 4 tracks + 1 instrumentation track

### Track A — Slug canonicalization (closes B1-B5)

**A1. Drop markdown reparsing.** Add a new helper in
`retrieval/tool.py`:

```python
async def list_known_slugs(
    query: str, namespace: str = "paradigm", top_k: int = 8
) -> list[tuple[str, str]]:
    """Return [(slug, definition), ...] for the top-k matching paradigm
    nodes. Uses the same vector + KG backbone as retrieve_knowledge but
    skips markdown formatting and reranking."""
```

Researcher calls this directly instead of `_parse_known_slugs`. Delete the
regex and the fallback token scanner. The tool returns slugs from KG node
metadata, not regex-parsed prose.

**A2. Reject empty slug proposals.** In `_slug_from_proposal`:

```python
def _slug_from_proposal(name: str, *, definition: str = "") -> str:
    s = slugify(name)
    if s:
        return s
    # Deterministic fallback so two empty proposals on different paradigms
    # don't collide on the literal "paradigm" sentinel.
    digest = hashlib.sha1(definition[:128].encode()).hexdigest()[:10]
    return f"unnamed-{digest}"
```

Caller passes `definition` from the emission. The `"paradigm"` literal goes
away.

**A3. Idempotent slugify.** In `tools/reports.py`:

```python
def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return re.sub(r"-{2,}", "-", name).strip("-")
```

Wire it into `kg_writer._validate_natural_key` so slugs supplied by the LLM
get re-normalized at the writer boundary. Add `test_slugify_idempotent` —
`slugify(slugify(x)) == slugify(x)` for a corpus of edge cases.

**A4. Two-pass canonicalize with ancestor expansion** in `canonicalize.py`.
Replace the single best-neighbor block (lines 165-182) with:

```python
# Pass 1 — direct neighbor at threshold τ_direct (e.g. 0.85)
direct_match = _best_neighbor(cand_vec, exist_vecs, tau=tau_direct)

# Pass 2 — for Paradigm only, if direct miss but cosine >= τ_loose (0.78),
# fetch parent paradigms via BELONGS_TO/EXTENDS and re-test against them.
if label == "Paradigm" and direct_match is None:
    loose = _best_neighbor(cand_vec, exist_vecs, tau=tau_loose)
    if loose is not None:
        ancestors = await _fetch_ancestors(kg, loose.key_value)
        # Merge into the strongest ancestor that the verifier accepts,
        # not into the loose neighbor itself.
        direct_match = await _select_ancestor(
            ancestors, cand_text, cand_vec, client
        )
```

`_fetch_ancestors` runs Cypher
`MATCH (n:Paradigm {slug: $slug})-[:EXTENDS|:BELONGS_TO*1..2]->(p:Paradigm) RETURN p`.

**A5. Per-label thresholds, calibrated against the fixture.** Replace
`DEFAULT_THRESHOLD = 0.85` with hand-picked initial values, then calibrate
once against `canonicalize-pairs.json` using only cached embeddings (no
LLM loop):

```python
LABEL_THRESHOLDS: dict[str, tuple[float, float]] = {
    # (τ_direct, τ_loose) — τ_loose only used by Pass 2 for ancestor expansion
    "Paradigm":  (0.85, 0.78),
    "Variable":  (0.90, 0.90),  # tighter; no ancestor pass
    "Postulate": (0.83, 0.83),  # tighter; no ancestor pass
}
```

A new script `scripts/calibrate_canonicalize_tau.py` runs the 18-pair
fixture through the cached cosine scores at every τ ∈ [0.70, 0.95] in
0.01 steps, computes precision/recall vs the labelled `should_merge`,
picks the τ that maximizes F1 (tie-break toward higher precision), and
emits new `LABEL_THRESHOLDS` values. Total cost ~$0 — embeddings are
deterministic and cached. The LLM verifier sits on top of cosine and
catches the gray-zone subset between τ_loose and τ_direct, so the
calibrated τ doesn't need to be perfect on its own.

### Track B — Retrieval (closes B6-B11)

**B1. Query rewriting at the tool boundary.** New module
`retrieval/query_rewriter.py`:

```python
class _QueryRewrite(BaseModel):
    focal_concept: str   # short noun phrase, used for dense embedding
    keywords: list[str]  # 3-7 lemmas, used for BM25 augmentation + KG NER hint

async def rewrite(query: str, client: AsyncAnthropic) -> _QueryRewrite:
    """One-shot Haiku call. Caches by sha1(query[:512]) for 1h."""
```

The rewritten query feeds **both** vector retrieval and KG NER:
- Dense path (`vector_retrieval.py`) embeds `focal_concept` only.
- Sparse path uses original `query + " ".join(keywords)`.
- KG NER (`kg_retrieval._extract_entities`) accepts the rewritten object
  and prepends `keywords` to its prompt as a hint. Avoids re-discovering
  noun phrases the rewriter already extracted.

Cache hits make this near-free for repeated queries within a run.

**B2. Move `exclude_run_id` into Qdrant filter** in
`vector_retrieval.py:54-55`. Build `Filter(must_not=[FieldCondition(key="run_id", match=MatchValue(value=run_id))])`
and pass via `query_filter=`. Removes the post-query Python filter.

**B3. ANN-index the KG entity names.** New collection `kg_entities_dense`
in `vector_store.py`. On every `kg_writer.populate_kg` write, batch-upsert
`(elementId, label, name, description_embedding)`. In
`kg_retrieval._link_entities`:

```python
async def _link_entities_ann(label: str, name: str) -> list[ExistingNode]:
    vec = await embedding_service.embed_query(name)
    hits = await vector_store.search_dense(
        "kg_entities_dense", vec,
        limit=5, query_filter=Filter(must=[FieldCondition(key="label", match=MatchValue(value=label))]),
    )
    return [h for h in hits if h.score >= 0.75]
```

Dropping the table scan + Python loop. Migration: one-time backfill of
`kg_entities_dense` from current KG state.

**B4. Type-filtered + IDF-decayed PPR** in `kg_retrieval.py:289-308`:

```cypher
MATCH path = (start)-[r*1..2]-(connected)
WHERE ALL(rel IN r WHERE type(rel) IN $allowed_types)
RETURN connected, length(path) AS hops, COUNT { (connected)--() } AS degree
```

Score: `entity.confidence * 0.85^hops / log(2 + degree)`. `allowed_types`
chosen by query intent (paradigm-namespace queries use
`SUPPORTS|CONTRADICTS|EXTENDS|BELONGS_TO`; variable queries use
`MEASURES|HAS_PARAMETER|GOVERNS`).

**B5. CRAG fail-closed for INCORRECT.** In `crag.py:53-60`:

```python
except Exception as exc:
    logger.warning("CRAG grading failed — degrading to AMBIGUOUS path: %s", exc)
    # Don't auto-promote to CORRECT. If web is configured, fall through
    # to web supplement; otherwise return raw results with grading_failed=True
    # so the caller can choose how to surface uncertainty.
    return _CragGrades(grades=["AMBIGUOUS"] * len(results), grading_failed=True)
```

**B6. Pre-CRAG truncation OR post-CRAG window growth.** Choose:

```python
# Option (a) — preferred: keep top_k=10 throughout, only truncate at
# the agent-facing boundary, and only if no web supplements were added.
final_results = results if results.web_supplemented else results[:top_k]
```

Updates `tool.py:374`. Web-injected results survive when they're added.

### Track C — Population dedup (closes B12-B16)

**C1. Paradigm-scoped Variable keys.**

- `shared/knowledge_graph.py:15-27`: change `Variable` unique key from
  `name` to a synthetic `id = f"{paradigm_slug}:{name}"`.
- `kg_writer._resolve_natural_key`: when label==Variable and `paradigm_slug`
  is in properties, build the composite id.
- Migration script `phase1-pablo/scripts/migrate_variable_keys.py`:
  for each Variable node, walk `BELONGS_TO/MEASURED_IN` to find its
  paradigm; rewrite as `{paradigm}:{name}`. Variables with no paradigm
  edge keep the bare name (orphan tag).

**C2. Drop text_preview truncation in resolver.**
`shared/memories.py`: add `content_full` field to Qdrant payload (full
content, no 200-char cap) for `memories_*` collections only — artifacts
keep the cap. `resolver._classify_conflict` reads `content_full` instead of
`text_preview`. Index payload size grows ~2-5× for `memories_*`; acceptable.

**C3. Sync Qdrant deletes with Postgres prune.** In
`consolidation._prune_low_confidence` (around line 540):

```python
await store.update_memory(memory_id, valid_to=now)
await vector_store.delete_dense("memories_dense", point_id=str(memory_id))
await vector_store.delete_sparse("memories_sparse", point_id=str(memory_id))
```

Add `delete_dense`/`delete_sparse` helpers in `vector_store.py` if absent.

**C4. MERGE for Reflection.** Add to `KnowledgeGraph.SCHEMA`:

```python
"Reflection": {"unique_key": "id", "indexes": ["created_at"]},
```

In `consolidation._store_reflections` (around line 339), replace
`kg.create_node` with `kg.upsert_node(label="Reflection", key="id", value=...)`.
The `id` is `sha1(sorted(cluster_member_ids))[:16]` so re-running on the
same cluster idempotently produces the same node.

**C5. UNKNOWN → DUPLICATE under high-cosine candidate.**
`resolver._classify_conflict` returns metadata including
`fallback_used: bool`. In the caller:

```python
if classification == "UNKNOWN" and best_candidate_score >= 0.85:
    classification = "DUPLICATE"  # safe default under classifier failure
elif classification == "UNKNOWN":
    # Genuinely no candidate; store as new memory.
    classification = "NEW"
```

### Track D — Eval extensions (closes B17)

#### D1 — `slug_hit_rate` predicate

Reads `evals/fixtures/slug-oracle.json` (new):

```json
[
  {"topic_text": "Q-learning agent ...", "expected_slug": "reinforcement-learning"},
  {"topic_text": "Loss aversion in human ...", "expected_slug": "prospect-theory"},
  ...
]
```

`@register("slug_hit_rate")` in `eval/assertions.py`. Args:
`{oracle: path, min_rate: 0.8}`. Looks up the current topic by `topic_text`
match (sha1 prefix of normalized text), checks whether `expected_slug` is
in `result.paradigms`. Returns `AssertionOutcome(passed=hit, detail=f"{hit}/{1}")`.
Suite-level aggregate computed by report writer (sum hits / sum total).

#### D2 — `merge_precision_recall` predicate

```python
@register("merge_precision_recall")
async def _merge_pr(ctx, args):
    """Run canonicalize._verify_merge over canonicalize-pairs.json fixture
    and return precision/recall/F1.

    args: {fixture: path, min_precision: 0.95, min_recall: 0.90}
    """
```

This is a **standalone predicate** — no Researcher run needed. Suites
using it can declare `stages: []` and `topics: [{text: "merge-quality-check"}]`.
Each pair costs ~1 Sonnet `_verify_merge` call (~$0.05). 18 pairs ≈ $1.

#### D3 — `kg_growth_rate` predicate

```python
@register("kg_growth_rate")
async def _kg_growth(ctx, args):
    """Suite-level only. Fires after the last topic.
    args: {label: "Paradigm", max_per_topic: 6}
    Reads ctx.kg_before/kg_after, computes (after-before)/n_topics,
    passes if <= max.
    """
```

Replaces the manual deltas users compute by reading the report.

#### D4 — `slug-accuracy.yaml` suite

```yaml
name: slug-accuracy
stages: [research]
reset_kg_before: false  # KG seeded by cumulative-growth first
topics:
  # 5 from paradigm-canonicalization + 3 fragmenting variants
  - text: "Q-learning agent trades off exploration and exploitation ..."
    expect:
      research:
        - paradigm: reinforcement-learning
        - tool_called: { name: retrieve_knowledge, min: 1 }
  ...
  - text: "Q-learning policy variant with eligibility traces"
    expect:
      research:
        - paradigm: reinforcement-learning  # must NOT be a new "q-learning-traces" slug
  ...
suite_assertions:
  - slug_hit_rate: { oracle: evals/fixtures/slug-oracle.json, min_rate: 0.8 }
  # Per-label growth limits — Paradigm is the real signal; Variable is
  # expected to inflate after C1 paradigm-scoping; Postulate stays
  # bounded.
  - kg_growth_rate: { label: Paradigm,  max_per_topic: 1.5 }
  - kg_growth_rate: { label: Variable,  max_per_topic: 6   }
  - kg_growth_rate: { label: Postulate, max_per_topic: 5   }
budget:
  max_usd_total: 10.00
```

`slug_hit_rate` uses **liberal "anywhere" matching**: the canonical slug
counts as a hit if it appears anywhere in `result.paradigms`, not only at
position 0. The Researcher legitimately emits multiple paradigms when a
topic spans them (e.g. "Q-learning trade-off" emits both
`reinforcement-learning` and `exploration-exploitation`). Paired with
`kg_growth_rate(Paradigm) ≤ 1.5/topic` as the brake, the metric can't be
gamed by slug-spamming.

`suite_assertions` is a new top-level field — runs after all topics finish.

#### D5 — `merge-quality.yaml` suite

```yaml
name: merge-quality
stages: []  # no pipeline runs
topics:
  - text: "merge-quality-fixture"
    expect:
      research:
        - merge_precision_recall:
            fixture: evals/fixtures/canonicalize-pairs.json
            min_precision: 0.95
            min_recall:    0.90
budget:
  max_usd_total: 1.50
```

Runs in <60s, costs ~$1. The tight loop for tuning A4/A5 thresholds.

#### D6 — Latency / speed metrics (NEW)

Three additions:

**D6a. `TimingLog`** in `eval/timing.py`:

```python
@dataclass
class StageTiming:
    stage: str          # "researcher" | "canonicalize" | "kg_writer" | ...
    started_at: float
    ended_at: float
    duration_ms: float

@dataclass
class ToolCallTiming:
    name: str
    started_at: float
    duration_ms: float

@dataclass
class TimingLog:
    stages: list[StageTiming]
    tool_calls: list[ToolCallTiming]
    wall_clock_ms: float
```

Hook into `runner._start_tool_call_recording` to capture every tool call's
duration. Hook into `Router._run_stage` to capture stage durations.

**D6b. Report fields** added to `report.json` per topic:

```json
"timing": {
  "wall_clock_ms": 142500,
  "stages": {"researcher": 89200, "canonicalize": 4100, "kg_writer": 1200},
  "retrieve_knowledge": {"calls": 4, "p50_ms": 320, "p95_ms": 1840},
  "_verify_merge":      {"calls": 6, "p50_ms": 950, "p95_ms": 2100}
}
```

Suite-level `timing_summary` aggregates these.

**D6c. Latency predicates:**

```python
@register("p95_below")
@register("avg_below")
async def _latency(ctx, args):
    # args: {tool: "retrieve_knowledge", p95_ms: 2500}
    # or:    {stage: "canonicalize", avg_ms: 6000}
```

Both `slug-accuracy.yaml` and `merge-quality.yaml` get latency assertions:

```yaml
- p95_below: { tool: retrieve_knowledge, p95_ms: 2500 }
- avg_below: { stage: canonicalize, avg_ms: 8000 }
```

This means Tracks A/B/C don't just have to improve accuracy — they have to
improve accuracy without regressing latency.

## Sequencing

```
Phase 0 — Eval foundations (build first, no LLM cost beyond ~$1)
    D6a TimingLog hooks
    D6b report fields
    D2  merge_precision_recall predicate
    D5  merge-quality.yaml suite
    Run baseline → record current precision/recall/F1/latency
    Commit baseline numbers as `evals/reports/2026-05-08-baseline-merge-quality/`

Phase 1 — Cheap Track A wins (~$2 of LLM)
    A2 reject empty slug_proposal
    A3 idempotent slugify + writer normalization
    Re-run merge-quality
    Expected: precision unchanged, recall +0.05 (idempotency closes some misses)

Phase 2 — Structural Track A wins (~$3)
    A1 list_known_slugs helper, drop _parse_known_slugs
    A4 ancestor expansion (Paradigm only)
    A5 per-label thresholds — ship hand-picked, then run
       scripts/calibrate_canonicalize_tau.py against the 18-pair
       fixture (no LLM cost), commit calibrated values
    Re-run merge-quality + new slug-accuracy.yaml
    Expected: slug hit rate 50% → 75-85%

Phase 3 — Track D online suite (~$10)
    D1 slug_hit_rate predicate
    D3 kg_growth_rate predicate
    D4 slug-accuracy.yaml
    Final calibration of thresholds against the online behavior

Phase 4 — Track B retrieval (~$5)
    B2 exclude_run_id Qdrant filter (free)
    B5 CRAG fail-closed (free)
    B6 post-CRAG window growth (free)
    Re-run slug-accuracy
    Then: B1 query rewriter, B3 ANN entity index, B4 typed PPR
    Expected: latency p95 -30%, slug hit rate +5pp

Phase 5 — Track C hygiene (~$3)
    C1 Variable composite keys (with migration)
    C4 Reflection MERGE
    C3 Qdrant prune sync
    C2 drop text_preview truncation
    C5 UNKNOWN → DUPLICATE under high cosine
    Validates against cumulative-growth.yaml — KG growth ≤ 30/topic.
```

Each phase commits its own `evals/reports/YYYY-MM-DD-<phase>/` so the
delta is auditable.

## Data flow changes

### Slug normalization invariant

After this refactor, every slug entering Neo4j MUST satisfy:

```
slug == slugify(slug)               # idempotent
match(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # only lowercase alnum + hyphen
2 <= len(slug) <= 80
not match(r"^[0-9a-f]{8}-...")      # not UUID-shaped (existing guard)
```

Enforced by `kg_writer._validate_natural_key` for `_SLUG_LIKE_LABELS`.

### Variable identity invariant

```
Variable.id = f"{paradigm_slug}:{normalized_name}"
```

Where `normalized_name = slugify(name)`. Cross-paradigm variables stay
separate; within-paradigm dedup still works via `:name` suffix.

### CRAG semantics

| Old | New |
|-----|-----|
| Haiku error → all CORRECT | Haiku error → all AMBIGUOUS, `grading_failed=True` |
| All INCORRECT, no web → drop all | All INCORRECT, no web → return with `low_confidence=True` |
| Mixed → keep CORRECT only | Mixed → keep CORRECT, web-supplement AMBIGUOUS |

## Testing plan

Per refactor:

- Unit tests for new helpers (`test_slug_idempotent.py`,
  `test_query_rewriter.py`, `test_ancestor_expansion.py`).
- Integration test for `list_known_slugs` against an in-memory KG fixture.
- `tests/eval/test_slug_hit_rate_predicate.py`,
  `test_merge_precision_recall_predicate.py`,
  `test_timing_log.py`.
- End-to-end: every phase ends with a full eval suite run + diff against
  the previous phase's report.

Existing tests must keep passing:
`pytest phase1-pablo/tests/knowledge/ phase1-pablo/tests/eval/ -x`.

## Cost envelope

| Phase | LLM cost | Wall clock |
|-------|----------|------------|
| 0     | ~$1      | 1-2 days |
| 1     | ~$2      | 1 day |
| 2     | ~$3      | 1-2 days |
| 3     | ~$10     | 1 day |
| 4     | ~$5      | 2 days |
| 5     | ~$3      | 1-2 days |
| **Total** | **~$24** | **~2 weeks part-time** |

## Risks

- **A4 ancestor expansion** depends on `BELONGS_TO`/`EXTENDS` edges
  existing in the KG. Current population pipeline emits some — we'll need
  to verify coverage on the cumulative-growth-seeded KG before trusting
  it. Mitigation: A4 falls back to direct match if no ancestors found.
- **B3 ANN entity index** requires backfill of existing KG; backfill
  script must run before B3 ships. Mitigation: keep the table-scan path
  as fallback if ANN returns 0 hits.
- **C1 Variable migration** is one-shot destructive; we need a `--dry-run`
  mode and a tested rollback. Mitigation: write migration as a Cypher
  script that runs in a transaction.
- **D6 timing overhead** must be negligible — use `time.monotonic_ns()`,
  not wall-clock formatting in hot paths.

## Decisions

1. **`slug_hit_rate` uses liberal matching.** The canonical slug counts
   as a hit if it appears anywhere in `result.paradigms`. Slug-spamming
   is bounded by `kg_growth_rate(Paradigm) ≤ 1.5/topic` (D3).
2. **No aggregate KG-growth target.** Replaced by per-label
   `kg_growth_rate` predicates. Paradigm growth is the slug-fragmentation
   signal; Variable inflation after C1 paradigm-scoping is expected and
   not a regression.
3. **Query rewriter (B1) feeds KG NER too.** The `keywords` field is
   prepended to the NER prompt as a hint. Cost is zero (rewrite already
   cached); quality lift is real on long queries.
4. **Per-label τ are hand-picked, then calibrated against the fixture
   using cached cosine scores only — no LLM gradient loop.** A new script
   `scripts/calibrate_canonicalize_tau.py` sweeps τ ∈ [0.70, 0.95] in
   0.01 steps, picks the F1 maximum (tie-break toward precision), and
   emits new `LABEL_THRESHOLDS` values. The LLM verifier on top catches
   the gray zone, so τ doesn't need to be perfect on its own.

## Success criteria (final)

| Metric | Baseline (2026-05-07) | Post-A2/A3/A4/A5 (2026-05-08, `slug-accuracy.yaml`) | Target |
|--------|-----------------------|------------------------------------------------------|--------|
| Slug reuse rate (`slug-accuracy.yaml`)            | ~50%       | **0.875** (7/8, threshold=0.80) ✓ | ≥ 80% |
| Merge precision (`merge-quality.yaml`)            | 1.000 (2026-05-08, n=18; tp=3 fp=0 fn=7 tn=8) | — (offline; not re-run in Phase 3) | ≥ 0.95 |
| Merge recall  (`merge-quality.yaml`)              | 0.300 (2026-05-08, n=18; f1=0.462) | — (offline; not re-run in Phase 3) | ≥ 0.90 |
| KG Paradigm  growth/topic (`cumulative-growth.yaml`) | ~6      | **1.62** (Δ=+13, n=8) ✗ | ≤ 1.5 |
| KG Variable  growth/topic (`cumulative-growth.yaml`) | ~9      | **7.62** (Δ=+61, n=8) ✗ | ≤ 6 |
| KG Postulate growth/topic (`cumulative-growth.yaml`) | ~7      | **7.75** (Δ=+62, n=8) ✗ | ≤ 5 |
| `retrieve_knowledge` p95                          | unmeasured | **19789 ms** ✗ | ≤ 2.5s |
| `canonicalize` avg                                | unmeasured | no data (stage not top-level in Phase 3 suite) | ≤ 8s |

Phase 3 baseline report: `evals/reports/2026-05-08-phase3-slug-accuracy/`. Suite cost $6.23, KG growth +515 nodes / +197 relations across 8 topics. The single slug miss was on "bounded-rationality" (fragmented to `fast-and-frugal-heuristics-adaptive-toolbox`, `optimal-stopping-secretary-problem`, `satisficing-and-aspiration-level-adaptation`) — Paradigm growth/topic and per-paradigm fragmentation are the two follow-ups for Phase 4/5.

All numbers emitted to `report.json`. Pass/fail surfaces in `report.md`.

