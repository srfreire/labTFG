# retrieve_knowledge underuse diagnosis (Issue 2)

## Symptom

Slug-accuracy eval (8 topics, 2026-05-09): `retrieve_knowledge` was called 1 time
total. The eval predicate `tool_called: retrieve_knowledge, min: 1` per topic
failed on 7 of 8 topics. The entire P4 retrieval stack (CRAG, recency weighting,
hybrid dense+sparse+KG, zerank-2 reranker) was idle.

## Hypotheses considered

1. **Tool ordering bias** — `retrieve_knowledge` was registered last in
   `self.tools`. Agents tend to default to earlier-listed tools.
2. **System prompt suppression** — the prompt directs the model away from
   retrieval.
3. **Empty-KG short-circuit** — `reset_kg_before: true` in slug-accuracy means
   the KG starts with only the 10 seeded canonical Paradigms; the model "learns"
   retrieval returns nothing useful and stops calling it.

## Verified root cause: hypothesis 2

Reading `RESEARCHER_SYSTEM_PROMPT` (pre-fix) showed an explicit cap and a narrow
allowed use:

> You may call `retrieve_knowledge` AT MOST 2 TIMES TOTAL across the whole run.
> Use it ONLY to look up the definition of a CANDIDATE paradigm listed in the
> user message when the candidate is loosely related to the topic and you need
> its definition to decide whether to reuse its slug.

But candidate definitions are ALREADY embedded in the user message by
`_retrieve_known_paradigms` → `_format_candidates(known_slugs, retrieval_text)`.
So the documented use-case is empty: the model has the definitions inline and
the prompt forbids broader use. The 1 call observed across 8 topics is
consistent with the model occasionally testing the tool against the prompt's
narrow framing.

Hypothesis 1 (ordering) is real but secondary. Hypothesis 3 was untestable
without first fixing 2 — the model never reaches the point of seeing an empty
result.

## Fix shipped

`RESEARCHER_SYSTEM_PROMPT`:

- Made one `retrieve_knowledge` call **mandatory at the start of the run**,
  before any web_search/launch_deep_research, scoped to "find related entities
  (Variables, Postulates, Reflections, Papers) for this topic".
- Lifted the cap from 2 to 3 total (1 mandatory + 2 follow-up).
- Removed the "only for candidate definitions" restriction.
- Reordered the `## Process` steps so step 2 is now the mandatory
  `retrieve_knowledge` call; subsequent steps (web_search, launch_deep_research,
  read_report, summary writing) renumbered accordingly.

The `_retrieve_known_paradigms` programmatic call is unchanged — it remains the
source of truth for candidate slugs (load-bearing for `slug_hit_rate`).

## Expected behavior change

- Per-topic `retrieve_knowledge` count rises from ≈0.125 (1/8) to ≥1.
- `tool_called: retrieve_knowledge, min: 1` predicate passes on every topic.
- The CRAG/recency/hybrid retrieval branches finally get exercised in
  production-like conditions.
- p95 latency observed in slug-accuracy was 5294ms on n=1; with n≥8 the metric
  becomes meaningful (sample-size-1 caveat from architecture report §4.4
  dissolves).

## Risks

- Mandatory tool-use can increase latency by ~5s/topic (one extra call).
  Acceptable for an eval.
- An empty/sparse KG (slug-accuracy resets) means the first call returns little.
  The model may dismiss subsequent calls. Mitigated by capping mandatory-ness at
  one call (after which the model can choose).
- Cost increase per topic: +1 retrieve_knowledge call ≈ +$0.01 (Haiku NER +
  rewriter + small embedding ops). Negligible vs $0.73/topic baseline.
