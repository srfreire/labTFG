"""Integration tests for ``decisionlab.eval.kgadmin`` against live Neo4j.

Exercises the full round-trip: write a few nodes/relations via raw Cypher,
verify stats / snapshot / reset / restore. Each test wipes the graph
before and after so they don't pollute each other or the dev KG.

Marked ``integration`` so the default unit run skips them. Run with:

    docker compose up -d neo4j
    uv run pytest tests/eval/test_kgadmin_integration.py -m integration
"""

from __future__ import annotations

import pytest

import shared
from decisionlab.eval import kgadmin

pytestmark = pytest.mark.integration


@pytest.fixture
async def live_kg():
    """Bring up shared, wipe the KG, yield, then wipe again on teardown.

    The double-wipe (before *and* after) keeps each test isolated even
    when the previous test crashed mid-way, which would otherwise leak
    nodes into the next test's pre-state.
    """
    await shared.init()
    if shared.kg is None:
        await shared.shutdown()
        pytest.skip("Neo4j not reachable — start docker compose first")
    await shared.kg.query("MATCH (n) DETACH DELETE n")
    try:
        yield
    finally:
        try:
            await shared.kg.query("MATCH (n) DETACH DELETE n")
        finally:
            await shared.shutdown()


async def _seed(nodes: list[tuple[str, dict]], rels: list[tuple[str, str, str, dict]]):
    """Helper: write some nodes (label, props) and relations
    (from_slug, type, to_slug, props) directly via Cypher."""
    for label, props in nodes:
        await shared.kg.query(f"CREATE (n:{label}) SET n = $props", {"props": props})
    for from_slug, rel_type, to_slug, props in rels:
        await shared.kg.query(
            f"MATCH (a {{slug: $f}}), (b {{slug: $t}}) "
            f"CREATE (a)-[r:{rel_type}]->(b) SET r = $props",
            {"f": from_slug, "t": to_slug, "props": props},
        )


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStatsLive:
    @pytest.mark.asyncio
    async def test_empty_graph(self, live_kg):
        stats = await kgadmin.stats()
        assert stats.total_nodes == 0
        assert stats.total_relations == 0
        assert stats.by_label == {}
        assert stats.by_type == {}

    @pytest.mark.asyncio
    async def test_counts_seeded_data(self, live_kg):
        await _seed(
            nodes=[
                ("Paradigm", {"slug": "rl", "name": "Reinforcement learning"}),
                ("Paradigm", {"slug": "ddm", "name": "Drift-diffusion"}),
                ("Variable", {"slug": "energy"}),
                ("Variable", {"slug": "reward"}),
            ],
            rels=[
                ("rl", "BELONGS_TO", "energy", {"valid_from": "2026-01-01"}),
                ("rl", "BELONGS_TO", "reward", {"valid_from": "2026-01-01"}),
                # One superseded relation — should NOT appear in active counts.
                (
                    "ddm",
                    "BELONGS_TO",
                    "reward",
                    {"valid_from": "2025-01-01", "valid_to": "2026-01-01"},
                ),
            ],
        )
        stats = await kgadmin.stats()
        assert stats.total_nodes == 4
        # Per P4-004 supersession lives in PG (`pipeline_memories.valid_to`),
        # not on the relation. ``stats()`` now counts every Neo4j edge — the
        # third "superseded" seed relation is included.
        assert stats.total_relations == 3
        assert stats.by_label == {"Paradigm": 2, "Variable": 2}
        assert stats.by_type == {"BELONGS_TO": 3}


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestResetLive:
    @pytest.mark.asyncio
    async def test_deletes_everything_and_returns_count(self, live_kg):
        await _seed(
            nodes=[("Paradigm", {"slug": "x"}), ("Paradigm", {"slug": "y"})],
            rels=[],
        )
        deleted = await kgadmin.reset(confirm=True)
        assert deleted == 2
        stats = await kgadmin.stats()
        assert stats.total_nodes == 0
        assert stats.total_relations == 0


# ---------------------------------------------------------------------------
# snapshot / restore round-trip
# ---------------------------------------------------------------------------


class TestSnapshotRestoreLive:
    @pytest.mark.asyncio
    async def test_round_trip_preserves_counts(self, live_kg):
        # Seed → snapshot → wipe → restore → assert same counts.
        await _seed(
            nodes=[
                ("Paradigm", {"slug": "rl", "name": "RL"}),
                ("Variable", {"slug": "reward"}),
            ],
            rels=[("rl", "BELONGS_TO", "reward", {"valid_from": "2026-01-01"})],
        )
        snap = await kgadmin.snapshot()
        assert len(snap["nodes"]) == 2
        assert len(snap["relations"]) == 1

        await kgadmin.restore(snap, reset_first=True)

        stats = await kgadmin.stats()
        assert stats.total_nodes == 2
        assert stats.total_relations == 1
        assert stats.by_label == {"Paradigm": 1, "Variable": 1}

    @pytest.mark.asyncio
    async def test_snapshot_to_file_and_back(self, live_kg, tmp_path):
        await _seed(
            nodes=[("Paradigm", {"slug": "ddm", "name": "DDM"})],
            rels=[],
        )
        path = tmp_path / "snap.json"
        await kgadmin.snapshot_to_file(path)
        assert path.exists()
        await kgadmin.reset(confirm=True)
        await kgadmin.restore_from_file(path)
        stats = await kgadmin.stats()
        assert stats.total_nodes == 1
        assert stats.by_label == {"Paradigm": 1}


# ---------------------------------------------------------------------------
# query pass-through
# ---------------------------------------------------------------------------


class TestQueryLive:
    @pytest.mark.asyncio
    async def test_round_trips_simple_match(self, live_kg):
        await _seed(
            nodes=[("Paradigm", {"slug": "rl", "name": "RL"})],
            rels=[],
        )
        rows = await kgadmin.query(
            "MATCH (p:Paradigm {slug: $s}) RETURN p.name AS name", {"s": "rl"}
        )
        assert rows == [{"name": "RL"}]

    @pytest.mark.asyncio
    async def test_raises_when_kg_unavailable(self, live_kg, monkeypatch):
        # Temporarily blank out shared.kg to confirm the guard fires.
        monkeypatch.setattr(shared, "kg", None)
        with pytest.raises(RuntimeError, match="not initialised"):
            await kgadmin.query("RETURN 1 AS n")
