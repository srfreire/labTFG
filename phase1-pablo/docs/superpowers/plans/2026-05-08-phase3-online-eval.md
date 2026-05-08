# Phase 3 — Online Eval Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the slug-oracle fixture, the `slug_hit_rate` and `kg_growth_rate` suite predicates, and the `slug-accuracy.yaml` end-to-end suite. Run the baseline against the current Phase 2 codebase to capture the post-A2/A3/A4/A5 numbers.

**Architecture:** A fixture file maps topic text → expected canonical slug; `slug_hit_rate` matches each topic in `topic_results` to an oracle entry by sha1 of normalized text and asks "did the canonical slug appear anywhere in `result.paradigms`?" (liberal matching, per spec decision 1). `kg_growth_rate` uses the per-label deltas already captured by `pre_stats`/`post_stats` on `SuiteAssertionContext`. The new suite re-uses the 4 paradigm-canonicalization topics + 4 deliberately fragmenting variants designed to tease apart canonical slug reuse from minting.

**Tech Stack:** Python 3.12, `pytest`, `pyyaml`.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Track D items D1, D3, D4.

**Depends on:** Phase 0 (suite_assertions plumbing). Doesn't strictly require Phase 1/2 to be done — can run against any state to capture a baseline; but the most useful comparison is Phase 2 → final.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `phase1-pablo/evals/fixtures/slug-oracle.json` | **new** | Topic-text → expected canonical slug map (8 entries) |
| `phase1-pablo/src/decisionlab/eval/assertions.py` | modify | `slug_hit_rate` (suite predicate) + `kg_growth_rate` (suite predicate) |
| `phase1-pablo/evals/suites/slug-accuracy.yaml` | **new** | 8-topic online suite |
| `phase1-pablo/tests/eval/test_assertions_slug_hit.py` | **new** | Tests for `slug_hit_rate` |
| `phase1-pablo/tests/eval/test_assertions_kg_growth.py` | **new** | Tests for `kg_growth_rate` |

---

## Task 1: `slug-oracle.json` fixture

**Files:**
- Create: `phase1-pablo/evals/fixtures/slug-oracle.json`

- [ ] **Step 1: Author the fixture**

```json
[
  {
    "topic_text": "Q-learning agent trades off exploration and exploitation in a foraging grid: how do action-value updates and ε-greedy schedules drive the policy toward optimal patch choice?",
    "expected_slug": "reinforcement-learning",
    "_doc": "RL umbrella — Q-learning is a child"
  },
  {
    "topic_text": "Why do people overweight losses relative to gains in financial decisions, and how does the value function curve below the reference point predict observed risk-seeking in the loss domain?",
    "expected_slug": "prospect-theory",
    "_doc": "Loss aversion is prospect theory"
  },
  {
    "topic_text": "Speed-accuracy tradeoff in two-alternative forced-choice tasks: how does a noisy evidence-accumulation process to bound a reaction-time distribution and a choice probability?",
    "expected_slug": "drift-diffusion-model",
    "_doc": "Mechanism description — DDM"
  },
  {
    "topic_text": "Bounded rationality and satisficing heuristics: when do agents stop searching once a good-enough alternative is found?",
    "expected_slug": "bounded-rationality",
    "_doc": "Direct match"
  },
  {
    "topic_text": "Q-learning policy variant with eligibility traces — how does TD(λ) blend Monte-Carlo and one-step bootstrapping?",
    "expected_slug": "reinforcement-learning",
    "_doc": "Fragmenting variant — should NOT mint a new q-learning-traces slug"
  },
  {
    "topic_text": "Drift-diffusion model with collapsing decision bounds: time-pressured perceptual choice in foraging contexts",
    "expected_slug": "drift-diffusion-model",
    "_doc": "Fragmenting variant — should NOT mint a new ddm-collapsing-bounds slug"
  },
  {
    "topic_text": "Reference-dependent valuation in financial gambles — how does the reference point shape risk-seeking under losses?",
    "expected_slug": "prospect-theory",
    "_doc": "Phrasing variant of loss aversion"
  },
  {
    "topic_text": "Free-energy principle as a unifying framework for perception, action, and learning in active inference agents",
    "expected_slug": "free-energy-principle",
    "_doc": "Direct match — must reuse the canonical slug"
  }
]
```

- [ ] **Step 2: Validate JSON**

```bash
uv run python -c "import json; pairs = json.loads(open('phase1-pablo/evals/fixtures/slug-oracle.json').read()); print(len(pairs), 'topics'); assert all('topic_text' in p and 'expected_slug' in p for p in pairs)"
```

Expected: `8 topics`.

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/evals/fixtures/slug-oracle.json
git commit -m "feat[phase1-eval]: slug-oracle.json fixture (8 topics)"
```

---

## Task 2: `slug_hit_rate` predicate

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/assertions.py`
- Test: `phase1-pablo/tests/eval/test_assertions_slug_hit.py` (new)

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/eval/test_assertions_slug_hit.py
"""slug_hit_rate: sum hits across topics, fail if rate below min_rate.
Liberal matching — canonical slug counts if it appears anywhere in
result.paradigms (not just position 0)."""

import json

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import TopicResult


def _tr(topic_text: str, paradigms: tuple[str, ...]) -> TopicResult:
    run = PipelineRunResult(
        run_id="r",
        topic=topic_text,
        stages_run=("research",),
        paradigms=paradigms,
    )
    return TopicResult(topic=topic_text, run=run, assertions={})


@pytest.fixture()
def fixture_path(tmp_path):
    pairs = [
        {"topic_text": "RL question",      "expected_slug": "reinforcement-learning"},
        {"topic_text": "loss aversion ?",  "expected_slug": "prospect-theory"},
        {"topic_text": "DDM speed acc",    "expected_slug": "drift-diffusion-model"},
        {"topic_text": "free energy ?",    "expected_slug": "free-energy-principle"},
    ]
    p = tmp_path / "oracle.json"
    p.write_text(json.dumps(pairs))
    return p


@pytest.mark.asyncio
async def test_slug_hit_rate_passes_on_full_hits(fixture_path):
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question",     ("reinforcement-learning",)),
            _tr("loss aversion ?", ("prospect-theory", "regret")),
            _tr("DDM speed acc",   ("drift-diffusion-model",)),
            _tr("free energy ?",   ("free-energy-principle", "active-inference")),
        ),
        pre_stats=None, post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 0.8}}, ctx
    )
    assert out.passed, out.detail
    assert "4/4" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_liberal_match_counts_position_n(fixture_path):
    """The canonical slug appears at position 1, not 0 — still a hit."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question", ("exploration-exploitation", "reinforcement-learning")),
        ),
        pre_stats=None, post_stats=None,
    )
    # min_rate=1.0 forces strict pass on this single-topic context
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 1.0}}, ctx
    )
    # only matched 1 of the 4 oracle topics, but that 1 was a liberal hit
    # — the predicate matches by topic_text, so the others are simply absent
    # from this context. Detail should show 1/1.
    assert "1/1" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_fails_below_threshold(fixture_path):
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question",     ("reinforcement-learning",)),  # hit
            _tr("loss aversion ?", ("regret-theory",)),           # miss
            _tr("DDM speed acc",   ("drift-diffusion-model",)),   # hit
            _tr("free energy ?",   ("predictive-coding",)),       # miss
        ),
        pre_stats=None, post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 0.8}}, ctx
    )
    assert not out.passed
    assert "2/4" in out.detail or "0.500" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_topic_not_in_oracle_skipped(fixture_path):
    """Topics not present in the oracle are not penalized; they're just
    not counted toward the denominator."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question",     ("reinforcement-learning",)),
            _tr("unrelated topic", ("something",)),  # not in oracle
        ),
        pre_stats=None, post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 1.0}}, ctx
    )
    assert "1/1" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_missing_oracle_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": "/nonexistent.json", "min_rate": 0.8}}, ctx
    )
    assert not out.passed
    assert "oracle" in out.detail.lower()
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/eval/test_assertions_slug_hit.py -v
```

Expected: `unknown suite predicate 'slug_hit_rate'`.

- [ ] **Step 3: Implement the predicate**

Append to `phase1-pablo/src/decisionlab/eval/assertions.py`:

```python
import hashlib as _hashlib


def _normalize_topic_for_match(text: str) -> str:
    """Identity-style hash for matching topic text → oracle entry. Robust
    to whitespace differences."""
    cleaned = " ".join(text.split())
    return _hashlib.sha1(cleaned.encode("utf-8")).hexdigest()


@register_suite("slug_hit_rate")
async def _slug_hit_rate(
    ctx: SuiteAssertionContext, args
) -> AssertionOutcome:
    """For each topic in topic_results, look up its oracle entry by
    text hash; count hit if expected_slug appears anywhere in
    result.paradigms (liberal matching). Pass iff hits/total >= min_rate.

    args: {oracle: path, min_rate: 0.8}
    Topics not present in the oracle are skipped (don't count toward
    denominator).
    """
    oracle_path = _Path(args["oracle"])
    if not oracle_path.exists():
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail=f"oracle not found: {oracle_path}",
        )
    min_rate = float(args.get("min_rate", 0.8))
    try:
        oracle = _json.loads(oracle_path.read_text())
    except _json.JSONDecodeError as exc:
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail=f"oracle not valid JSON: {exc}",
        )

    by_hash = {
        _normalize_topic_for_match(p["topic_text"]): p["expected_slug"]
        for p in oracle
    }

    hits = 0
    total = 0
    misses: list[str] = []
    for tr in ctx.topic_results:
        h = _normalize_topic_for_match(tr.topic)
        expected = by_hash.get(h)
        if expected is None:
            continue  # topic not in oracle; skip
        total += 1
        if expected in tr.run.paradigms:
            hits += 1
        else:
            misses.append(f"{expected!r} not in {list(tr.run.paradigms)!r}")

    if total == 0:
        return AssertionOutcome(
            name="slug_hit_rate",
            passed=False,
            detail="no topic_results matched the oracle",
        )
    rate = hits / total
    detail = f"{hits}/{total} = {rate:.3f}, threshold={min_rate:.2f}"
    if misses:
        detail += "; misses: " + "; ".join(misses[:3])
        if len(misses) > 3:
            detail += f" (+{len(misses) - 3} more)"
    return AssertionOutcome(
        name="slug_hit_rate", passed=rate >= min_rate, detail=detail
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/eval/test_assertions_slug_hit.py -v
```

Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/assertions.py phase1-pablo/tests/eval/test_assertions_slug_hit.py
git commit -m "feat[phase1-eval]: slug_hit_rate suite predicate (liberal matching)"
```

---

## Task 3: `kg_growth_rate` predicate

**Files:**
- Modify: `phase1-pablo/src/decisionlab/eval/assertions.py`
- Test: `phase1-pablo/tests/eval/test_assertions_kg_growth.py` (new)

- [ ] **Step 1: Inspect KGStats shape**

```bash
grep -n "class KGStats\|by_label\|total_nodes" phase1-pablo/src/decisionlab/eval/kgadmin.py | head -20
```

Confirm `KGStats` has a `by_label: dict[str, int]` field (or equivalent). Adapt the test fixture if the field name differs.

- [ ] **Step 2: Failing test**

```python
# phase1-pablo/tests/eval/test_assertions_kg_growth.py
"""kg_growth_rate: per-label delta divided by topic count, fail above
max_per_topic. Pre/post stats come in via SuiteAssertionContext."""

from dataclasses import dataclass, field

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import TopicResult


@dataclass(frozen=True)
class _FakeStats:
    by_label: dict[str, int] = field(default_factory=dict)


def _tr(topic):
    return TopicResult(topic=topic, run=PipelineRunResult(
        run_id="r", topic=topic, stages_run=("research",)
    ), assertions={})


@pytest.mark.asyncio
async def test_kg_growth_rate_under_threshold_passes():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"), _tr("b"), _tr("c"), _tr("d")),  # 4 topics
        pre_stats=_FakeStats(by_label={"Paradigm": 10}),
        post_stats=_FakeStats(by_label={"Paradigm": 14}),  # +4 / 4 = 1.0
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Paradigm", "max_per_topic": 1.5}}, ctx
    )
    assert out.passed, out.detail
    assert "1.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_over_threshold_fails():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"), _tr("b")),  # 2 topics
        pre_stats=_FakeStats(by_label={"Variable": 5}),
        post_stats=_FakeStats(by_label={"Variable": 25}),  # +20 / 2 = 10.0
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Variable", "max_per_topic": 6}}, ctx
    )
    assert not out.passed
    assert "10.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_unknown_label_treated_as_zero():
    """If the label has no entry pre or post, growth = 0 — passes."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"),),
        pre_stats=_FakeStats(by_label={}),
        post_stats=_FakeStats(by_label={}),
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Phantom", "max_per_topic": 0.5}}, ctx
    )
    assert out.passed
    assert "0.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_no_stats_fails_visibly():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"),),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Paradigm", "max_per_topic": 1.5}}, ctx
    )
    assert not out.passed
    assert "stats" in out.detail.lower()
```

- [ ] **Step 3: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/eval/test_assertions_kg_growth.py -v
```

Expected: `unknown suite predicate 'kg_growth_rate'`.

- [ ] **Step 4: Implement**

Append to `phase1-pablo/src/decisionlab/eval/assertions.py`:

```python
@register_suite("kg_growth_rate")
async def _kg_growth_rate(
    ctx: SuiteAssertionContext, args
) -> AssertionOutcome:
    """Per-label growth rate (post - pre) / n_topics. Passes iff
    rate <= max_per_topic.

    args: {label: "Paradigm", max_per_topic: 1.5}
    """
    label = args["label"]
    max_per_topic = float(args["max_per_topic"])
    if ctx.pre_stats is None or ctx.post_stats is None:
        return AssertionOutcome(
            name="kg_growth_rate",
            passed=False,
            detail=f"missing pre/post stats — cannot compute growth for {label}",
        )
    n_topics = max(1, len(ctx.topic_results))
    pre_n = ctx.pre_stats.by_label.get(label, 0)
    post_n = ctx.post_stats.by_label.get(label, 0)
    delta = post_n - pre_n
    rate = delta / n_topics
    return AssertionOutcome(
        name="kg_growth_rate",
        passed=rate <= max_per_topic,
        detail=(
            f"{label}: pre={pre_n} post={post_n} Δ={delta:+d} "
            f"n={n_topics} rate={rate:.2f}/topic max={max_per_topic:.2f}"
        ),
    )
```

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/eval/test_assertions_kg_growth.py -v
```

Expected: PASS (4/4).

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/eval/assertions.py phase1-pablo/tests/eval/test_assertions_kg_growth.py
git commit -m "feat[phase1-eval]: kg_growth_rate suite predicate"
```

---

## Task 4: `slug-accuracy.yaml` suite

**Files:**
- Create: `phase1-pablo/evals/suites/slug-accuracy.yaml`

- [ ] **Step 1: Author the suite**

```yaml
# phase1-pablo/evals/suites/slug-accuracy.yaml
# Online slug-accuracy regression — exercises the full Researcher
# pipeline against the slug-oracle.json fixture and bounds per-label
# KG growth.
#
# Pre-condition: KG seeded by cumulative-growth.yaml first (so the
# canonical paradigms exist and can be reused, not minted).
#
# Cost: 8 topics × research-stage ~$1.20/topic ≈ $10.

name: slug-accuracy
stages: [research]
reset_kg_before: false

topics:
  - text: "Q-learning agent trades off exploration and exploitation in a foraging grid: how do action-value updates and ε-greedy schedules drive the policy toward optimal patch choice?"
    expect:
      research:
        - tool_called: { name: retrieve_knowledge, min: 1 }
        - paradigm: reinforcement-learning

  - text: "Why do people overweight losses relative to gains in financial decisions, and how does the value function curve below the reference point predict observed risk-seeking in the loss domain?"
    expect:
      research:
        - tool_called: { name: retrieve_knowledge, min: 1 }
        - paradigm: prospect-theory

  - text: "Speed-accuracy tradeoff in two-alternative forced-choice tasks: how does a noisy evidence-accumulation process to bound a reaction-time distribution and a choice probability?"
    expect:
      research:
        - tool_called: { name: retrieve_knowledge, min: 1 }
        - paradigm: drift-diffusion-model

  - text: "Bounded rationality and satisficing heuristics: when do agents stop searching once a good-enough alternative is found?"
    expect:
      research:
        - paradigm: bounded-rationality

  - text: "Q-learning policy variant with eligibility traces — how does TD(λ) blend Monte-Carlo and one-step bootstrapping?"
    expect:
      research:
        - paradigm: reinforcement-learning  # MUST canonicalize, not mint q-learning-traces

  - text: "Drift-diffusion model with collapsing decision bounds: time-pressured perceptual choice in foraging contexts"
    expect:
      research:
        - paradigm: drift-diffusion-model  # MUST canonicalize

  - text: "Reference-dependent valuation in financial gambles — how does the reference point shape risk-seeking under losses?"
    expect:
      research:
        - paradigm: prospect-theory

  - text: "Free-energy principle as a unifying framework for perception, action, and learning in active inference agents"
    expect:
      research:
        - paradigm: free-energy-principle

suite_assertions:
  - slug_hit_rate:
      oracle: evals/fixtures/slug-oracle.json
      min_rate: 0.80
  - kg_growth_rate: { label: Paradigm,  max_per_topic: 1.5 }
  - kg_growth_rate: { label: Variable,  max_per_topic: 6   }
  - kg_growth_rate: { label: Postulate, max_per_topic: 5   }
  - p95_below: { tool: retrieve_knowledge, p95_ms: 2500 }
  - avg_below: { stage: canonicalize,      avg_ms: 8000 }

budget:
  max_usd_total: 12.00
```

- [ ] **Step 2: Lint via SuiteSpec parser**

```bash
cd phase1-pablo
uv run python -c "
from pathlib import Path
from decisionlab.eval.suite import SuiteSpec
spec = SuiteSpec.from_yaml(Path('evals/suites/slug-accuracy.yaml'))
print('topics:', len(spec.topics))
print('suite_assertions:', len(spec.suite_assertions))
"
```

Expected: `topics: 8`, `suite_assertions: 6`.

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/evals/suites/slug-accuracy.yaml
git commit -m "feat[phase1-eval]: slug-accuracy.yaml online suite (8 topics)"
```

---

## Task 5: Run baseline + record numbers

**Files:**
- Output: `phase1-pablo/evals/reports/2026-05-08-phase3-slug-accuracy/`

- [ ] **Step 1: Pre-seed the KG**

```bash
cd phase1-pablo
uv run python -m decisionlab.cli eval run evals/suites/cumulative-growth.yaml
```

Expected: 5 topics, ~$10, populates KG with the canonical paradigms.

- [ ] **Step 2: Run slug-accuracy**

```bash
uv run python -m decisionlab.cli eval run evals/suites/slug-accuracy.yaml
LAST=$(ls -t evals/reports/ | head -1)
mv "evals/reports/${LAST}" evals/reports/2026-05-08-phase3-slug-accuracy
```

- [ ] **Step 3: Read the numbers**

```bash
cat phase1-pablo/evals/reports/2026-05-08-phase3-slug-accuracy/report.md
```

Look for the **Suite assertions** table — note `slug_hit_rate`, `kg_growth_rate(Paradigm)`, `p95_below(retrieve_knowledge)`, `avg_below(canonicalize)`.

- [ ] **Step 4: Update spec success-criteria table**

Open `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md`, locate the **Success criteria (final)** table, and fill in the baseline column with the actual numbers from Step 3.

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/evals/reports/2026-05-08-phase3-slug-accuracy/ phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md
git commit -m "feat[phase1-eval]: phase 3 slug-accuracy baseline report"
```

---

## Task 6: Final regression sweep

- [ ] **Step 1: Format + lint**

```bash
cd phase1-pablo && uv run ruff format --check . && uv run ruff check .
```

- [ ] **Step 2: Test sweep**

```bash
cd phase1-pablo && uv run pytest tests/eval -x
```

Expected: PASS.

---

## Self-Review

| Spec deliverable (Phase 3) | Implemented in |
|----------------------------|----------------|
| D1 slug_hit_rate predicate | Task 2 |
| D3 kg_growth_rate predicate | Task 3 |
| D4 slug-accuracy.yaml suite | Task 4 |
| Baseline numbers recorded | Task 5 |

**Placeholder check:** No "TBD". Step 4 of Task 5 expects engineer-completed values — those are eval outputs, not placeholders.

**Type consistency:** `slug_hit_rate` and `kg_growth_rate` are both registered with `@register_suite`. Both consume `SuiteAssertionContext` from Phase 0. Oracle fixture shape matches the predicate's `topic_text/expected_slug` keys throughout.

