# Phase 4 — Track B Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve retrieval precision and recall — query rewriting at the tool boundary, Qdrant-side `exclude_run_id` filtering, ANN-indexed KG entity linking, type-filtered + IDF-decayed PPR, CRAG fail-closed, and post-CRAG window growth.

**Architecture:** A new `query_rewriter` module turns raw multi-sentence queries into `(focal_concept, keywords)` pairs feeding both the dense embedding path (focal only) and the BM25 path (full + keywords). KG entity linking gets an ANN-backed `kg_entities_dense` Qdrant collection populated by `kg_writer`, eliminating O(N) Cypher table scans. PPR is rewritten to filter by relation type and dampen by node degree. CRAG flips its failure mode to AMBIGUOUS rather than CORRECT. Top-k truncation moves to the agent boundary so CRAG-injected web supplements survive.

**Tech Stack:** Python 3.12, `pytest`, `qdrant-client`, `anthropic` (Haiku for query rewrite + KG NER), `pydantic` v2.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Track B items B1-B6.

**Depends on:** Phase 0 (timing instrumentation lets us measure retrieval p95 before/after). Phase 3 (`slug-accuracy.yaml` baseline numbers needed to assert retrieval improvements don't regress slug accuracy).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `phase1-pablo/src/decisionlab/knowledge/retrieval/query_rewriter.py` | **new** | `rewrite(query) -> _QueryRewrite` with sha1 in-process cache |
| `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py` | modify | Use focal_concept for dense; use full+keywords for sparse; move `exclude_run_id` into Qdrant filter |
| `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` | modify | ANN-backed `_link_entities_ann`; type-filtered + IDF-decayed PPR; accept rewrite hint in NER |
| `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py` | modify | Fail-closed: error → AMBIGUOUS, not CORRECT |
| `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py` | modify | Truncate to top_k only when no web supplement; thread query rewriter |
| `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` | modify | After every node write, upsert `(elementId, label, name, embedding)` into `kg_entities_dense` |
| `shared/shared/vector_store.py` | modify | Add `kg_entities_dense` collection definition; `delete_dense`/`delete_sparse` helpers (precondition for Phase 5 too) |
| `phase1-pablo/scripts/backfill_kg_entities.py` | **new** | One-shot backfill of `kg_entities_dense` from current KG state |

---

## Task 1: `vector_store.kg_entities_dense` collection + delete helpers

**Files:**
- Modify: `shared/shared/vector_store.py:24-33`

- [ ] **Step 1: Failing test**

```python
# shared/tests/test_vector_store_kg_entities.py
"""kg_entities_dense collection registered with the same dim/distance
as the other dense collections; delete helpers exist for both dense
and sparse."""

from shared.vector_store import COLLECTIONS_DENSE, VectorStore


def test_kg_entities_dense_registered():
    assert "kg_entities_dense" in COLLECTIONS_DENSE
    spec = COLLECTIONS_DENSE["kg_entities_dense"]
    assert spec["size"] == 1024
    assert spec["distance"] == "cosine"


def test_delete_dense_method_exists():
    assert hasattr(VectorStore, "delete_dense")
    assert callable(VectorStore.delete_dense)


def test_delete_sparse_method_exists():
    assert hasattr(VectorStore, "delete_sparse")
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest shared/tests/test_vector_store_kg_entities.py -v
```

Expected: failures.

- [ ] **Step 3: Add the collection + helpers**

In `shared/shared/vector_store.py`, in the `COLLECTIONS_DENSE` dict (around line 24):

```python
COLLECTIONS_DENSE = {
    "artifacts_dense": {"size": 1024, "distance": "cosine"},
    "memories_dense":  {"size": 1024, "distance": "cosine"},
    "kg_entities_dense": {"size": 1024, "distance": "cosine"},  # NEW
}
```

Add the methods to `VectorStore`:

```python
async def delete_dense(self, collection: str, *, point_id: str) -> None:
    await self._client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=[point_id]),
    )

async def delete_sparse(self, collection: str, *, point_id: str) -> None:
    await self._client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=[point_id]),
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest shared/tests/test_vector_store_kg_entities.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/shared/vector_store.py shared/tests/test_vector_store_kg_entities.py
git commit -m "feat[shared-vec]: kg_entities_dense collection + delete helpers"
```

---

## Task 2: Backfill script for `kg_entities_dense`

**Files:**
- Create: `phase1-pablo/scripts/backfill_kg_entities.py`

- [ ] **Step 1: Write the script**

```python
# phase1-pablo/scripts/backfill_kg_entities.py
"""One-shot backfill: walk every Paradigm/Variable/Postulate node in
Neo4j, embed (label, name, description), upsert into kg_entities_dense.

Idempotent — re-running with no changes is cheap (Voyage caches
embeddings; Qdrant upserts overwrite on point_id collision).
"""

from __future__ import annotations

import asyncio
import logging

from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)


LABELS = ("Paradigm", "Variable", "Postulate")


async def main():
    kg = KnowledgeGraph()
    emb = EmbeddingService()
    vec = VectorStore()

    for label in LABELS:
        # Pull all nodes of this label.
        rows = await kg.execute_query(
            f"MATCH (n:{label}) "
            f"RETURN elementId(n) AS id, "
            f"COALESCE(n.slug, n.name, n.id) AS key_value, "
            f"COALESCE(n.name, n.slug) AS name, "
            f"COALESCE(n.description, '') AS description"
        )
        if not rows:
            logger.info("backfill: no %s nodes", label)
            continue
        texts = [
            f"{r['name']}: {r['description']}" if r["description"] else r["name"]
            for r in rows
        ]
        vecs = await emb.embed_texts(texts)

        points = [
            {
                "id": r["id"],
                "vector": v,
                "payload": {
                    "label": label,
                    "key_value": r["key_value"],
                    "name": r["name"],
                },
            }
            for r, v in zip(rows, vecs)
        ]
        await vec.upsert_dense("kg_entities_dense", points)
        logger.info("backfill: upserted %d %s entities", len(points), label)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

- [ ] **Step 2: Run the backfill (after KG has been populated by previous phases)**

```bash
cd phase1-pablo
uv run python scripts/backfill_kg_entities.py
```

Expected: log lines like `backfill: upserted 12 Paradigm entities`.

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/scripts/backfill_kg_entities.py
git commit -m "feat[phase1-kg]: backfill_kg_entities.py one-shot ANN seeder"
```

---

## Task 3: `kg_writer` upserts into `kg_entities_dense` after every write

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/kg_writer.py:151-225`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/test_kg_writer_ann_sync.py
"""kg_writer upserts into kg_entities_dense after writing slug-like
nodes — so the entity ANN index stays current with the graph."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_paradigm_write_triggers_ann_upsert(monkeypatch):
    from decisionlab.knowledge import kg_writer as w

    # Stub the embedding service.
    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(return_value=[[0.1] * 1024])

    # Stub the vector store.
    fake_vec = MagicMock()
    fake_vec.upsert_dense = AsyncMock()

    # Stub KG.
    fake_kg = MagicMock()
    fake_kg.execute_write = AsyncMock(return_value={
        "elementId": "el-1",
        "created": True,
    })

    monkeypatch.setattr(w, "_get_embedding_service", lambda: fake_emb)
    monkeypatch.setattr(w, "_get_vector_store", lambda: fake_vec)

    from decisionlab.knowledge.models import ExtractionResult, NodeSpec
    extraction = ExtractionResult(
        nodes=[NodeSpec(label="Paradigm",
                        properties={"slug": "rl", "name": "RL", "description": "..."})],
        relations=[],
        facts=[],
    )

    await w.populate_kg(extraction, kg=fake_kg, run_id="r1")

    fake_emb.embed_texts.assert_awaited_once()
    fake_vec.upsert_dense.assert_awaited_once()
    args, kwargs = fake_vec.upsert_dense.call_args
    assert args[0] == "kg_entities_dense"
    points = args[1]
    assert len(points) == 1
    assert points[0]["payload"]["label"] == "Paradigm"
    assert points[0]["payload"]["key_value"] == "rl"
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_kg_writer_ann_sync.py -v
```

- [ ] **Step 3: Implement the upsert**

In `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`, after a Paradigm/Variable/Postulate node has been MERGEd successfully (around line 217-225), batch the (label, key_value, name, description) for ANN upsert. At the end of `populate_kg`, after the per-entity loops, before returning:

```python
# Sync ANN index for slug-like labels — used by retrieval._link_entities_ann.
ann_targets = [
    n for n in extraction.nodes if n.label in _SLUG_LIKE_LABELS
]
if ann_targets:
    try:
        emb = _get_embedding_service()
        vec = _get_vector_store()
        texts = []
        ids = []
        payloads = []
        for n in ann_targets:
            key = _resolve_natural_key(n)
            if key is None:
                continue
            name = n.properties.get("name") or key
            desc = n.properties.get("description") or ""
            texts.append(f"{name}: {desc}" if desc else name)
            ids.append(f"{n.label}:{key}")  # deterministic id; survives re-runs
            payloads.append({
                "label": n.label,
                "key_value": key,
                "name": name,
            })
        if texts:
            vecs = await emb.embed_texts(texts)
            points = [
                {"id": pid, "vector": v, "payload": pl}
                for pid, v, pl in zip(ids, vecs, payloads)
            ]
            await vec.upsert_dense("kg_entities_dense", points)
    except Exception as exc:
        logger.warning("kg_writer: ANN sync failed (non-fatal): %s", exc)
```

(Adapt to the actual writer structure — the principle is: after a successful MERGE for a slug-like label, fire-and-forget the ANN upsert.)

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_kg_writer_ann_sync.py -v
```

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/kg_writer.py phase1-pablo/tests/knowledge/test_kg_writer_ann_sync.py
git commit -m "feat[phase1-kg]: kg_writer syncs slug-like nodes into kg_entities_dense"
```

---

## Task 4: ANN-backed `_link_entities_ann` in kg_retrieval

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py:150-219`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_kg_link_entities_ann.py
"""Replace the O(N) Cypher table scan with a single Qdrant ANN call
against kg_entities_dense."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_link_entities_uses_ann(monkeypatch):
    from decisionlab.knowledge.retrieval import kg_retrieval as kg_r

    # Capture whether _link_entities_ann was called.
    called = AsyncMock(return_value=[
        type("_E", (), {"key_value": "reinforcement-learning",
                        "name": "Reinforcement Learning",
                        "score": 0.91})(),
    ])
    monkeypatch.setattr(kg_r, "_link_entities_ann", called)

    out = await kg_r._link_entities("Paradigm", "RL")
    called.assert_awaited_once()
    assert out[0].key_value == "reinforcement-learning"


@pytest.mark.asyncio
async def test_ann_below_threshold_returns_empty(monkeypatch):
    """If best ANN hit is below the similarity threshold, return []
    (no fallback to table scan)."""
    from decisionlab.knowledge.retrieval import kg_retrieval as kg_r

    fake_vec = MagicMock()
    fake_vec.search_dense = AsyncMock(return_value=[
        type("_H", (), {
            "id": "Paradigm:foo",
            "score": 0.50,  # below threshold
            "payload": {"label": "Paradigm", "key_value": "foo", "name": "Foo"},
        })()
    ])
    monkeypatch.setattr(kg_r, "_get_vector_store", lambda: fake_vec)

    out = await kg_r._link_entities_ann("Paradigm", "FooQuery")
    assert out == []
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement**

In `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`, add:

```python
async def _link_entities_ann(label: str, name: str) -> list[_LinkedEntity]:
    """ANN-backed entity linking against kg_entities_dense.

    Replaces the O(N) Cypher table scan + Python cosine loop. Returns
    only hits scoring >= _SIMILARITY_THRESHOLD.
    """
    vec = _get_vector_store()
    if vec is None:
        return []
    emb = _get_embedding_service()
    if emb is None:
        return []
    query_vec = await emb.embed_query(name)
    hits = await vec.search_dense(
        "kg_entities_dense",
        query_vec,
        limit=5,
        query_filter=Filter(must=[
            FieldCondition(key="label", match=MatchValue(value=label))
        ]),
    )
    out: list[_LinkedEntity] = []
    for h in hits:
        if (h.score or 0.0) < _SIMILARITY_THRESHOLD:
            continue
        payload = h.payload or {}
        out.append(_LinkedEntity(
            key_value=payload.get("key_value", ""),
            name=payload.get("name", ""),
            score=h.score,
        ))
    return out
```

Replace `_link_entities`'s table-scan path (line 189-191) with an ANN call first, falling back to Cypher exact match only:

```python
async def _link_entities(label: str, name: str) -> list[_LinkedEntity]:
    # Step 1: exact case-insensitive Cypher match (cheap)
    exact = await _link_entities_exact(label, name)
    if exact:
        return exact
    # Step 2: ANN against kg_entities_dense (no table scan)
    return await _link_entities_ann(label, name)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval -x
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py phase1-pablo/tests/knowledge/retrieval/test_kg_link_entities_ann.py
git commit -m "feat[phase1-retrieval]: ANN-backed KG entity linking"
```

---

## Task 5: Type-filtered + IDF-decayed PPR

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py:289-308`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_kg_ppr.py
"""PPR traversal must filter relations by type (per query intent) and
dampen high-degree hub nodes."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_ppr_filters_by_relation_type():
    from decisionlab.knowledge.retrieval.kg_retrieval import _ppr_traverse

    fake_kg = MagicMock()
    fake_kg.execute_query = AsyncMock(return_value=[])

    await _ppr_traverse(
        fake_kg,
        seed_id="el-1",
        seed_label="Paradigm",
        intent="paradigm",
        limit=10,
    )
    args, kwargs = fake_kg.execute_query.call_args
    cypher = args[0]
    assert "rel IN $allowed_types" in cypher or "type(rel)" in cypher
    params = kwargs if kwargs else (args[1] if len(args) > 1 else {})
    assert "EXTENDS" in params.get("allowed_types", [])
    assert "BELONGS_TO" in params.get("allowed_types", [])


@pytest.mark.asyncio
async def test_ppr_score_damps_by_degree():
    from decisionlab.knowledge.retrieval.kg_retrieval import _score_node

    high_degree = _score_node(confidence=1.0, hops=1, degree=200)
    low_degree  = _score_node(confidence=1.0, hops=1, degree=2)
    assert low_degree > high_degree
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement**

In `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`, add:

```python
import math


_PARADIGM_INTENT_TYPES = ("SUPPORTS", "CONTRADICTS", "EXTENDS", "BELONGS_TO")
_VARIABLE_INTENT_TYPES = ("MEASURES", "HAS_PARAMETER", "GOVERNS")


def _types_for_intent(intent: str) -> tuple[str, ...]:
    if intent == "variable":
        return _VARIABLE_INTENT_TYPES
    return _PARADIGM_INTENT_TYPES  # default


def _score_node(*, confidence: float, hops: int, degree: int) -> float:
    """Per-node PPR score with hub-dampening:

        score = confidence * 0.85^hops / log(2 + degree)
    """
    decay = _PPR_DECAY ** hops
    damp = 1.0 / math.log(2 + max(0, degree))
    return confidence * decay * damp


async def _ppr_traverse(
    kg, *, seed_id: str, seed_label: str, intent: str, limit: int = 20
):
    allowed_types = list(_types_for_intent(intent))
    rows = await kg.execute_query(
        "MATCH (start) WHERE elementId(start) = $seed_id "
        "MATCH path = (start)-[r*1..2]-(connected) "
        "WHERE ALL(rel IN r WHERE type(rel) IN $allowed_types) "
        "RETURN connected, "
        "       length(path) AS hops, "
        "       COUNT { (connected)--() } AS degree, "
        "       COALESCE(connected.confidence, 1.0) AS confidence "
        "LIMIT $limit",
        {"seed_id": seed_id, "allowed_types": allowed_types, "limit": limit},
    )
    scored = []
    for r in rows:
        s = _score_node(
            confidence=float(r.get("confidence") or 1.0),
            hops=int(r.get("hops") or 1),
            degree=int(r.get("degree") or 0),
        )
        scored.append((s, r["connected"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored
```

Replace the existing PPR block (line 289-308) with calls to `_ppr_traverse`. Pipe `intent` from the caller — for the tool's `namespace` argument, map: `paradigm/postulate -> "paradigm"`, `variable -> "variable"`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval -x
```

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py phase1-pablo/tests/knowledge/retrieval/test_kg_ppr.py
git commit -m "feat[phase1-retrieval]: type-filtered IDF-decayed PPR"
```

---

## Task 6: Query rewriter

**Files:**
- Create: `phase1-pablo/src/decisionlab/knowledge/retrieval/query_rewriter.py`
- Test: `phase1-pablo/tests/knowledge/retrieval/test_query_rewriter.py` (new)

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_query_rewriter.py
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_rewrite_returns_focal_and_keywords(monkeypatch):
    from decisionlab.knowledge.retrieval import query_rewriter as qr

    async def fake_call_structured(**kwargs):
        return qr._QueryRewrite(
            focal_concept="reinforcement learning",
            keywords=["q-learning", "exploration", "exploitation"],
        )

    monkeypatch.setattr(qr, "call_structured", fake_call_structured)

    out = await qr.rewrite(
        "How does Q-learning trade off exploration and exploitation?",
        client=MagicMock(),
    )
    assert out.focal_concept == "reinforcement learning"
    assert "q-learning" in out.keywords


@pytest.mark.asyncio
async def test_rewrite_caches_by_query_hash(monkeypatch):
    from decisionlab.knowledge.retrieval import query_rewriter as qr

    qr._cache.clear()
    calls = 0

    async def fake_call_structured(**kwargs):
        nonlocal calls
        calls += 1
        return qr._QueryRewrite(focal_concept="x", keywords=[])

    monkeypatch.setattr(qr, "call_structured", fake_call_structured)

    await qr.rewrite("q", client=MagicMock())
    await qr.rewrite("q", client=MagicMock())
    assert calls == 1
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement**

```python
# phase1-pablo/src/decisionlab/knowledge/retrieval/query_rewriter.py
"""Query rewriter — turn raw multi-sentence queries into a focal noun
phrase and a small bag of keywords. Feeds both vector retrieval (dense
uses focal_concept; sparse uses query + keywords) and KG NER.

In-process cache keyed by sha1(query[:512]). Cache is cleared on
process restart; that's fine for eval suites which fit in one process.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic import BaseModel, Field

from decisionlab.runtime.structured import call_structured

logger = logging.getLogger(__name__)


class _QueryRewrite(BaseModel):
    focal_concept: str = Field(
        description="Short noun phrase capturing the topic. Used for dense embedding."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="3-7 lemmas relevant to the topic. Used for BM25 + KG NER hint.",
    )


_SYSTEM_PROMPT = """\
You are a query rewriter. Given a research question, produce:
- focal_concept: the single noun phrase that best names the topic
  (e.g. "drift-diffusion model", "reinforcement learning",
  "prospect theory")
- keywords: 3-7 lemmas useful for keyword search (e.g.
  ["evidence accumulation", "decision boundary", "reaction time"])

Be concise. Lowercase. No punctuation. Do not paraphrase the question;
extract.
"""

_MAX_TOKENS = 256
_cache: dict[str, _QueryRewrite] = {}


def _cache_key(query: str) -> str:
    return hashlib.sha1(query[:512].encode("utf-8")).hexdigest()


async def rewrite(query: str, *, client) -> _QueryRewrite:
    key = _cache_key(query)
    if key in _cache:
        return _cache[key]
    try:
        result = await call_structured(
            client=client,
            messages=[{"role": "user", "content": query}],
            system=_SYSTEM_PROMPT,
            schema=_QueryRewrite,
            max_tokens=_MAX_TOKENS,
            model="claude-haiku-4-5-20251001",
        )
    except Exception as exc:
        logger.warning("query_rewriter: rewrite failed; using passthrough: %s", exc)
        result = _QueryRewrite(focal_concept=query, keywords=[])
    _cache[key] = result
    return result
```

- [ ] **Step 4: Run, verify pass**

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/query_rewriter.py phase1-pablo/tests/knowledge/retrieval/test_query_rewriter.py
git commit -m "feat[phase1-retrieval]: query_rewriter Haiku module + sha1 cache"
```

---

## Task 7: Wire rewriter into vector retrieval + KG NER

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py:71-135`
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py:83-132`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_retrieval_uses_rewriter.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_dense_uses_focal_concept(monkeypatch):
    from decisionlab.knowledge.retrieval import vector_retrieval as vr
    from decisionlab.knowledge.retrieval.query_rewriter import _QueryRewrite

    rewrite_mock = AsyncMock(return_value=_QueryRewrite(
        focal_concept="reinforcement learning",
        keywords=["q-learning"],
    ))
    monkeypatch.setattr(vr, "_rewrite", rewrite_mock)

    embed_mock = AsyncMock(return_value=[0.1] * 1024)
    monkeypatch.setattr(vr, "_embed_query", embed_mock)

    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])
    monkeypatch.setattr(vr, "_get_vector_store", lambda: fake_vs)

    await vr.vector_retrieve(
        query="How does Q-learning trade off exploration and exploitation?",
        namespace="paradigm",
        limit=5,
    )

    # Dense path embedded focal_concept, not the raw query.
    embed_mock.assert_awaited_with("reinforcement learning")

    # Sparse path used the raw query (with keywords appended somewhere
    # — we just check the raw question is present).
    sparse_call = fake_vs.search_sparse.call_args
    text_used = sparse_call.kwargs.get("text") or sparse_call.args[1]
    assert "Q-learning" in text_used or "q-learning" in text_used
```

- [ ] **Step 2: Wire it**

In `vector_retrieval.py`:

```python
from decisionlab.knowledge.retrieval.query_rewriter import rewrite as _rewrite


async def vector_retrieve(query: str, *, namespace, limit, client=None, ...):
    rewritten = await _rewrite(query, client=client) if client else None
    focal = rewritten.focal_concept if rewritten else query
    keywords = " ".join(rewritten.keywords) if rewritten else ""

    # Dense — focal only
    dense_vec = await _embed_query(focal)
    dense_hits = await vec.search_dense(...)

    # Sparse — full + keywords
    sparse_text = f"{query} {keywords}".strip()
    sparse_hits = await vec.search_sparse(..., text=sparse_text)
```

In `kg_retrieval.py`, similarly thread the rewritten object into NER prompt as a hint (prepend `Hint keywords: {keywords}` to the NER user message).

- [ ] **Step 3: Run, verify pass**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval -x
```

- [ ] **Step 4: Commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/ phase1-pablo/tests/knowledge/retrieval/test_retrieval_uses_rewriter.py
git commit -m "feat[phase1-retrieval]: dense uses focal_concept; sparse uses query+keywords; KG NER gets keywords hint"
```

---

## Task 8: Move `exclude_run_id` into Qdrant filter

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py:54-55`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_exclude_run_id_filter.py
"""exclude_run_id must be applied as a Qdrant must_not filter, not in
Python post-processing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_exclude_run_id_passed_to_qdrant(monkeypatch):
    from decisionlab.knowledge.retrieval import vector_retrieval as vr
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue

    fake_vs = MagicMock()
    fake_vs.search_dense = AsyncMock(return_value=[])
    fake_vs.search_sparse = AsyncMock(return_value=[])
    monkeypatch.setattr(vr, "_get_vector_store", lambda: fake_vs)
    monkeypatch.setattr(vr, "_embed_query", AsyncMock(return_value=[0.1]*1024))
    monkeypatch.setattr(vr, "_rewrite", AsyncMock(return_value=None))

    await vr.vector_retrieve(
        query="x", namespace="paradigm", limit=5, exclude_run_id="run-123"
    )

    qf = fake_vs.search_dense.call_args.kwargs.get("query_filter")
    assert qf is not None
    must_not_strs = [str(c) for c in qf.must_not or []]
    assert any("run-123" in s for s in must_not_strs)
```

- [ ] **Step 2: Implement**

In `vector_retrieval.py:54-55`, build the filter:

```python
from qdrant_client.http.models import Filter, FieldCondition, MatchValue


def _build_filter(*, namespace=None, exclude_run_id=None) -> Filter | None:
    must = []
    must_not = []
    if namespace:
        must.append(FieldCondition(key="namespace", match=MatchValue(value=namespace)))
    if exclude_run_id:
        must_not.append(FieldCondition(key="run_id", match=MatchValue(value=exclude_run_id)))
    if not must and not must_not:
        return None
    return Filter(must=must or None, must_not=must_not or None)
```

Pass the result via `query_filter=` to `search_dense` / `search_sparse`. Remove the post-query Python filter loop.

- [ ] **Step 3: Run, verify pass + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval -x
git add phase1-pablo/src/decisionlab/knowledge/retrieval/vector_retrieval.py phase1-pablo/tests/knowledge/retrieval/test_exclude_run_id_filter.py
git commit -m "fix[phase1-retrieval]: exclude_run_id moves to Qdrant must_not"
```

---

## Task 9: CRAG fail-closed

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py:53-60, 125-127`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_crag_fail_closed.py
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_haiku_error_marks_results_ambiguous(monkeypatch):
    from decisionlab.knowledge.retrieval import crag

    async def boom(**_):
        raise RuntimeError("haiku timeout")

    monkeypatch.setattr(crag, "_call_haiku", boom)

    results = [{"text": "x"}, {"text": "y"}]
    grades = await crag._grade(results, query="probe", client=MagicMock())
    assert all(g == "AMBIGUOUS" for g in grades.grades)
    assert grades.grading_failed is True
```

- [ ] **Step 2: Implement**

In `crag.py:53-60`:

```python
@dataclass(frozen=True)
class _CragGrades:
    grades: list[str]
    grading_failed: bool = False


async def _grade(results, *, query, client):
    if not results:
        return _CragGrades(grades=[])
    try:
        # ... existing Haiku call
    except Exception as exc:
        logger.warning("CRAG grading failed → treating as AMBIGUOUS: %s", exc)
        return _CragGrades(
            grades=["AMBIGUOUS"] * len(results),
            grading_failed=True,
        )
```

Update the routing logic at line 189-267 to honour `grading_failed` (pass results through with a logged warning rather than auto-promote to CORRECT).

- [ ] **Step 3: Run, verify pass + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/retrieval/test_crag_fail_closed.py -v
git add phase1-pablo/src/decisionlab/knowledge/retrieval/crag.py phase1-pablo/tests/knowledge/retrieval/test_crag_fail_closed.py
git commit -m "fix[phase1-retrieval]: CRAG fails closed (AMBIGUOUS) on grading error"
```

---

## Task 10: Top-k truncation moves to agent boundary

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py:374`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/retrieval/test_topk_after_crag.py
"""When CRAG injects web supplements, the final list shouldn't be
truncated to top_k mid-process. Truncation only happens at the agent
boundary, and only if no web supplement was added."""

import pytest


@pytest.mark.asyncio
async def test_web_supplemented_results_survive_topk():
    """If CRAG injected web supplements, return all kept+web (capped at
    2*top_k). Otherwise truncate to top_k as before."""
    from decisionlab.knowledge.retrieval.tool import _final_truncate

    # Case A — no web supplement, truncate normally
    results_a = [{"text": f"r{i}"} for i in range(10)]
    out_a = _final_truncate(results_a, top_k=5, web_supplemented=False)
    assert len(out_a) == 5

    # Case B — web supplemented, allow up to 2*top_k
    results_b = [{"text": f"r{i}"} for i in range(10)]
    out_b = _final_truncate(results_b, top_k=5, web_supplemented=True)
    assert len(out_b) == 10  # all kept, capped at 2*5
```

- [ ] **Step 2: Implement**

```python
def _final_truncate(results, *, top_k, web_supplemented: bool):
    cap = top_k * 2 if web_supplemented else top_k
    return results[:cap]
```

Wire `web_supplemented` from CRAG's return value through to the truncation call site.

- [ ] **Step 3: Run, commit**

```bash
git add phase1-pablo/src/decisionlab/knowledge/retrieval/tool.py phase1-pablo/tests/knowledge/retrieval/test_topk_after_crag.py
git commit -m "fix[phase1-retrieval]: preserve web-supplemented results past top_k cap"
```

---

## Task 11: Re-run slug-accuracy + record numbers

**Files:**
- Output: `phase1-pablo/evals/reports/2026-05-08-phase4-slug-accuracy/`

- [ ] **Step 1: Run the suite**

```bash
cd phase1-pablo
uv run python -m decisionlab.cli eval run evals/suites/slug-accuracy.yaml
LAST=$(ls -t evals/reports/ | head -1)
mv "evals/reports/${LAST}" evals/reports/2026-05-08-phase4-slug-accuracy
```

- [ ] **Step 2: Compare to Phase 3 baseline**

```bash
diff <(cat phase1-pablo/evals/reports/2026-05-08-phase3-slug-accuracy/report.md | grep -E "p95|avg|slug_hit_rate") \
     <(cat phase1-pablo/evals/reports/2026-05-08-phase4-slug-accuracy/report.md | grep -E "p95|avg|slug_hit_rate")
```

Expected: `retrieve_knowledge` p95 reduced (was uncovered, now should be < 2500ms); `slug_hit_rate` ≥ Phase 3.

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/evals/reports/2026-05-08-phase4-slug-accuracy/
git commit -m "feat[phase1-eval]: phase 4 slug-accuracy report (post Track B)"
```

---

## Task 12: Final sweep

```bash
cd phase1-pablo && uv run ruff format --check . && uv run ruff check . && uv run pytest tests/ -x
```

---

## Self-Review

| Spec deliverable (Phase 4) | Implemented in |
|----------------------------|----------------|
| B1 query rewriter (vector + NER) | Tasks 6, 7 |
| B2 exclude_run_id Qdrant filter | Task 8 |
| B3 ANN entity index | Tasks 1, 2, 3, 4 |
| B4 type-filtered + IDF-decayed PPR | Task 5 |
| B5 CRAG fail-closed | Task 9 |
| B6 post-CRAG window growth | Task 10 |

**Placeholder check:** No "TBD". Adapt-to-actual-shape directives in Tasks 3, 4, 7 are explicit.

**Type consistency:** `_QueryRewrite{focal_concept, keywords}`, `_LinkedEntity{key_value, name, score}`, `_CragGrades{grades, grading_failed}`, `_score_node(*, confidence, hops, degree)` — all consistent.

