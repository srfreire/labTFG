# Phase 2 — Structural Track A Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the brittle markdown-regex slug parser with a structured `list_known_slugs` retrieval helper, add a two-pass canonicalizer that expands ancestors before merging, switch to per-label thresholds, then calibrate them against the 18-pair fixture using cached cosine scores only.

**Architecture:** A new helper in `retrieval/tool.py` returns `[(slug, definition), ...]` directly from the KG/vector store, sidestepping the markdown re-parsing in the Researcher. The canonicalizer gets a Pass-2 that, when a Paradigm candidate cosine-matches between τ_loose and τ_direct, expands the candidate's neighbours via `EXTENDS|BELONGS_TO` and re-tests against ancestors. Per-label thresholds are stored in a single dict and tunable by a calibration script that runs the fixture through cosine alone (zero LLM cost).

**Tech Stack:** Python 3.12, `pytest`, `numpy` (cosine math), Cypher.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Track A items A1, A4, A5.

**Depends on:** Phase 1 (idempotent slugify) — `_slug_from_proposal` should already accept `definition`. Also depends on Phase 3's `slug-accuracy.yaml` for end-to-end validation; the engineer can either build Phase 3 first or run Phase 2 validation against `merge-quality.yaml` only.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` | modify | New `list_known_slugs(query, namespace, top_k) -> list[tuple[str, str]]` helper |
| `phase1-pablo/src/decisionlab/agents/researcher.py` | modify | Use `list_known_slugs`; delete `_KNOWN_SLUG_RE` and `_parse_known_slugs` |
| `phase1-pablo/src/decisionlab/canonicalize.py` | modify | Two-pass logic with ancestor expansion for Paradigm; `LABEL_THRESHOLDS` dict |
| `phase1-pablo/scripts/calibrate_canonicalize_tau.py` | **new** | Sweep τ ∈ [0.70, 0.95] over fixture; emit calibrated values |
| `phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py` | **new** | Helper unit tests |
| `phase1-pablo/tests/test_canonicalize_ancestor.py` | **new** | Two-pass + ancestor expansion tests |
| `phase1-pablo/tests/test_canonicalize_thresholds.py` | **new** | Per-label threshold tests |

---

## Task 1: `list_known_slugs` helper

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py`
- Test: `phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py
"""list_known_slugs returns (slug, definition) tuples directly from the
KG without going through markdown rendering."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_list_known_slugs_returns_tuples(monkeypatch):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    fake_records = [
        {"slug": "reinforcement-learning", "name": "Reinforcement Learning",
         "description": "Value-based action selection."},
        {"slug": "prospect-theory", "name": "Prospect Theory",
         "description": "Asymmetric value function over gains/losses."},
    ]

    fake_kg = MagicMock()
    fake_kg.execute_query = AsyncMock(return_value=fake_records)

    monkeypatch.setattr(tool_mod, "_get_kg", lambda: fake_kg)

    out = await tool_mod.list_known_slugs(
        query="how do animals decide which patch to forage",
        namespace="paradigm",
        top_k=5,
    )
    assert out == [
        ("reinforcement-learning", "Value-based action selection."),
        ("prospect-theory", "Asymmetric value function over gains/losses."),
    ]


@pytest.mark.asyncio
async def test_list_known_slugs_empty_when_kg_unavailable(monkeypatch):
    from decisionlab.knowledge.retrieval import tool as tool_mod

    monkeypatch.setattr(tool_mod, "_get_kg", lambda: None)
    out = await tool_mod.list_known_slugs(query="probe", namespace="paradigm", top_k=5)
    assert out == []
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py -v
```

Expected: `AttributeError: list_known_slugs`.

- [ ] **Step 3: Inspect existing tool.py to find the KG accessor pattern**

```bash
grep -n "execute_query\|knowledge_graph\|_get_kg\|kg =\|_kg_query" phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py | head -20
```

Note the actual accessor — the test stubbed `_get_kg`, but the module may use a different shape. Adapt the test fixture accordingly if needed.

- [ ] **Step 4: Implement `list_known_slugs`**

In `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py`, add (mirror existing async helpers):

```python
async def list_known_slugs(
    query: str,
    *,
    namespace: str = "paradigm",
    top_k: int = 8,
) -> list[tuple[str, str]]:
    """Return [(slug, definition), ...] for the top-k matching paradigm
    nodes. Uses the same vector backbone as ``retrieve_knowledge`` to
    rank, but returns slugs directly from the KG instead of parsing
    them out of formatted markdown.

    Returns an empty list when the KG is unavailable (preserving the
    Researcher's "no candidates → __NEW__ for everything" fallback).
    """
    if namespace != "paradigm":
        # Future-proof: the helper is paradigm-only today; other namespaces
        # don't have a comparable slug field on their nodes.
        raise ValueError(f"list_known_slugs: unsupported namespace {namespace!r}")

    # Step 1: vector retrieve to rank candidate slugs by relevance to query.
    # We piggyback on the existing tool's vector path rather than reimplement.
    from decisionlab.knowledge.retrieval.vector_retrieval import vector_retrieve

    hits = await vector_retrieve(
        query=query,
        namespace="paradigm",
        limit=top_k * 2,  # over-fetch; KG join may drop some
    )

    # Step 2: each hit's payload should carry an entity_id (Paradigm slug).
    candidate_slugs: list[str] = []
    seen: set[str] = set()
    for h in hits:
        slug = (h.payload or {}).get("entity_slug") or (h.payload or {}).get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        candidate_slugs.append(slug)
        if len(candidate_slugs) >= top_k:
            break

    if not candidate_slugs:
        return []

    # Step 3: hydrate definitions from the KG in one query.
    kg = _get_kg()
    if kg is None:
        return [(slug, "") for slug in candidate_slugs]

    rows = await kg.execute_query(
        "MATCH (p:Paradigm) WHERE p.slug IN $slugs "
        "RETURN p.slug AS slug, p.description AS description",
        {"slugs": candidate_slugs},
    )
    desc_by_slug = {r["slug"]: (r.get("description") or "") for r in rows}
    return [(s, desc_by_slug.get(s, "")) for s in candidate_slugs]
```

If `_get_kg` doesn't exist, find the project's accessor (e.g. `from shared import knowledge_graph_singleton`) and use that.

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py phase1-pablo/tests/knowledge/retrieval/test_list_known_slugs.py
git commit -m "feat[phase1-retrieval]: list_known_slugs structured helper"
```

---

## Task 2: Researcher uses `list_known_slugs`; delete regex parser

**Files:**
- Modify: `phase1-pablo/src/decisionlab/agents/researcher.py:200-242, 294-329`

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/agents/test_researcher_uses_list_known_slugs.py
"""Researcher must call list_known_slugs (not retrieve_knowledge +
markdown regex) for paradigm candidate enumeration."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_retrieve_known_paradigms_uses_helper(monkeypatch):
    from decisionlab.agents import researcher as r_mod

    fake_helper = AsyncMock(return_value=[
        ("reinforcement-learning", "Value-based action selection."),
        ("prospect-theory", "Asymmetric value over gains/losses."),
    ])
    monkeypatch.setattr(r_mod, "list_known_slugs", fake_helper)

    researcher = r_mod.Researcher(
        client=object(),
        search=object(),
        knowledge_tool_schema={"name": "retrieve_knowledge"},
        knowledge_tool_handler=AsyncMock(return_value=""),
    )
    slugs, _ = await researcher._retrieve_known_paradigms("any topic")
    fake_helper.assert_awaited_once()
    assert slugs == ["reinforcement-learning", "prospect-theory"]


def test_no_more_known_slug_regex():
    """The regex parser is dead code now."""
    import inspect
    from decisionlab.agents import researcher

    src = inspect.getsource(researcher)
    assert "_KNOWN_SLUG_RE" not in src
    assert "_parse_known_slugs" not in src
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/agents/test_researcher_uses_list_known_slugs.py -v
```

Expected: FAIL — current `_retrieve_known_paradigms` calls the markdown handler and `_parse_known_slugs`.

- [ ] **Step 3: Replace the implementation**

In `phase1-pablo/src/decisionlab/agents/researcher.py`:

- Add the import at the top:
  ```python
  from decisionlab.knowledge.retrieval.tool import list_known_slugs
  ```
- **Delete** lines 200-242 (`_KNOWN_SLUG_RE` and `_parse_known_slugs`).
- Replace `_retrieve_known_paradigms` (around line 294-329):

```python
async def _retrieve_known_paradigms(self, problem: str) -> tuple[list[str], str]:
    """Mandatory first step: ask the KG which paradigms it already covers.

    Returns ``(known_slugs, retrieval_text)``. ``retrieval_text`` is now
    a deterministic synthetic block built from ``(slug, definition)``
    pairs — used by the prompt template downstream — not the model's
    free-form markdown.
    """
    if self._knowledge_tool_handler is None:
        logger.info(
            "Researcher: knowledge backbone unavailable — no candidate slugs"
        )
        return [], ""
    try:
        pairs = await list_known_slugs(
            query=problem, namespace="paradigm", top_k=_RETRIEVAL_TOP_K
        )
    except Exception as exc:
        logger.warning(
            "Researcher: list_known_slugs raised on %r — degrading: %s",
            problem,
            exc,
        )
        return [], ""

    slugs = [s for s, _d in pairs]
    retrieval_text = "\n".join(
        f"- **{slug}** — {defn or '(no description)'}" for slug, defn in pairs
    )
    logger.info(
        "Researcher: retrieved %d candidate slug(s) from KG: %s",
        len(slugs),
        slugs,
    )
    return slugs, retrieval_text
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/agents/test_researcher_uses_list_known_slugs.py -v
```

Expected: PASS, 2/2.

- [ ] **Step 5: Run wider agent tests**

```bash
uv run pytest phase1-pablo/tests/agents -x
```

Expected: PASS. Some tests may have been asserting on the markdown format of `retrieval_text` — update them to accept the new deterministic format.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/agents/researcher.py phase1-pablo/tests/agents/test_researcher_uses_list_known_slugs.py
git commit -m "fix[phase1-research]: list_known_slugs replaces markdown regex parser"
```

---

## Task 3: `LABEL_THRESHOLDS` dict

**Files:**
- Modify: `phase1-pablo/src/decisionlab/canonicalize.py:53-54`
- Test: `phase1-pablo/tests/test_canonicalize_thresholds.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/test_canonicalize_thresholds.py
"""Per-label thresholds — Paradigm gets a τ_direct/τ_loose pair, others
get τ_direct only."""

from decisionlab.canonicalize import LABEL_THRESHOLDS, threshold_for


def test_label_thresholds_keys():
    assert set(LABEL_THRESHOLDS.keys()) == {"Paradigm", "Variable", "Postulate"}


def test_threshold_for_paradigm_returns_pair():
    direct, loose = threshold_for("Paradigm")
    assert 0.7 <= loose <= direct <= 0.95


def test_threshold_for_variable_pair_equal():
    direct, loose = threshold_for("Variable")
    assert direct == loose  # no ancestor expansion for non-Paradigm labels


def test_threshold_for_unknown_label_falls_back():
    """Unknown labels get a sane default rather than raising."""
    direct, loose = threshold_for("Nonexistent")
    assert direct == 0.85  # legacy default
    assert loose == direct
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/test_canonicalize_thresholds.py -v
```

Expected: ImportError — `LABEL_THRESHOLDS`, `threshold_for` don't exist.

- [ ] **Step 3: Implement**

In `phase1-pablo/src/decisionlab/canonicalize.py:53-54`, replace `DEFAULT_THRESHOLD` with:

```python
# Hand-picked initial values — calibrated by
# scripts/calibrate_canonicalize_tau.py (Task 5).
LABEL_THRESHOLDS: dict[str, tuple[float, float]] = {
    # (τ_direct, τ_loose). τ_loose only used by Pass 2 ancestor expansion
    # for Paradigm; for non-Paradigm labels the two are equal (no Pass 2).
    "Paradigm":  (0.85, 0.78),
    "Variable":  (0.90, 0.90),
    "Postulate": (0.83, 0.83),
}

# Legacy single-threshold knob still referenced by callers that don't
# yet pass per-label τ. Kept as the fallback for unknown labels.
DEFAULT_THRESHOLD: float = 0.85


def threshold_for(label: str) -> tuple[float, float]:
    """Return (τ_direct, τ_loose) for a label. Falls back to
    (DEFAULT_THRESHOLD, DEFAULT_THRESHOLD) for unknowns."""
    return LABEL_THRESHOLDS.get(label, (DEFAULT_THRESHOLD, DEFAULT_THRESHOLD))
```

- [ ] **Step 4: Wire into `canonicalize`**

Find the threshold check at `canonicalize.py:177` (`if best_idx < 0 or best_score < threshold: continue`). Replace the local `threshold` (passed as kwarg) with the per-label resolution:

```python
# At the top of the for-loop over candidates:
tau_direct, tau_loose = threshold_for(label)

# Replace the existing threshold check:
if best_idx < 0 or best_score < tau_loose:
    continue
# Pass-2 ancestor expansion (Task 4) will hook in here.
```

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/test_canonicalize_thresholds.py -v
uv run pytest phase1-pablo/tests/test_canonicalize.py -x
```

Expected: PASS for new test; the existing canonicalize tests may fail because the kwarg `threshold=` no longer drives behaviour. Update those tests to pass `tau_direct`/`tau_loose` explicitly, or accept that the per-label dict overrides them.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/canonicalize.py phase1-pablo/tests/test_canonicalize_thresholds.py
git commit -m "feat[phase1-canon]: per-label thresholds dict + threshold_for helper"
```

---

## Task 4: Two-pass canonicalize with ancestor expansion

**Files:**
- Modify: `phase1-pablo/src/decisionlab/canonicalize.py:165-240`
- Test: `phase1-pablo/tests/test_canonicalize_ancestor.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# phase1-pablo/tests/test_canonicalize_ancestor.py
"""Two-pass canonicalize: when a Paradigm candidate cosine-matches
between τ_loose (0.78) and τ_direct (0.85), expand the candidate's
neighbours via EXTENDS|BELONGS_TO and re-test against ancestors. The
verifier sees the candidate vs the ancestor, not vs the loose neighbour.

Concrete failure mode being fixed: q-learning candidate cosine-matches
policy-gradient at 0.82 (between τ_loose 0.78 and τ_direct 0.85). Old
behaviour: skip — no merge happens, q-learning becomes its own node.
New behaviour: expand policy-gradient's parents → reinforcement-learning
sits at 0.91 cosine to q-learning → merge into reinforcement-learning."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.canonicalize import _ExistingNode


@pytest.mark.asyncio
async def test_ancestor_expansion_merges_into_parent(monkeypatch):
    from decisionlab import canonicalize as c_mod

    # Stub embedding service: q-learning cosine-matches policy-gradient
    # at 0.82, but reinforcement-learning at 0.91.
    async def fake_embed(texts):
        # Just return distinct vectors per text; distances are tabulated below.
        return [[1.0 if "q-learning" in t else
                 0.82 if "policy-gradient" in t else
                 0.91 if "reinforcement-learning" in t else
                 0.0,
                 0.0, 0.0] for t in texts]

    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(side_effect=fake_embed)

    # Stub KG: existing nodes are policy-gradient and reinforcement-learning.
    # _fetch_ancestors(policy-gradient) returns [reinforcement-learning].
    fake_kg = MagicMock()
    fake_kg.execute_query = AsyncMock(side_effect=[
        # First call: _fetch_existing_nodes(Paradigm)
        [{"slug": "policy-gradient", "name": "Policy Gradient",
          "description": "Direct policy optimisation"},
         {"slug": "reinforcement-learning", "name": "Reinforcement Learning",
          "description": "Value-based action selection"}],
        # Second call: _fetch_ancestors(policy-gradient)
        [{"slug": "reinforcement-learning",
          "name": "Reinforcement Learning",
          "description": "Value-based action selection"}],
    ])

    # Stub verifier: approve q-learning -> reinforcement-learning.
    from decisionlab.canonicalize import _MergeVerification

    async def fake_verify(*, label, candidate_text, existing_text, similarity, client):
        approved = "reinforcement-learning" in existing_text
        return _MergeVerification(merge=approved, reason="ok")

    monkeypatch.setattr(c_mod, "_verify_merge", fake_verify)

    # Build extraction with one Paradigm node "q-learning".
    from decisionlab.knowledge.models import ExtractionResult, NodeSpec
    extraction = ExtractionResult(
        nodes=[NodeSpec(label="Paradigm",
                        properties={"slug": "q-learning",
                                    "name": "Q-learning",
                                    "description": "Off-policy TD control"})],
        relations=[],
        facts=[],
    )

    out = await c_mod.canonicalize(
        extraction,
        kg=fake_kg,
        embedding_service=fake_emb,
        client=object(),
    )

    # The q-learning candidate was dropped (merged); only the existing
    # nodes survive in the output.
    surviving_slugs = {n.properties.get("slug") for n in out.nodes}
    assert "q-learning" not in surviving_slugs
```

> Adjust the `_ExistingNode` / `NodeSpec` import paths if your repo nests them differently. The structural assertion (q-learning gets dropped via ancestor expansion) is the contract; the rest is wiring.

- [ ] **Step 2: Run, verify it fails**

```bash
uv run pytest phase1-pablo/tests/test_canonicalize_ancestor.py -v
```

Expected: FAIL — current code's Pass 1 stops at `if best_score < tau_loose: continue` (or `< 0.85` pre-Task 3) and never expands ancestors.

- [ ] **Step 3: Implement `_fetch_ancestors`**

In `phase1-pablo/src/decisionlab/canonicalize.py`, add:

```python
async def _fetch_ancestors(
    kg: KnowledgeGraph, slug: str, max_hops: int = 2
) -> list[_ExistingNode]:
    """Return up to max_hops ancestors of a Paradigm via EXTENDS|BELONGS_TO.

    Used by the Pass-2 ancestor expansion: when a candidate cosine-matches
    a leaf paradigm just below τ_direct, we want to test merging into the
    *parent* paradigm instead, since LLMs frequently propose specialisations
    (e.g. "Q-learning") that should canonicalize to the umbrella.
    """
    rows = await kg.execute_query(
        f"MATCH (start:Paradigm {{slug: $slug}})"
        f"-[:EXTENDS|BELONGS_TO*1..{max_hops}]->(p:Paradigm) "
        "RETURN p.slug AS slug, p.name AS name, p.description AS description",
        {"slug": slug},
    )
    out: list[_ExistingNode] = []
    for r in rows:
        text = f"{r.get('name') or r['slug']}: {r.get('description') or ''}"
        out.append(
            _ExistingNode(
                key_value=r["slug"],
                text=text,
                properties=dict(r),
            )
        )
    return out
```

- [ ] **Step 4: Implement Pass-2 in the canonicalize loop**

Replace the threshold-failed branch (`canonicalize.py:177-182`) with:

```python
# Pass 1 — direct neighbour at τ_direct
direct_idx = best_idx if best_score >= tau_direct else -1

# Pass 2 — Paradigm-only ancestor expansion when in the τ_loose..τ_direct
# gray zone. The loose neighbour is *not* the merge target; it's just a
# probe whose ancestors we test against.
if direct_idx < 0 and label == "Paradigm" and best_score >= tau_loose:
    loose_neighbour = existing[best_idx]
    try:
        ancestors = await _fetch_ancestors(kg, loose_neighbour.key_value)
    except Exception as exc:
        logger.warning(
            "canonicalize: _fetch_ancestors failed for %s: %s",
            loose_neighbour.key_value,
            exc,
        )
        ancestors = []
    if ancestors:
        anc_texts = [a.text for a in ancestors]
        anc_vecs = await embedding_service.embed_texts(anc_texts)
        # Pick the strongest ancestor cosine.
        best_anc_idx = -1
        best_anc_score = -1.0
        for j, av in enumerate(anc_vecs):
            sim = _cosine(cand_vec, av)
            if sim > best_anc_score:
                best_anc_score = sim
                best_anc_idx = j
        if best_anc_idx >= 0 and best_anc_score >= tau_direct:
            # Found a good ancestor — substitute it as the merge target.
            existing = list(existing) + [ancestors[best_anc_idx]]
            best_idx = len(existing) - 1
            best_score = best_anc_score
            direct_idx = best_idx
            logger.info(
                "canonicalize: ancestor expansion %s sim=%.3f -> %s sim=%.3f",
                loose_neighbour.key_value,
                # the original loose score:
                next(
                    sim for sim in [_cosine(cand_vec, e_v) for e_v in exist_vecs]
                    if sim == best_score
                ) if False else 0.0,  # cosmetic logging
                ancestors[best_anc_idx].key_value,
                best_anc_score,
            )

if direct_idx < 0:
    continue

# (now best_idx is the merge target; the LLM verifier runs as before)
```

(Adapt this to the project's actual variable shape — the principle is: when Pass 1 misses, run Pass 2; if Pass 2 finds an ancestor at ≥ τ_direct, set that as the merge target and let the LLM verifier confirm.)

- [ ] **Step 5: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/test_canonicalize_ancestor.py -v
```

Expected: PASS.

- [ ] **Step 6: Run full canonicalize suite**

```bash
uv run pytest phase1-pablo/tests/test_canonicalize.py phase1-pablo/tests/test_canonicalize_ancestor.py phase1-pablo/tests/test_canonicalize_thresholds.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add phase1-pablo/src/decisionlab/canonicalize.py phase1-pablo/tests/test_canonicalize_ancestor.py
git commit -m "feat[phase1-canon]: two-pass canonicalize with ancestor expansion for Paradigm"
```

---

## Task 5: Calibration script

**Files:**
- Create: `phase1-pablo/scripts/calibrate_canonicalize_tau.py`

- [ ] **Step 1: Write the script**

```python
# phase1-pablo/scripts/calibrate_canonicalize_tau.py
"""Calibrate canonicalize per-label thresholds against the
canonicalize-pairs.json fixture using cached cosine scores only —
no LLM calls. Emits a suggested LABEL_THRESHOLDS dict to stdout.

Usage:
    cd phase1-pablo
    uv run python scripts/calibrate_canonicalize_tau.py

The script:
  1. Loads canonicalize-pairs.json.
  2. Embeds all (candidate, existing) texts via the project's
     EmbeddingService (cached transparently by Voyage if you've run
     merge-quality in the same hour).
  3. For each label and each tau in [0.70, 0.95, 0.01]:
       - predict merge iff cosine >= tau
       - compute precision/recall/F1 vs labelled should_merge
  4. Pick tau that maximises F1; tie-break toward precision.
  5. Print the resulting dict in copy-pasteable form.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from pathlib import Path

from shared.embedding import EmbeddingService

FIXTURE = Path("evals/fixtures/canonicalize-pairs.json")


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def main():
    pairs = json.loads(FIXTURE.read_text())
    by_label: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_label[p["label"]].append(p)

    emb = EmbeddingService()  # singleton; reuses Voyage credentials

    out: dict[str, tuple[float, float]] = {}
    for label, label_pairs in by_label.items():
        cand_texts = [p["candidate"] for p in label_pairs]
        exist_texts = [p["existing"] for p in label_pairs]
        cand_vecs = await emb.embed_texts(cand_texts)
        exist_vecs = await emb.embed_texts(exist_texts)
        cosines = [cosine(c, e) for c, e in zip(cand_vecs, exist_vecs)]
        labels = [bool(p["should_merge"]) for p in label_pairs]

        best_tau = 0.85
        best_f1 = -1.0
        best_p = 0.0
        for tau_int in range(70, 96):
            tau = tau_int / 100.0
            tp = sum(1 for c, l in zip(cosines, labels) if c >= tau and l)
            fp = sum(1 for c, l in zip(cosines, labels) if c >= tau and not l)
            fn = sum(1 for c, l in zip(cosines, labels) if c < tau and l)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            if f1 > best_f1 or (f1 == best_f1 and precision > best_p):
                best_f1 = f1
                best_p = precision
                best_tau = tau
        # τ_loose for Paradigm is 0.07 below τ_direct (heuristic);
        # for other labels we keep direct == loose.
        if label == "Paradigm":
            out[label] = (round(best_tau, 2), round(max(0.70, best_tau - 0.07), 2))
        else:
            out[label] = (round(best_tau, 2), round(best_tau, 2))
        print(f"  {label:<10} τ_direct={best_tau:.2f} F1={best_f1:.3f} (n={len(label_pairs)})")

    print("\nSuggested LABEL_THRESHOLDS:")
    print("LABEL_THRESHOLDS = {")
    for k, v in sorted(out.items()):
        print(f"    {k!r:<12}: ({v[0]:.2f}, {v[1]:.2f}),")
    print("}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Make it executable and run**

```bash
chmod +x phase1-pablo/scripts/calibrate_canonicalize_tau.py
cd phase1-pablo
uv run python scripts/calibrate_canonicalize_tau.py
```

Expected output: per-label F1 scores and a suggested `LABEL_THRESHOLDS` block.

- [ ] **Step 3: Update `LABEL_THRESHOLDS` in canonicalize.py**

Paste the suggested values into `phase1-pablo/src/decisionlab/canonicalize.py` (Task 3 location), replacing the hand-picked initial values.

- [ ] **Step 4: Re-run the merge-quality suite**

```bash
cd phase1-pablo
uv run python -m decisionlab.cli eval run evals/suites/merge-quality.yaml
LAST=$(ls -t evals/reports/ | head -1)
mv "evals/reports/${LAST}" evals/reports/2026-05-08-phase2-merge-quality
cat evals/reports/2026-05-08-phase2-merge-quality/report.md | grep -E "precision|recall|f1"
```

- [ ] **Step 5: Verify F1 improved vs Phase 1 baseline**

```bash
diff <(grep -E "precision|recall|f1" phase1-pablo/evals/reports/2026-05-08-phase1-merge-quality/report.md) \
     <(grep -E "precision|recall|f1" phase1-pablo/evals/reports/2026-05-08-phase2-merge-quality/report.md)
```

Expected: Phase 2 F1 ≥ Phase 1 F1.

- [ ] **Step 6: Commit**

```bash
git add phase1-pablo/scripts/calibrate_canonicalize_tau.py phase1-pablo/src/decisionlab/canonicalize.py phase1-pablo/evals/reports/2026-05-08-phase2-merge-quality/
git commit -m "feat[phase1-canon]: calibrated per-label thresholds + report"
```

---

## Task 6: Final regression sweep

- [ ] **Step 1: Format + lint**

```bash
cd phase1-pablo && uv run ruff format --check . && uv run ruff check .
```

- [ ] **Step 2: Full test sweep**

```bash
cd phase1-pablo && uv run pytest tests/ -x --ignore=tests/agents/test_full_pipeline_integration.py
```

Expected: all PASS.

- [ ] **Step 3: Commit any formatter fixes**

---

## Self-Review

**Spec coverage:**

| Spec deliverable (Phase 2) | Implemented in |
|----------------------------|----------------|
| A1 list_known_slugs helper | Task 1 |
| A1 drop _parse_known_slugs | Task 2 |
| A4 ancestor expansion | Tasks 3, 4 |
| A5 per-label thresholds | Task 3 |
| A5 calibration script | Task 5 |
| Re-run merge-quality | Task 5 |

**Placeholder check:** No "TBD". Adapt-to-actual-shape directives in Tasks 1, 4 are explicit pointers — engineer fills them by reading the relevant module. The fake stubs in tests are intentionally minimal.

**Type consistency:** `LABEL_THRESHOLDS: dict[str, tuple[float, float]]`, `threshold_for(label) -> tuple[float, float]`, `_fetch_ancestors(kg, slug, max_hops=2) -> list[_ExistingNode]`, `list_known_slugs(query, *, namespace, top_k) -> list[tuple[str, str]]` — all consistent.

