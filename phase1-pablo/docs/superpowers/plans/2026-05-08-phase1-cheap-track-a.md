# Phase 1 — Cheap Track A Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the silent slug-collision bugs (empty `slug_proposal` collapsing to `"paradigm"`, non-idempotent `slugify`) and make slug normalization the writer's responsibility, validated by re-running the Phase 0 merge-quality baseline.

**Architecture:** Two narrow code changes — `_slug_from_proposal` rejects empty proposals deterministically (sha1-suffix fallback), and `slugify` is rewritten to be idempotent under unicode normalization. Defensive normalization at the writer (`kg_writer._validate_natural_key`) catches any LLM-supplied slug that bypassed the producer-side checks.

**Tech Stack:** Python 3.12, `pytest`, `unicodedata`, `hashlib`.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Track A items A2, A3.

**Depends on:** Phase 0 plan (`merge-quality.yaml` baseline must exist).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `phase1-pablo/src/decisionlab/tools/reports.py` | modify | Replace `slugify` with idempotent unicode-aware version |
| `phase1-pablo/src/decisionlab/agents/researcher.py` | modify | `_slug_from_proposal` accepts `definition`; deterministic fallback |
| `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` | modify | `_validate_natural_key` re-normalizes via `slugify` for slug-like labels |
| `phase1-pablo/tests/tools/test_slugify.py` | **new** | Idempotency property tests + unicode/punctuation cases |
| `phase1-pablo/tests/agents/test_slug_from_proposal.py` | **new** | Empty-proposal fallback test |
| `phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py` | **new** | Writer-level renormalization test |

---

## Task 1: Failing tests for the new `slugify` contract

**Files:**
- Create: `phase1-pablo/tests/tools/test_slugify.py`

- [ ] **Step 1: Write the failing tests**

```python
# phase1-pablo/tests/tools/test_slugify.py
"""slugify must be idempotent and produce only [a-z0-9-] tokens."""

import re

import pytest

from decisionlab.tools.reports import slugify


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Reinforcement Learning", "reinforcement-learning"),
        ("Drift-diffusion model (DDM)", "drift-diffusion-model-ddm"),
        ("q_learning", "q-learning"),
        ("Q-Learning  ", "q-learning"),
        ("Bayesian   Inference", "bayesian-inference"),
        ("Naïve Bayes", "naive-bayes"),
        ("free-energy / variational", "free-energy-variational"),
        ("model: prospect theory", "model-prospect-theory"),
        ("---multiple---dashes---", "multiple-dashes"),
        ("a.b.c", "a-b-c"),
    ],
)
def test_slugify_canonical_forms(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Reinforcement Learning",
        "Drift-diffusion model (DDM)",
        "Naïve Bayes",
        "model: prospect theory",
        "q_learning",
        "free-energy / variational",
    ],
)
def test_slugify_idempotent(raw):
    once = slugify(raw)
    twice = slugify(once)
    assert once == twice, f"slugify not idempotent: {once!r} -> {twice!r}"


def test_slugify_only_safe_chars():
    s = slugify("ÁÉÍÓÚáéíóú !@#$%^&*() Free Energy 2.0")
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s), f"unsafe chars in {s!r}"


def test_slugify_empty_input_returns_empty():
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("@@@") == ""
```

- [ ] **Step 2: Run, verify it fails**

```bash
uv run pytest phase1-pablo/tests/tools/test_slugify.py -v
```

Expected: failures on `(DDM)` parens, `Naïve` accent, `q_learning` underscore.

- [ ] **Step 3: Replace `slugify`**

In `phase1-pablo/src/decisionlab/tools/reports.py:34-37`:

```python
import re
import unicodedata


def slugify(name: str) -> str:
    """Idempotent kebab-case slug for paradigm/variable/postulate keys.

    Steps:
      1. Unicode-normalize and strip diacritics (NFKD + ASCII filter).
      2. Lowercase.
      3. Collapse any run of non-alphanumeric characters into a single '-'.
      4. Strip leading/trailing '-'.

    The collapse-runs rule is what makes the function idempotent: once the
    output is restricted to ``[a-z0-9-]+`` with no leading/trailing/consecutive
    hyphens, applying the same transformation again produces the same string.
    """
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    return hyphenated.strip("-")
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/tools/test_slugify.py -v
```

Expected: all PASS.

- [ ] **Step 5: Sanity-check existing slugify callers**

```bash
grep -rn "from decisionlab.tools.reports import slugify\|reports.slugify" phase1-pablo/src/ phase1-pablo/tests/
```

For each call site, verify the new behaviour is acceptable (i.e. callers are not asserting on the old "keep parentheses" output). Run the affected test files individually if any look brittle.

- [ ] **Step 6: Run full test sweep on affected modules**

```bash
uv run pytest phase1-pablo/tests/tools phase1-pablo/tests/agents phase1-pablo/tests/knowledge -x
```

Expected: PASS. Any failures here mean a downstream test was relying on the old slugify shape — fix the test, not the slugify.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/tools/reports.py phase1-pablo/tests/tools/test_slugify.py
git commit -m "fix[phase1-tools]: idempotent unicode-aware slugify"
```

---

## Task 2: Failing test for `_slug_from_proposal` empty fallback

**Files:**
- Create: `phase1-pablo/tests/agents/test_slug_from_proposal.py`

- [ ] **Step 1: Write the failing tests**

```python
# phase1-pablo/tests/agents/test_slug_from_proposal.py
"""When the LLM emits __NEW__ but slug_proposal is empty, the fallback
must NOT collapse to a literal "paradigm" (which would silently merge
unrelated paradigms in Neo4j). Use a deterministic sha1 of the
definition so two distinct paradigms with empty proposals stay
distinct."""

from decisionlab.agents.researcher import _slug_from_proposal


def test_nonempty_proposal_runs_slugify():
    assert _slug_from_proposal("Reinforcement Learning") == "reinforcement-learning"


def test_empty_proposal_uses_definition_hash():
    s = _slug_from_proposal("", definition="A model of value-based action selection ...")
    assert s.startswith("unnamed-")
    assert len(s) >= len("unnamed-") + 6


def test_empty_proposal_distinct_for_distinct_definitions():
    a = _slug_from_proposal("", definition="Variational free-energy minimization")
    b = _slug_from_proposal("", definition="Drift-diffusion evidence accumulation")
    assert a != b


def test_empty_proposal_no_definition_raises():
    """Accept this guardrail: if both proposal AND definition are empty,
    we have no idea what paradigm this is. Refuse rather than silently
    minting a colliding slug."""
    import pytest

    with pytest.raises(ValueError, match="empty"):
        _slug_from_proposal("", definition="")
```

- [ ] **Step 2: Run, verify it fails**

```bash
uv run pytest phase1-pablo/tests/agents/test_slug_from_proposal.py -v
```

Expected: failures — current signature is `_slug_from_proposal(name)` (no `definition` kwarg); current empty path returns `"paradigm"`.

- [ ] **Step 3: Update `_slug_from_proposal`**

In `phase1-pablo/src/decisionlab/agents/researcher.py:196-198`, replace:

```python
import hashlib


def _slug_from_proposal(name: str, *, definition: str = "") -> str:
    """Turn a free-form paradigm name into a kebab-case slug.

    On empty ``name``, derives a deterministic short hash from the
    definition so two unrelated paradigms with empty proposals don't
    collide on a single sentinel slug. Refuses when both are empty —
    we have no signal to disambiguate from.
    """
    s = slugify(name)
    if s:
        return s
    if not definition.strip():
        raise ValueError(
            "_slug_from_proposal: both name and definition empty; cannot mint slug"
        )
    digest = hashlib.sha1(definition.strip()[:128].encode("utf-8")).hexdigest()[:10]
    return f"unnamed-{digest}"
```

- [ ] **Step 4: Update the caller**

In the same file, find the `__NEW__` branch in `_emit_structured` (around `researcher.py:431-433`). Currently:

```python
if slug == "__NEW__":
    proposal = emission.slug_proposal or ""
    slug = _slug_from_proposal(proposal) if proposal else "paradigm"
```

Replace with:

```python
if slug == "__NEW__":
    proposal = emission.slug_proposal or ""
    slug = _slug_from_proposal(proposal, definition=emission.definition)
```

The `emission.definition` field already exists in `ParadigmEmission` (`researcher.py:185`).

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/agents/test_slug_from_proposal.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the wider agents/researcher suite**

```bash
uv run pytest phase1-pablo/tests/agents -x
```

Expected: PASS. If a test stub passes a `_slug_from_proposal(name)` without `definition`, update that test to pass a definition (or to use the new ValueError path).

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/agents/researcher.py phase1-pablo/tests/agents/test_slug_from_proposal.py
git commit -m "fix[phase1-research]: deterministic fallback for empty slug_proposal"
```

---

## Task 3: Writer-level slug renormalization

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/kg_writer.py:56-83`
- Test: `phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py
"""Defense-in-depth: any slug-like natural key entering kg_writer
gets re-normalized through slugify. Catches LLM emissions that
bypassed the producer-side normalization."""

import pytest

from decisionlab.knowledge.kg_writer import _validate_natural_key


def test_slug_like_label_gets_renormalized():
    ok, value, err = _validate_natural_key(
        label="Paradigm", key_name="slug", key_value="Reinforcement Learning"
    )
    assert ok, err
    assert value == "reinforcement-learning"


def test_slug_already_canonical_passes_through():
    ok, value, err = _validate_natural_key(
        label="Paradigm", key_name="slug", key_value="prospect-theory"
    )
    assert ok
    assert value == "prospect-theory"


def test_uuid_shaped_slug_still_rejected():
    ok, value, err = _validate_natural_key(
        label="Paradigm",
        key_name="slug",
        key_value="a6744d26-4c5d-4e3f-9b8a-1f2c3d4e5f60",
    )
    assert not ok
    assert "uuid" in err.lower() or "natural key" in err.lower()


def test_non_slug_label_unchanged():
    """Author.name shouldn't be slugified — it's a human-readable name."""
    ok, value, err = _validate_natural_key(
        label="Author", key_name="name", key_value="Daniel Kahneman"
    )
    assert ok
    assert value == "Daniel Kahneman"
```

- [ ] **Step 2: Run, verify it fails**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py -v
```

Expected: `test_slug_like_label_gets_renormalized` fails (current behaviour passes the key through verbatim).

- [ ] **Step 3: Locate `_SLUG_LIKE_LABELS` and `_validate_natural_key`**

```bash
grep -n "_SLUG_LIKE_LABELS\|def _validate_natural_key" phase1-pablo/src/decisionlab/knowledge/kg_writer.py
```

Confirm the labels set and the function signature. The function returns a 3-tuple `(ok, value, err)`.

- [ ] **Step 4: Add normalization**

Modify `_validate_natural_key`. After the UUID/length checks succeed, before returning ok, add a slugify pass for slug-like labels:

```python
from decisionlab.tools.reports import slugify  # at top of module


def _validate_natural_key(*, label, key_name, key_value):
    # ... existing UUID-shape and length guards unchanged ...

    if label in _SLUG_LIKE_LABELS:
        # Defense-in-depth: even if the producer misses normalization
        # (Researcher, extraction, canonicalize), the writer is the
        # last line. Empty after slugify is a hard reject — caller
        # must supply a non-empty key.
        normalized = slugify(str(key_value))
        if not normalized:
            return (False, key_value, f"slug normalized to empty: {key_value!r}")
        return (True, normalized, None)

    return (True, key_value, None)
```

(Adapt to the function's actual return-value shape — match what's currently there; some implementations return a dataclass or use raise-on-error. The principle is the same: insert a `slugify` call before accepting a slug-like key.)

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run wider kg_writer suite + extraction integration**

```bash
uv run pytest phase1-pablo/tests/knowledge -x
```

Expected: PASS. The pre-existing `test_uuid_shaped_paradigm_slug_rejected` still passes because the UUID check runs before slugify.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/kg_writer.py phase1-pablo/tests/knowledge/test_kg_writer_slug_norm.py
git commit -m "fix[phase1-kg]: writer renormalizes slug-like natural keys"
```

---

## Task 4: Re-run merge-quality baseline; confirm no regression

**Files:**
- Output: `phase1-pablo/evals/reports/2026-05-08-phase1-merge-quality/`

- [ ] **Step 1: Confirm baseline numbers from Phase 0**

```bash
cat phase1-pablo/evals/reports/2026-05-08-baseline-merge-quality/report.md | grep -E "precision|recall|f1"
```

Note the baseline `precision`, `recall`, `f1` numbers.

- [ ] **Step 2: Run merge-quality on the modified code**

```bash
cd phase1-pablo
uv run python -m decisionlab.cli eval run evals/suites/merge-quality.yaml
```

Expected: completes in <2 min, ~$1 cost.

- [ ] **Step 3: Move report to the named directory**

```bash
LAST=$(ls -t phase1-pablo/evals/reports/ | head -1)
mv "phase1-pablo/evals/reports/${LAST}" phase1-pablo/evals/reports/2026-05-08-phase1-merge-quality
cat phase1-pablo/evals/reports/2026-05-08-phase1-merge-quality/report.md | grep -E "precision|recall|f1"
```

- [ ] **Step 4: Compare numbers**

| Metric | Phase 0 baseline | Phase 1 result | Acceptable? |
|--------|------------------|----------------|-------------|
| precision | _read from Step 1_ | _read from Step 3_ | ≥ baseline |
| recall    | _read from Step 1_ | _read from Step 3_ | ≥ baseline |
| f1        | _read from Step 1_ | _read from Step 3_ | ≥ baseline |

If precision regressed by >0.02 or recall regressed by >0.02, **stop** — investigate which test pair flipped. The slugify change should not affect `_verify_merge` (which compares free-form text). A regression here means a downstream effect we missed; do not proceed to Phase 2 until it's understood.

- [ ] **Step 5: Commit the report**

```bash
git add phase1-pablo/evals/reports/2026-05-08-phase1-merge-quality/
git commit -m "feat[phase1-eval]: phase 1 merge-quality report (post A2/A3)"
```

---

## Task 5: Property-based regression test for slugify

**Files:**
- Create: `phase1-pablo/tests/tools/test_slugify_property.py`

- [ ] **Step 1: Write the property test**

```python
# phase1-pablo/tests/tools/test_slugify_property.py
"""Property-based regression: slugify is idempotent and produces only
safe characters across a wide input space."""

import re

from hypothesis import given, settings, strategies as st

from decisionlab.tools.reports import slugify


_SAFE = re.compile(r"^([a-z0-9]+(-[a-z0-9]+)*)?$")


@given(st.text(max_size=200))
@settings(max_examples=300)
def test_slugify_idempotent_property(raw):
    once = slugify(raw)
    assert slugify(once) == once


@given(st.text(max_size=200))
@settings(max_examples=300)
def test_slugify_output_is_safe(raw):
    s = slugify(raw)
    assert _SAFE.fullmatch(s) is not None, f"unsafe slug: {s!r} from {raw!r}"
```

- [ ] **Step 2: Add hypothesis to dev deps if missing**

```bash
grep -n "hypothesis" phase1-pablo/pyproject.toml
```

If missing, add:

```bash
cd phase1-pablo
uv add --dev hypothesis
```

- [ ] **Step 3: Run the property test**

```bash
uv run pytest phase1-pablo/tests/tools/test_slugify_property.py -v
```

Expected: PASS, 600 total assertions across both properties.

- [ ] **Step 4: Commit**

```bash
git add phase1-pablo/tests/tools/test_slugify_property.py phase1-pablo/pyproject.toml phase1-pablo/uv.lock
git commit -m "test[phase1-tools]: hypothesis property test for slugify idempotency"
```

---

## Task 6: Lint, typecheck, final regression sweep

- [ ] **Step 1: Format check**

```bash
cd phase1-pablo && uv run ruff format --check .
```

If diffs, run `uv run ruff format .` then commit.

- [ ] **Step 2: Lint**

```bash
cd phase1-pablo && uv run ruff check .
```

Expected: no errors.

- [ ] **Step 3: Full test sweep**

```bash
cd phase1-pablo && uv run pytest tests/tools tests/agents tests/knowledge tests/eval -x
```

Expected: all PASS.

- [ ] **Step 4: Commit any final formatting**

```bash
git add -A
git commit -m "chore[phase1]: ruff format pass on Phase 1" || true
```

---

## Self-Review

**Spec coverage check:**

| Spec deliverable (Phase 1) | Implemented in |
|----------------------------|----------------|
| A2 reject empty slug_proposal | Task 2 |
| A3 idempotent slugify | Tasks 1, 5 |
| A3 writer normalization | Task 3 |
| Re-run merge-quality, expect no precision regression, recall +0.05 | Task 4 |

**Placeholder check:** No "TBD". The "fill in baseline numbers" cells in Task 4's table are specifically engineer-completed at run time — they are values the eval produces.

**Type consistency:** `_slug_from_proposal(name, *, definition)`, `slugify(name) -> str`, `_validate_natural_key` 3-tuple return — all consistent across tasks.

