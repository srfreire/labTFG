"""Integration tests for KnowledgeGraph (requires Neo4j on localhost:7687).

Covers acceptance criteria AC1-AC5 from P1-001.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from shared.knowledge_graph import KnowledgeGraph
from shared.settings import load_settings

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def kg():
    """Yield a connected KnowledgeGraph and clean up all data afterwards."""
    settings = load_settings()
    client = KnowledgeGraph(
        settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD
    )
    await client.init_schema()
    yield client
    # Wipe all test data
    await client.query("MATCH (n) DETACH DELETE n")
    await client.close()


# -- AC1: init_schema idempotency -----------------------------------------------


@pytest.mark.asyncio
async def test_init_schema_creates_constraints(kg: KnowledgeGraph):
    """init_schema() creates constraints without error on a fresh Neo4j."""
    constraints = await kg.query("SHOW CONSTRAINTS YIELD name RETURN name")
    constraint_names = {r["name"] for r in constraints}
    # Spot-check a few expected constraints
    assert any("Paradigm" in n and "slug" in n for n in constraint_names)
    assert any("Paper" in n and "doi" in n for n in constraint_names)
    assert any("Postulate" in n and "id" in n for n in constraint_names)
    assert any("Formulation" in n and "id" in n for n in constraint_names)


@pytest.mark.asyncio
async def test_init_schema_is_idempotent(kg: KnowledgeGraph):
    """Calling init_schema() a second time succeeds silently."""
    # kg fixture already called init_schema once; call again
    await kg.init_schema()
    # No error = pass


@pytest.mark.asyncio
async def test_init_schema_creates_vector_indexes(kg: KnowledgeGraph):
    """P4-002: init_schema creates a native vector index for each
    slug-like label so retrieval can entity-link via
    ``db.index.vector.queryNodes``."""
    rows = await kg.query("SHOW VECTOR INDEXES YIELD name RETURN name")
    names = {r["name"] for r in rows}
    for label in ("Paradigm", "Variable", "Postulate", "Formulation", "Model"):
        assert f"{label.lower()}_embedding_idx" in names, (
            f"vector index for {label} missing — got {names}"
        )


# -- AC2: create nodes + SUPPORTS relation + query neighbors -------------------


@pytest.mark.asyncio
async def test_create_paper_postulate_supports_roundtrip(kg: KnowledgeGraph):
    """Create Paper + Postulate, link with SUPPORTS including temporal metadata, query back."""
    paper_id = await kg.create_node(
        "Paper",
        {
            "doi": "10.1234/test-paper",
            "title": "Test Paper on Reward",
            "year": 2024,
            "citation_count": 42,
            "venue": "Nature Neuroscience",
        },
    )
    assert paper_id is not None

    postulate_id = await kg.create_node(
        "Postulate",
        {
            "id": "P-TEST-001",
            "statement": "Dopamine mediates wanting, not liking",
            "falsifiable": True,
        },
    )
    assert postulate_id is not None

    await kg.create_relation(
        from_label="Paper",
        from_key="doi",
        from_value="10.1234/test-paper",
        to_label="Postulate",
        to_key="id",
        to_value="P-TEST-001",
        rel_type="SUPPORTS",
        properties={
            "confidence": 0.9,
            "quote": "Our results demonstrate...",
            "run_id": "run-001",
        },
    )

    neighbors = await kg.get_neighbors("Paper", "doi", "10.1234/test-paper")
    assert len(neighbors) >= 1
    postulate_neighbor = next(n for n in neighbors if n.get("id") == "P-TEST-001")
    assert postulate_neighbor["statement"] == "Dopamine mediates wanting, not liking"


# -- AC3: uniqueness constraints reject duplicates -----------------------------


@pytest.mark.asyncio
async def test_uniqueness_constraint_rejects_duplicate_doi(kg: KnowledgeGraph):
    """Two Papers with the same DOI are rejected."""
    await kg.create_node(
        "Paper",
        {
            "doi": "10.1234/unique-test",
            "title": "First",
            "year": 2024,
        },
    )
    with pytest.raises(Exception):  # noqa: B017  — driver raises a generic error type here
        await kg.create_node(
            "Paper",
            {
                "doi": "10.1234/unique-test",
                "title": "Duplicate",
                "year": 2025,
            },
        )


@pytest.mark.asyncio
async def test_uniqueness_constraint_rejects_duplicate_paradigm_slug(
    kg: KnowledgeGraph,
):
    """Two Paradigms with the same slug are rejected."""
    await kg.create_node(
        "Paradigm",
        {
            "slug": "homeostatic-regulation",
            "name": "Homeostatic Regulation",
        },
    )
    with pytest.raises(Exception):  # noqa: B017  — driver raises a generic error type here
        await kg.create_node(
            "Paradigm",
            {
                "slug": "homeostatic-regulation",
                "name": "Duplicate",
            },
        )


# -- AC4: get_neighbors with rel_type filter ----------------------------------


@pytest.mark.asyncio
async def test_get_neighbors_with_rel_type_filter(kg: KnowledgeGraph):
    """get_neighbors with rel_type returns only relations of that type."""
    await kg.create_node(
        "Paper",
        {
            "doi": "10.1234/filter-test",
            "title": "Filter Test",
            "year": 2024,
        },
    )
    await kg.create_node(
        "Postulate",
        {
            "id": "P-FILTER-S",
            "statement": "Supported claim",
            "falsifiable": True,
        },
    )
    await kg.create_node(
        "Postulate",
        {
            "id": "P-FILTER-C",
            "statement": "Contradicted claim",
            "falsifiable": True,
        },
    )

    await kg.create_relation(
        "Paper",
        "doi",
        "10.1234/filter-test",
        "Postulate",
        "id",
        "P-FILTER-S",
        "SUPPORTS",
        {"confidence": 0.8, "run_id": "run-002"},
    )
    await kg.create_relation(
        "Paper",
        "doi",
        "10.1234/filter-test",
        "Postulate",
        "id",
        "P-FILTER-C",
        "CONTRADICTS",
        {"confidence": 0.7, "run_id": "run-002"},
    )

    supports_only = await kg.get_neighbors(
        "Paper", "doi", "10.1234/filter-test", rel_type="SUPPORTS"
    )
    assert len(supports_only) == 1
    assert supports_only[0]["id"] == "P-FILTER-S"

    contradicts_only = await kg.get_neighbors(
        "Paper", "doi", "10.1234/filter-test", rel_type="CONTRADICTS"
    )
    assert len(contradicts_only) == 1
    assert contradicts_only[0]["id"] == "P-FILTER-C"

    all_neighbors = await kg.get_neighbors("Paper", "doi", "10.1234/filter-test")
    assert len(all_neighbors) == 2


# -- AC5: raw Cypher query ----------------------------------------------------


@pytest.mark.asyncio
async def test_query_raw_cypher(kg: KnowledgeGraph):
    """query() executes arbitrary Cypher and returns deserialized results."""
    await kg.create_node(
        "Paradigm",
        {
            "slug": "cypher-test",
            "name": "Cypher Test Paradigm",
            "description": "For testing raw queries",
        },
    )

    results = await kg.query(
        "MATCH (p:Paradigm {slug: $slug}) RETURN p.name AS name, p.description AS desc",
        {"slug": "cypher-test"},
    )
    assert len(results) == 1
    assert results[0]["name"] == "Cypher Test Paradigm"
    assert results[0]["desc"] == "For testing raw queries"


@pytest.mark.asyncio
async def test_query_returns_empty_for_no_match(kg: KnowledgeGraph):
    """query() returns empty list when nothing matches."""
    results = await kg.query(
        "MATCH (p:Paradigm {slug: $slug}) RETURN p",
        {"slug": "nonexistent"},
    )
    assert results == []


# -- get_node ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_node_returns_properties(kg: KnowledgeGraph):
    """get_node returns the node's properties as a dict."""
    await kg.create_node(
        "BrainRegion",
        {
            "name": "Nucleus Accumbens",
            "system": "hedonic",
        },
    )
    node = await kg.get_node("BrainRegion", "name", "Nucleus Accumbens")
    assert node is not None
    assert node["name"] == "Nucleus Accumbens"
    assert node["system"] == "hedonic"


@pytest.mark.asyncio
async def test_get_node_returns_none_for_missing(kg: KnowledgeGraph):
    """get_node returns None when the node doesn't exist."""
    node = await kg.get_node("BrainRegion", "name", "Nonexistent")
    assert node is None


# -- get_neighbors direction ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_neighbors_direction(kg: KnowledgeGraph):
    """get_neighbors respects direction parameter."""
    await kg.create_node(
        "Postulate",
        {
            "id": "P-DIR-001",
            "statement": "Direction test",
            "falsifiable": True,
        },
    )
    await kg.create_node(
        "Paradigm",
        {
            "slug": "dir-paradigm",
            "name": "Direction Paradigm",
        },
    )
    await kg.create_relation(
        "Postulate",
        "id",
        "P-DIR-001",
        "Paradigm",
        "slug",
        "dir-paradigm",
        "BELONGS_TO",
        {"run_id": "run-dir"},
    )

    # Outgoing from Postulate should find Paradigm
    outgoing = await kg.get_neighbors("Postulate", "id", "P-DIR-001", direction="out")
    assert len(outgoing) == 1
    assert outgoing[0]["slug"] == "dir-paradigm"

    # Incoming to Postulate should find nothing (relation goes out)
    incoming = await kg.get_neighbors("Postulate", "id", "P-DIR-001", direction="in")
    assert len(incoming) == 0


# -- Validation & error handling -----------------------------------------------


@pytest.mark.asyncio
async def test_create_node_rejects_unknown_label(kg: KnowledgeGraph):
    """create_node raises ValueError for labels not in the schema."""
    with pytest.raises(ValueError, match="Unknown label"):
        await kg.create_node("FakeLabel", {"key": "val"})


@pytest.mark.asyncio
async def test_create_relation_raises_on_missing_node(kg: KnowledgeGraph):
    """create_relation raises ValueError when an endpoint node doesn't exist."""
    await kg.create_node(
        "Paper",
        {
            "doi": "10.1234/orphan-test",
            "title": "Orphan",
            "year": 2024,
        },
    )
    with pytest.raises(ValueError, match="not found"):
        await kg.create_relation(
            "Paper",
            "doi",
            "10.1234/orphan-test",
            "Postulate",
            "id",
            "NONEXISTENT",
            "SUPPORTS",
            {"confidence": 0.5, "run_id": "run-err"},
        )


@pytest.mark.asyncio
async def test_create_relation_rejects_unknown_rel_type(kg: KnowledgeGraph):
    """create_relation raises ValueError for unknown relation types."""
    with pytest.raises(ValueError, match="Unknown relation type"):
        await kg.create_relation(
            "Paper",
            "doi",
            "x",
            "Postulate",
            "id",
            "y",
            "FAKE_REL",
            {},
        )


@pytest.mark.asyncio
async def test_get_neighbors_rejects_invalid_direction(kg: KnowledgeGraph):
    """get_neighbors raises ValueError for invalid direction."""
    with pytest.raises(ValueError, match="Invalid direction"):
        await kg.get_neighbors("Paper", "doi", "x", direction="sideways")
