"""Tests for kg_writer — covers AC1 through AC5."""

from __future__ import annotations

import re

import pytest

from decisionlab.knowledge.kg_writer import populate_kg
from decisionlab.knowledge.models import (
    ExtractionResult,
    KGWriteResult,
    NodeSpec,
    RelationSpec,
)

# ---------------------------------------------------------------------------
# Fake in-memory Neo4j — simulates MERGE, relation lookup, supersession
# ---------------------------------------------------------------------------


class FakeTransaction:
    """Simulates an AsyncManagedTransaction against an in-memory store."""

    def __init__(self, store: FakeNeo4jStore) -> None:
        self._store = store

    async def run(self, cypher: str, params: dict | None = None):
        params = params or {}
        return FakeResult(self._store.execute(cypher, params))


class FakeResult:
    """Wraps a list of dicts to behave like a Neo4j async Result."""

    def __init__(self, records: list[dict]) -> None:
        self._records = records

    async def single(self) -> dict | None:
        return self._records[0] if self._records else None


class FakeNeo4jStore:
    """In-memory graph store that interprets a subset of Cypher patterns."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}  # "Label:key_value" -> properties
        self.relations: list[dict] = []  # list of relation dicts
        self._rel_counter = 0

    def _node_key(self, label: str, key_prop: str, key_value) -> str:
        return f"{label}:{key_prop}={key_value}"

    def execute(self, cypher: str, params: dict) -> list[dict]:
        cypher_upper = cypher.strip().upper()

        if cypher_upper.startswith("MERGE"):
            return self._handle_merge(cypher, params)
        elif "WHERE r.valid_to IS NULL" in cypher:
            return self._handle_relation_check(cypher, params)
        elif "WHERE elementId(r)" in cypher:
            return self._handle_supersede(cypher, params)
        elif cypher_upper.startswith("MATCH") and "CREATE (a)-[r:" in cypher:
            return self._handle_create_relation(cypher, params)
        return []

    def _handle_merge(self, cypher: str, params: dict) -> list[dict]:
        """Handle MERGE (n:Label {key: $key_value}) ON CREATE/ON MATCH."""
        m = re.search(r"MERGE \(n:(\w+) \{(\w+): \$key_value\}\)", cypher)
        if not m:
            return []
        label, key_prop = m.group(1), m.group(2)
        key_value = params["key_value"]
        nk = self._node_key(label, key_prop, key_value)

        if nk in self.nodes:
            # ON MATCH path
            update_props = params.get("update_props", {})
            self.nodes[nk].update(update_props)
            run_id = params.get("run_id")
            if run_id:
                self.nodes[nk].setdefault("run_ids", [])
                self.nodes[nk]["run_ids"].append(run_id)
            return [{"was_created": False}]
        else:
            # ON CREATE path
            create_props = params.get("create_props", {})
            self.nodes[nk] = dict(create_props)
            return [{"was_created": True}]

    def _handle_relation_check(self, cypher: str, params: dict) -> list[dict]:
        """Check for existing active relation (valid_to IS NULL)."""
        from_val = params.get("from_val")
        to_val = params.get("to_val")

        for rel in self.relations:
            if (
                rel["from_val"] == from_val
                and rel["to_val"] == to_val
                and rel.get("valid_to") is None
            ):
                return [{"props": dict(rel["props"]), "rid": rel["rid"]}]
        return []

    def _handle_supersede(self, cypher: str, params: dict) -> list[dict]:
        """Set valid_to on an existing relation."""
        rid = params.get("rid")
        now = params.get("now")
        for rel in self.relations:
            if rel["rid"] == rid:
                rel["valid_to"] = now
                rel["props"]["valid_to"] = now
                return [{}]
        return []

    def _handle_create_relation(self, cypher: str, params: dict) -> list[dict]:
        """Create a new relation between matched nodes."""
        # Extract labels and key props from MATCH clause
        m = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$from_val\}\), "
            r"\(b:(\w+) \{(\w+): \$to_val\}\)",
            cypher,
        )
        if not m:
            return []

        from_label, from_key = m.group(1), m.group(2)
        to_label, to_key = m.group(3), m.group(4)
        from_val = params["from_val"]
        to_val = params["to_val"]

        # Check endpoints exist
        from_nk = self._node_key(from_label, from_key, from_val)
        to_nk = self._node_key(to_label, to_key, to_val)
        if from_nk not in self.nodes or to_nk not in self.nodes:
            return []  # endpoints not found

        self._rel_counter += 1
        rid = f"rel-{self._rel_counter}"
        props = dict(params.get("props", {}))

        # Extract rel_type from Cypher
        rm = re.search(r"CREATE \(a\)-\[r:(\w+)", cypher)
        rel_type = rm.group(1) if rm else "UNKNOWN"

        self.relations.append(
            {
                "rid": rid,
                "from_val": from_val,
                "to_val": to_val,
                "rel_type": rel_type,
                "props": props,
                "valid_to": None,
            }
        )
        return [{"rid": rid}]


class FakeKnowledgeGraph:
    """Fake KnowledgeGraph that uses an in-memory store."""

    def __init__(self, store: FakeNeo4jStore | None = None) -> None:
        self.store = store or FakeNeo4jStore()

    @staticmethod
    def unique_key_for(label: str) -> str:
        schema = {
            "Paradigm": "slug",
            "Variable": "name",
            "Equation": "latex",
            "BrainRegion": "name",
            "Author": "name",
            "Paper": "doi",
            "Postulate": "id",
            "Formulation": "id",
            "Parameter": "name",
            "Model": "formulation_id",
        }
        if label not in schema:
            raise ValueError(f"Unknown label: {label!r}")
        return schema[label]

    async def execute_write(self, work):
        tx = FakeTransaction(self.store)
        return await work(tx)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _research_extraction(run_id: str = "run-1") -> ExtractionResult:
    """Realistic ExtractionResult from a researcher stage."""
    return ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "name": "Homeostatic Regulation",
                    "slug": "homeostatic-regulation",
                    "description": "Behavior as instrument for restoring equilibrium",
                },
                natural_key="slug",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "energy_level",
                    "type": "state",
                    "range": "[0,100]",
                },
                natural_key="name",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "ghrelin",
                    "type": "molecular",
                    "range": "positive",
                },
                natural_key="name",
            ),
            NodeSpec(
                label="BrainRegion",
                properties={"name": "hypothalamus", "system": "homeostatic"},
                natural_key="name",
            ),
            NodeSpec(
                label="Paper",
                properties={
                    "title": "The Wisdom of the Body",
                    "year": 1932,
                    "doi": "10.1234/twotb",
                },
                natural_key="doi",
            ),
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "P1",
                    "statement": "Every living system has set points",
                    "falsifiable": True,
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "P2",
                    "statement": "Deviations generate error signals",
                    "falsifiable": True,
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Postulate",
                from_key_value="P1",
                to_label="Paradigm",
                to_key_value="homeostatic-regulation",
                rel_type="BELONGS_TO",
                properties={},
            ),
            RelationSpec(
                from_label="Postulate",
                from_key_value="P2",
                to_label="Paradigm",
                to_key_value="homeostatic-regulation",
                rel_type="BELONGS_TO",
                properties={},
            ),
            RelationSpec(
                from_label="Paper",
                from_key_value="10.1234/twotb",
                to_label="Postulate",
                to_key_value="P1",
                rel_type="SUPPORTS",
                properties={
                    "confidence": 0.9,
                    "quote": "set points exist in all organisms",
                },
            ),
            RelationSpec(
                from_label="Variable",
                from_key_value="ghrelin",
                to_label="BrainRegion",
                to_key_value="hypothalamus",
                rel_type="MEASURES",
                properties={"mechanism": "hormonal signaling"},
            ),
        ],
        facts=["Ghrelin modulates hunger via hypothalamus"],
        stage="researcher",
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# AC1: Populating from ExtractionResult creates all expected nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac1_creates_all_expected_nodes():
    """AC1: populate_kg creates all nodes from ExtractionResult in Neo4j."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()

    result = await populate_kg(extraction, kg)

    assert isinstance(result, KGWriteResult)
    assert (
        result.nodes_created == 7
    )  # 1 paradigm + 2 vars + 1 region + 1 paper + 2 postulates
    assert result.nodes_merged == 0
    assert result.errors == []

    # Verify specific nodes exist in the store
    store = kg.store
    assert "Paradigm:slug=homeostatic-regulation" in store.nodes
    assert "Variable:name=energy_level" in store.nodes
    assert "Variable:name=ghrelin" in store.nodes
    assert "BrainRegion:name=hypothalamus" in store.nodes
    assert "Paper:doi=10.1234/twotb" in store.nodes
    assert "Postulate:id=P1" in store.nodes
    assert "Postulate:id=P2" in store.nodes


@pytest.mark.asyncio
async def test_ac1_creates_relations():
    """AC1: populate_kg creates all expected relations."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()

    result = await populate_kg(extraction, kg)

    assert result.relations_created == 4
    assert result.relations_superseded == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_ac1_relations_carry_provenance():
    """AC1+AC4: All created relations carry run_id, created_at, valid_from."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()

    await populate_kg(extraction, kg)

    for rel in kg.store.relations:
        props = rel["props"]
        assert "run_id" in props, f"Relation missing run_id: {rel}"
        assert "created_at" in props, f"Relation missing created_at: {rel}"
        assert "valid_from" in props, f"Relation missing valid_from: {rel}"
        assert props["run_id"] == "run-1"


# ---------------------------------------------------------------------------
# AC2: Second run merges nodes, skips duplicate relations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac2_second_run_merges_nodes():
    """AC2: Running same ExtractionResult twice merges nodes (no duplicates)."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction(run_id="run-1")

    result1 = await populate_kg(extraction, kg)
    assert result1.nodes_created == 7
    assert result1.nodes_merged == 0

    # Second run with same data
    extraction2 = _research_extraction(run_id="run-2")
    result2 = await populate_kg(extraction2, kg)

    assert result2.nodes_created == 0
    assert result2.nodes_merged == 7
    assert result2.errors == []


@pytest.mark.asyncio
async def test_ac2_second_run_skips_duplicate_relations():
    """AC2: Second run skips relations with identical properties."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction(run_id="run-1")

    result1 = await populate_kg(extraction, kg)
    assert result1.relations_created == 4

    # Second run — same extraction, same properties
    extraction2 = _research_extraction(run_id="run-2")
    result2 = await populate_kg(extraction2, kg)

    # Relations with identical non-temporal props should be skipped
    assert result2.relations_created == 0
    assert result2.relations_superseded == 0


# ---------------------------------------------------------------------------
# AC3: Modified ExtractionResult supersedes old relations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac3_modified_relation_supersedes_old():
    """AC3: Changed relation confidence → old gets valid_to, new created."""
    kg = FakeKnowledgeGraph()
    extraction1 = _research_extraction(run_id="run-1")
    await populate_kg(extraction1, kg)

    # Second run with modified confidence on SUPPORTS relation
    extraction2 = ExtractionResult(
        nodes=extraction1.nodes,
        relations=[
            RelationSpec(
                from_label="Paper",
                from_key_value="10.1234/twotb",
                to_label="Postulate",
                to_key_value="P1",
                rel_type="SUPPORTS",
                properties={
                    "confidence": 0.95,
                    "quote": "updated evidence for set points",
                },
            ),
        ],
        facts=[],
        stage="researcher",
        run_id="run-2",
    )
    result2 = await populate_kg(extraction2, kg)

    assert result2.relations_superseded == 1
    assert result2.relations_created == 1

    # Old relation should have valid_to set
    superseded = [r for r in kg.store.relations if r["valid_to"] is not None]
    assert len(superseded) == 1

    # New relation should have the updated confidence
    active = [
        r
        for r in kg.store.relations
        if r["valid_to"] is None and r["rel_type"] == "SUPPORTS"
    ]
    assert len(active) == 1
    assert active[0]["props"]["confidence"] == 0.95


# ---------------------------------------------------------------------------
# AC4: All relations carry temporal and provenance metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac4_relations_carry_metadata():
    """AC4: Every relation has run_id, created_at, confidence, valid_from."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()

    await populate_kg(extraction, kg)

    for rel in kg.store.relations:
        props = rel["props"]
        assert "run_id" in props
        assert "created_at" in props
        assert "valid_from" in props
    # The SUPPORTS relation should also have confidence
    supports = [r for r in kg.store.relations if r["rel_type"] == "SUPPORTS"]
    assert len(supports) == 1
    assert supports[0]["props"]["confidence"] == 0.9


# ---------------------------------------------------------------------------
# AC5: Transaction failure returns KGWriteResult with errors, not exception
# ---------------------------------------------------------------------------


class FailingFakeKnowledgeGraph(FakeKnowledgeGraph):
    """A KG that raises during execute_write to simulate transaction failure."""

    async def execute_write(self, work):
        raise RuntimeError("Neo4j connection lost")


@pytest.mark.asyncio
async def test_ac5_transaction_failure_returns_errors():
    """AC5: Transaction failure returns KGWriteResult with errors, not exception."""
    kg = FailingFakeKnowledgeGraph()
    extraction = _research_extraction()

    result = await populate_kg(extraction, kg)

    assert isinstance(result, KGWriteResult)
    assert result.nodes_created == 0
    assert result.nodes_merged == 0
    assert result.relations_created == 0
    assert result.relations_superseded == 0
    assert len(result.errors) >= 1
    assert "Neo4j connection lost" in result.errors[0]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_extraction_returns_zero_counts():
    """Empty ExtractionResult produces zero-count KGWriteResult."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[], relations=[], facts=[], stage="researcher", run_id="run-0"
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 0
    assert result.nodes_merged == 0
    assert result.relations_created == 0
    assert result.relations_superseded == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_node_with_missing_natural_key_falls_back_to_other_property():
    """When the declared natural_key is absent, the writer should fall back to
    a known identifier property (slug/id/doi/url/name/title) instead of
    silently dropping the node — see the #4 fallback in kg_writer."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(label="Paradigm", properties={"name": "Test"}, natural_key="slug"),
            # "slug" is missing → fall back to "name"
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-err",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_node_with_no_usable_key_synthesizes_one():
    """When neither the declared natural_key nor any fallback property is
    present but properties exist, the writer should synthesize a stable id."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"foo": "bar", "baz": 42},
                natural_key="slug",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-syn",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_node_with_no_properties_at_all_reports_error():
    """A node with no properties has nothing to hash — still an error."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(label="Paradigm", properties={}, natural_key="slug"),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-empty",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 0
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_relation_with_missing_endpoint_reports_error():
    """Relation referencing non-existent node reports an error."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[],
        relations=[
            RelationSpec(
                from_label="Paper",
                from_key_value="nonexistent-doi",
                to_label="Postulate",
                to_key_value="P1",
                rel_type="SUPPORTS",
                properties={"confidence": 0.5},
            ),
        ],
        facts=[],
        stage="researcher",
        run_id="run-err",
    )

    result = await populate_kg(extraction, kg)

    assert result.relations_created == 0
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_node_merge_preserves_created_at():
    """Merged node preserves original created_at from first creation."""
    kg = FakeKnowledgeGraph()
    ext1 = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Variable",
                properties={"name": "dopamine", "type": "molecular"},
                natural_key="name",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    await populate_kg(ext1, kg)

    original_created = kg.store.nodes["Variable:name=dopamine"]["created_at"]

    ext2 = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Variable",
                properties={"name": "dopamine", "type": "neurotransmitter"},
                natural_key="name",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-2",
    )
    await populate_kg(ext2, kg)

    node = kg.store.nodes["Variable:name=dopamine"]
    assert node["created_at"] == original_created  # preserved from first creation
    assert node["type"] == "neurotransmitter"  # updated property
    assert "run-2" in node.get("run_ids", [])


# ---------------------------------------------------------------------------
# Cypher injection guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_node_label_rejected():
    """Node with malicious/malformed label is rejected, not interpolated into Cypher."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm} DETACH DELETE n //",
                properties={"slug": "injected"},
                natural_key="slug",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-inj",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 0
    assert len(result.errors) == 1
    assert "invalid label" in result.errors[0].lower()


@pytest.mark.asyncio
async def test_invalid_rel_type_rejected():
    """Relation with malformed rel_type is rejected."""
    kg = FakeKnowledgeGraph()
    # Create valid nodes first
    ext_nodes = ExtractionResult(
        nodes=[
            NodeSpec(label="Paradigm", properties={"slug": "test"}, natural_key="slug"),
            NodeSpec(
                label="Postulate",
                properties={"id": "P1", "statement": "x"},
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    await populate_kg(ext_nodes, kg)

    ext_rels = ExtractionResult(
        nodes=[],
        relations=[
            RelationSpec(
                from_label="Postulate",
                from_key_value="P1",
                to_label="Paradigm",
                to_key_value="test",
                rel_type="BELONGS_TO} DELETE r //",
                properties={},
            ),
        ],
        facts=[],
        stage="researcher",
        run_id="run-2",
    )

    result = await populate_kg(ext_rels, kg)

    assert result.relations_created == 0
    assert len(result.errors) == 1
    assert "invalid rel_type" in result.errors[0].lower()


@pytest.mark.asyncio
async def test_invalid_from_label_rejected():
    """Relation with malformed from_label is rejected."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[],
        relations=[
            RelationSpec(
                from_label="Bad Label!",
                from_key_value="x",
                to_label="Paradigm",
                to_key_value="y",
                rel_type="SUPPORTS",
                properties={},
            ),
        ],
        facts=[],
        stage="researcher",
        run_id="run-bad",
    )

    result = await populate_kg(extraction, kg)

    assert result.relations_created == 0
    assert len(result.errors) == 1
    assert "invalid from_label" in result.errors[0].lower()


@pytest.mark.asyncio
async def test_node_with_updated_at_in_properties_counts_as_created():
    """Node whose properties contain 'updated_at' is still correctly counted as created."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Variable",
                properties={
                    "name": "serotonin",
                    "type": "molecular",
                    "updated_at": "stale",
                },
                natural_key="name",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 1
    assert result.nodes_merged == 0
