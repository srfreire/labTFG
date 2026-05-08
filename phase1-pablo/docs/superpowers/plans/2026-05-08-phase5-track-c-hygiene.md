# Phase 5 — Track C Population Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop the long-tail noise that drowns retrieval over time — paradigm-scope Variable nodes, sync Qdrant deletes with Postgres prune, MERGE Reflection nodes (idempotent), feed full content to the conflict classifier, default UNKNOWN to DUPLICATE under high cosine.

**Architecture:** Five focused fixes, mostly correctness. The biggest is C1 — Variable.name is currently the global Neo4j unique key, so `reward` in RL clobbers `reward` in prospect-theory. We migrate to a composite `id = "{paradigm_slug}:{name}"` with a one-shot Cypher migration. Other fixes are localized: a `delete_dense`/`delete_sparse` call after Postgres prune (Task 2 of Phase 4 already added the helpers); a unique key on Reflection so consolidation retries don't duplicate; a payload schema bump to carry `content_full` for memories; and a fallback rule in the resolver.

**Tech Stack:** Python 3.12, `pytest`, Cypher (one-shot migration), Qdrant.

**Spec reference:** `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md` — Track C items C1-C5.

**Depends on:** Phase 4 (`delete_dense`/`delete_sparse` helpers). Phase 0 (timing, baseline).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `shared/shared/knowledge_graph.py` | modify | Variable schema: unique key `id`, indexed `paradigm_slug` |
| `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` | modify | Build `Variable.id = f"{paradigm_slug}:{slugify(name)}"` |
| `shared/migrations/2026-05-08-paradigm-scoped-variables.cypher` | **new** | One-shot migration |
| `shared/shared/memories.py` | modify | Qdrant payload includes `content_full` for memories collection |
| `phase1-pablo/src/decisionlab/knowledge/resolver.py` | modify | Conflict classifier reads `content_full`; UNKNOWN→DUPLICATE under high cosine |
| `phase1-pablo/src/decisionlab/knowledge/consolidation.py` | modify | Prune deletes Qdrant points; Reflection MERGEs by deterministic id |

---

## Task 1: Variable schema — paradigm-scoped composite id

**Files:**
- Modify: `shared/shared/knowledge_graph.py:15-27`
- Test: `shared/tests/test_knowledge_graph_schema.py`

- [ ] **Step 1: Failing test**

```python
# shared/tests/test_knowledge_graph_schema.py
"""Variable's unique key is now `id` (composite paradigm_slug:name),
not the bare `name`."""

from shared.knowledge_graph import KnowledgeGraph


def test_variable_unique_key_is_id():
    assert KnowledgeGraph.unique_key_for("Variable") == "id"


def test_variable_indexes_include_paradigm_slug():
    info = KnowledgeGraph.SCHEMA["Variable"]
    assert "paradigm_slug" in info["indexes"]
    assert "name" in info["indexes"]
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest shared/tests/test_knowledge_graph_schema.py -v
```

- [ ] **Step 3: Update the schema**

In `shared/shared/knowledge_graph.py:15-27`, change Variable's entry:

```python
SCHEMA = {
    # ... other labels unchanged ...
    "Variable": {"unique_key": "id", "indexes": ["paradigm_slug", "name"]},
    # ...
}
```

- [ ] **Step 4: Run, verify pass**

```bash
uv run pytest shared/tests/test_knowledge_graph_schema.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/shared/knowledge_graph.py shared/tests/test_knowledge_graph_schema.py
git commit -m "feat[shared-kg]: Variable.id composite key (paradigm-scoped)"
```

---

## Task 2: kg_writer builds composite Variable.id

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/test_kg_writer_variable_composite.py
"""Variable nodes get id = {paradigm_slug}:{slugify(name)} when
paradigm_slug is in their properties."""

from decisionlab.knowledge.kg_writer import _resolve_natural_key


def test_variable_with_paradigm_gets_composite_id():
    spec = type("_Spec", (), {
        "label": "Variable",
        "properties": {"name": "reward", "paradigm_slug": "reinforcement-learning"},
    })()
    out = _resolve_natural_key(spec)
    assert out == ("id", "reinforcement-learning:reward")


def test_variable_without_paradigm_falls_back_to_name():
    """Orphan variable — no paradigm context — gets unscoped id."""
    spec = type("_Spec", (), {
        "label": "Variable",
        "properties": {"name": "reward"},
    })()
    out = _resolve_natural_key(spec)
    # Orphan tag — accept either bare name or "orphan:reward"; pick whichever
    # the implementation chooses, just don't silently merge with the scoped one.
    assert out is not None
    label, value = out
    assert label == "id"
    assert value != "reinforcement-learning:reward"


def test_variable_id_normalises_name():
    """Inner spaces / mixed case in name → slugified before composite."""
    spec = type("_Spec", (), {
        "label": "Variable",
        "properties": {"name": "Action Value", "paradigm_slug": "reinforcement-learning"},
    })()
    out = _resolve_natural_key(spec)
    assert out == ("id", "reinforcement-learning:action-value")
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement**

In `phase1-pablo/src/decisionlab/knowledge/kg_writer.py`, modify `_resolve_natural_key`. After the existing label-specific path:

```python
from decisionlab.tools.reports import slugify  # if not already imported


def _resolve_natural_key(node):
    if node.label == "Variable":
        name = node.properties.get("name") or ""
        paradigm = node.properties.get("paradigm_slug") or ""
        slug_name = slugify(name)
        if not slug_name:
            return None  # genuinely no signal — let the caller fall back to synthetic id
        if paradigm:
            return ("id", f"{slugify(paradigm)}:{slug_name}")
        # Orphan: still scope it under a fixed namespace so it can't collide
        # with a real paradigm-scoped variable.
        return ("id", f"orphan:{slug_name}")

    # ... existing logic for other labels unchanged ...
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_kg_writer_variable_composite.py -v
git add phase1-pablo/src/decisionlab/knowledge/kg_writer.py phase1-pablo/tests/knowledge/test_kg_writer_variable_composite.py
git commit -m "fix[phase1-kg]: Variable.id = {paradigm}:{slugify(name)}"
```

---

## Task 3: Migration script for existing Variables

**Files:**
- Create: `shared/migrations/2026-05-08-paradigm-scoped-variables.cypher`

- [ ] **Step 1: Write the migration**

```cypher
// shared/migrations/2026-05-08-paradigm-scoped-variables.cypher
//
// Move every Variable from name-keyed to id-keyed. For each Variable:
//   1. Find its parent Paradigm (via BELONGS_TO or MEASURED_IN)
//   2. Set id = "{paradigm.slug}:{slugify(name)}"
//   3. Orphans get id = "orphan:{slugify(name)}"
//
// IMPORTANT: run inside an explicit transaction. If the migration fails
// halfway through, the partial state is unsafe (some Variables have id,
// others don't). Wrap in BEGIN ... COMMIT / ROLLBACK.
//
// To run:
//   cypher-shell -u neo4j -p $NEO4J_PASSWORD \
//     -f shared/migrations/2026-05-08-paradigm-scoped-variables.cypher

// Step 1 — orphan variables (no paradigm linkage)
MATCH (v:Variable)
WHERE NOT (v)-[:BELONGS_TO|:MEASURED_IN]->(:Paradigm)
  AND v.id IS NULL
SET v.id = "orphan:" + toLower(replace(replace(v.name, " ", "-"), "_", "-"));

// Step 2 — paradigm-scoped variables
MATCH (v:Variable)-[:BELONGS_TO|:MEASURED_IN]->(p:Paradigm)
WHERE v.id IS NULL
WITH v, head(collect(p)) AS parent
SET v.id = parent.slug + ":" +
           toLower(replace(replace(v.name, " ", "-"), "_", "-")),
    v.paradigm_slug = parent.slug;

// Step 3 — drop the old name-uniqueness constraint, add new id-uniqueness
DROP CONSTRAINT variable_name_unique IF EXISTS;
CREATE CONSTRAINT variable_id_unique IF NOT EXISTS
  FOR (v:Variable) REQUIRE v.id IS UNIQUE;
CREATE INDEX variable_paradigm_slug IF NOT EXISTS
  FOR (v:Variable) ON (v.paradigm_slug);
CREATE INDEX variable_name_idx IF NOT EXISTS
  FOR (v:Variable) ON (v.name);

// Step 4 — verify
MATCH (v:Variable) WHERE v.id IS NULL
RETURN count(v) AS missing_ids;
// expected: 0. If non-zero, ROLLBACK and investigate.
```

- [ ] **Step 2: Test the migration on a copy of the dev KG**

```bash
# Snapshot first
neo4j-admin database dump neo4j --to-path=/tmp/pre-c1-variable-migration

# Run the migration
cypher-shell -u neo4j -p $NEO4J_PASSWORD \
  -f shared/migrations/2026-05-08-paradigm-scoped-variables.cypher
```

Expected: final query returns `missing_ids: 0`.

- [ ] **Step 3: Commit**

```bash
git add shared/migrations/2026-05-08-paradigm-scoped-variables.cypher
git commit -m "feat[shared-kg]: paradigm-scoped Variable migration script"
```

---

## Task 4: `content_full` in memories Qdrant payload

**Files:**
- Modify: `shared/shared/memories.py` and `shared/shared/vector_store.py` payload writers
- Modify: `phase1-pablo/src/decisionlab/knowledge/resolver.py:126`

- [ ] **Step 1: Failing test**

```python
# shared/tests/test_memory_payload_full.py
"""Memories collection payload includes content_full (no 200-char cap).
Artifacts collection still uses text_preview."""

from shared.memories import build_memory_payload


def test_memory_payload_has_content_full():
    payload = build_memory_payload(
        content="x" * 1500,
        namespace="paradigm",
        run_id="r",
        importance=5.0,
        confidence=0.9,
    )
    assert payload["content_full"] == "x" * 1500
    assert payload["text_preview"] == "x" * 200  # legacy field still present
```

- [ ] **Step 2: Implement**

Find the function that builds the Qdrant payload for memory upserts (e.g. `build_memory_payload` in `shared/shared/memories.py`). Add `content_full` alongside the existing `text_preview`. For the artifacts collection, leave `text_preview` only (artifact text is large; storing full text bloats the index).

- [ ] **Step 3: Update resolver to read `content_full` for the conflict classifier**

In `phase1-pablo/src/decisionlab/knowledge/resolver.py:126`, replace:

```python
existing_text = best["payload"].get("text_preview", "")
```

with:

```python
existing_text = best["payload"].get("content_full") or best["payload"].get("text_preview", "")
# Legacy memories may not have content_full yet; fallback prevents
# crashes during the rollout window.
```

- [ ] **Step 4: Commit**

```bash
git add shared/shared/memories.py phase1-pablo/src/decisionlab/knowledge/resolver.py shared/tests/test_memory_payload_full.py
git commit -m "feat[shared-mem]: content_full in memories payload; resolver reads it"
```

---

## Task 5: Sync Qdrant deletes with Postgres prune

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/consolidation.py:514-545`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/test_consolidation_qdrant_sync.py
"""When consolidation prunes a memory (sets valid_to in Postgres), the
corresponding Qdrant points in memories_dense and memories_sparse must
be deleted too — otherwise pruned content keeps surfacing in retrieval."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_prune_deletes_qdrant_points(monkeypatch):
    from decisionlab.knowledge import consolidation as c_mod

    fake_store = MagicMock()
    fake_store.list_prunable = AsyncMock(return_value=[
        {"id": "mem-1", "valid_to": None, "confidence": 0.05,
         "access_count": 0, "created_at": "1970-01-01T00:00:00Z"},
    ])
    fake_store.update_memory = AsyncMock()
    monkeypatch.setattr(c_mod, "_get_store", lambda: fake_store)

    fake_vec = MagicMock()
    fake_vec.delete_dense = AsyncMock()
    fake_vec.delete_sparse = AsyncMock()
    monkeypatch.setattr(c_mod, "_get_vector_store", lambda: fake_vec)

    await c_mod._prune_low_confidence(run_id="r")

    fake_vec.delete_dense.assert_awaited_with("memories_dense", point_id="mem-1")
    fake_vec.delete_sparse.assert_awaited_with("memories_sparse", point_id="mem-1")
```

- [ ] **Step 2: Implement**

In `consolidation.py:514-545`, add the deletes after the `update_memory(valid_to=...)` call:

```python
async def _prune_low_confidence(*, run_id: str):
    store = _get_store()
    vec = _get_vector_store()
    candidates = await store.list_prunable()
    for mem in candidates:
        if not _is_prunable(mem):
            continue
        await store.update_memory(mem["id"], valid_to=datetime.now(UTC))
        # Sync vector store — pruned memories should no longer appear in
        # retrieval results.
        try:
            await vec.delete_dense("memories_dense", point_id=str(mem["id"]))
            await vec.delete_sparse("memories_sparse", point_id=str(mem["id"]))
        except Exception as exc:
            logger.warning(
                "consolidation: Qdrant delete failed for %s (non-fatal): %s",
                mem["id"], exc,
            )
```

- [ ] **Step 3: Run + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_consolidation_qdrant_sync.py -v
git add phase1-pablo/src/decisionlab/knowledge/consolidation.py phase1-pablo/tests/knowledge/test_consolidation_qdrant_sync.py
git commit -m "fix[phase1-consolid]: prune deletes Qdrant points"
```

---

## Task 6: MERGE Reflection nodes by deterministic id

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/consolidation.py:339`
- Modify: `shared/shared/knowledge_graph.py` SCHEMA

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/test_reflection_merge.py
"""Reflection nodes have a deterministic id derived from cluster member
ids; consolidation retries don't duplicate them."""

import hashlib

from decisionlab.knowledge.consolidation import _reflection_id_for


def test_reflection_id_deterministic():
    members = ["m-1", "m-2", "m-3"]
    a = _reflection_id_for(members)
    b = _reflection_id_for(["m-3", "m-1", "m-2"])  # order shouldn't matter
    assert a == b
    assert len(a) == 16


def test_reflection_id_differs_for_different_clusters():
    a = _reflection_id_for(["m-1", "m-2"])
    b = _reflection_id_for(["m-1", "m-3"])
    assert a != b
```

- [ ] **Step 2: Implement**

Add to `consolidation.py`:

```python
def _reflection_id_for(member_ids: list[str]) -> str:
    """Stable id for a Reflection node — sha1 of sorted member ids,
    truncated to 16 chars. Same cluster → same id, so re-running
    consolidation upserts rather than duplicates."""
    blob = ",".join(sorted(str(m) for m in member_ids)).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]
```

Add Reflection to the schema (`shared/shared/knowledge_graph.py`):

```python
"Reflection": {"unique_key": "id", "indexes": ["created_at"]},
```

In `consolidation.py:339`, replace `kg.create_node(...)` with `kg.upsert_node(label="Reflection", key="id", value=_reflection_id_for(member_ids), properties={...})` (or whichever the project's MERGE-equivalent helper is — check the kg_writer style).

- [ ] **Step 3: Run + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_reflection_merge.py -v
git add phase1-pablo/src/decisionlab/knowledge/consolidation.py shared/shared/knowledge_graph.py phase1-pablo/tests/knowledge/test_reflection_merge.py
git commit -m "fix[phase1-consolid]: MERGE Reflection by sha1(member_ids)"
```

---

## Task 7: Resolver UNKNOWN → DUPLICATE under high cosine

**Files:**
- Modify: `phase1-pablo/src/decisionlab/knowledge/resolver.py:178-184, 354-367`

- [ ] **Step 1: Failing test**

```python
# phase1-pablo/tests/knowledge/test_resolver_unknown_safe.py
"""When the conflict classifier fails (returns UNKNOWN) AND a high-cosine
candidate exists (>= 0.85), default to DUPLICATE rather than NEW —
fail-closed under degraded LLM."""

import pytest


@pytest.mark.asyncio
async def test_unknown_with_high_cosine_treated_as_duplicate(monkeypatch):
    from decisionlab.knowledge import resolver as r_mod

    async def boom(*args, **kwargs):
        # Simulate StructuredOutputError → UNKNOWN
        return {"classification": "UNKNOWN", "reasoning": "boom"}
    monkeypatch.setattr(r_mod, "_classify_conflict", boom)

    decision = await r_mod._decide_what_to_do(
        fact="x",
        best_candidate_score=0.91,
        best_candidate_payload={"content_full": "x"},
        run_id="r",
    )
    assert decision == "DUPLICATE"


@pytest.mark.asyncio
async def test_unknown_no_candidate_still_new():
    """If no candidate exists at all, UNKNOWN means store as NEW."""
    from decisionlab.knowledge import resolver as r_mod

    decision = await r_mod._decide_what_to_do(
        fact="x",
        best_candidate_score=0.0,
        best_candidate_payload=None,
        run_id="r",
    )
    assert decision == "NEW"
```

- [ ] **Step 2: Implement**

In `resolver.py`, factor the post-classification decision into a helper:

```python
async def _decide_what_to_do(
    *, fact: str, best_candidate_score: float, best_candidate_payload, run_id: str,
) -> str:
    """Map a (cosine, classification) pair to the storage decision."""
    if best_candidate_payload is None:
        return "NEW"
    classification = (await _classify_conflict(fact, best_candidate_payload))[
        "classification"
    ]
    if classification == "UNKNOWN":
        # Fail-closed: under classifier degradation, prefer skipping the
        # write (DUPLICATE) over creating a likely-redundant memory.
        if best_candidate_score >= 0.85:
            return "DUPLICATE"
        return "NEW"
    return classification
```

Update the caller (`resolver.py:354-367`) to use `_decide_what_to_do` and dispatch on the returned string.

- [ ] **Step 3: Run + commit**

```bash
uv run pytest phase1-pablo/tests/knowledge/test_resolver_unknown_safe.py -v
git add phase1-pablo/src/decisionlab/knowledge/resolver.py phase1-pablo/tests/knowledge/test_resolver_unknown_safe.py
git commit -m "fix[phase1-resolver]: UNKNOWN → DUPLICATE under high cosine"
```

---

## Task 8: Re-run cumulative-growth + record numbers

**Files:**
- Output: `phase1-pablo/evals/reports/2026-05-08-phase5-cumulative-growth/`

- [ ] **Step 1: Reset KG (necessary — Variable schema changed)**

```bash
cd phase1-pablo
uv run python -c "
import asyncio
from decisionlab.eval import kgadmin
asyncio.run(kgadmin.reset(confirm=True))
"
```

- [ ] **Step 2: Run cumulative-growth (5 topics, ~$10)**

```bash
uv run python -m decisionlab.cli eval run evals/suites/cumulative-growth.yaml
LAST=$(ls -t evals/reports/ | head -1)
mv "evals/reports/${LAST}" evals/reports/2026-05-08-phase5-cumulative-growth
```

- [ ] **Step 3: Verify per-label growth rates against targets**

Open `phase1-pablo/evals/reports/2026-05-08-phase5-cumulative-growth/report.md`:
- `kg_growth_rate(Paradigm)` ≤ 1.5/topic
- `kg_growth_rate(Variable)` ≤ 6/topic
- `kg_growth_rate(Postulate)` ≤ 5/topic

- [ ] **Step 4: Commit**

```bash
git add phase1-pablo/evals/reports/2026-05-08-phase5-cumulative-growth/
git commit -m "feat[phase1-eval]: phase 5 cumulative-growth report (post Track C)"
```

---

## Task 9: Final regression sweep + spec update

- [ ] **Step 1: Format + lint**

```bash
cd phase1-pablo && uv run ruff format --check . && uv run ruff check .
```

- [ ] **Step 2: Full test sweep**

```bash
cd phase1-pablo && uv run pytest tests/ -x
```

- [ ] **Step 3: Update spec success-criteria with final numbers**

Open `phase1-pablo/docs/superpowers/specs/2026-05-08-memory-system-accuracy-refactor-design.md`. The "current baseline" column has been updated through phases 0-4; now fill the **final achieved** numbers from the Phase 5 report. If any target was missed, document it in the spec under a "Deferred" section so the next iteration knows where to look.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs[phase1]: final accuracy-refactor numbers (post Phases 0-5)"
```

---

## Self-Review

| Spec deliverable (Phase 5) | Implemented in |
|----------------------------|----------------|
| C1 paradigm-scoped Variable keys | Tasks 1, 2 |
| C1 migration script | Task 3 |
| C2 content_full in payload | Task 4 |
| C3 Qdrant prune sync | Task 5 |
| C4 Reflection MERGE | Task 6 |
| C5 UNKNOWN → DUPLICATE | Task 7 |
| Re-run cumulative-growth | Task 8 |

**Placeholder check:** No "TBD". Migration verification (`missing_ids: 0`) is engineer-checked at runtime — that's a real check, not a placeholder.

**Type consistency:** `_resolve_natural_key(node) -> tuple[str, str] | None`, `_reflection_id_for(member_ids: list[str]) -> str`, `_decide_what_to_do(...) -> str` (returning one of `NEW|DUPLICATE|CORROBORATION|ENRICHMENT|CONTRADICTION`) — all consistent.

**Cross-phase notes:** Phase 4 added `delete_dense`/`delete_sparse` (used here in Task 5). Phase 0's `kg_growth_rate` predicate (added in Phase 3 plan) gives the threshold check for Task 8. The whole stack telescopes: Phase 0's foundations are still doing the measuring at Phase 5.

