"""Tests for kg_writer — covers AC1 through AC5."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest

from decisionlab.knowledge import kg_writer
from decisionlab.knowledge.kg_writer import populate_kg
from decisionlab.knowledge.models import (
    ExtractionResult,
    KGWriteResult,
    NodeSpec,
    RelationSpec,
)
from shared.pipeline_memories import memory_content_hash


@pytest.fixture(autouse=True)
def _stub_node_run_observation(monkeypatch):
    """Suppress the Postgres insert by default.

    Tests that need to verify the side-effect override this with their own
    recorder (see ``test_node_run_observation_records_per_merge``).
    """

    async def _noop(**_kwargs):
        return None

    monkeypatch.setattr(kg_writer, "_record_node_run_observation", _noop)


def test_node_create_props_drops_nulls_inside_lists():
    props = kg_writer._node_create_props(
        {
            "id": "p1",
            "range": ["0", None, "1"],
            "failure_reason": None,
            "metadata": {"unsupported": "map"},
        },
        now="2026-06-06T00:00:00+00:00",
    )

    assert props["range"] == ["0", "1"]
    assert "failure_reason" not in props
    assert "metadata" not in props


class _FakePGStore:
    """In-memory ``pipeline_memories`` analog for kg_writer relation tests.

    Simulates the three PG helpers (``_create_relation_memory``,
    ``_close_memory``, ``_fetch_active_memory_meta``) so the AC3
    supersession path stays exercisable without hitting Postgres.
    """

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, dict] = {}

    async def create(
        self,
        *,
        run_id: uuid.UUID,
        stage: str,
        content: str,
        confidence: float,
        importance: float,
        properties: dict,
        valid_from,
        db=None,
    ) -> uuid.UUID:
        new_id = uuid.uuid4()
        self.rows[new_id] = {
            "run_id": run_id,
            "stage": stage,
            "content": content,
            "confidence": confidence,
            "importance": importance,
            "properties": dict(properties),
            "valid_from": valid_from,
            "valid_to": None,
        }
        return new_id

    async def close(self, memory_id: uuid.UUID, *, valid_to, db=None) -> bool:
        row = self.rows.get(memory_id)
        if row is None or row.get("valid_to") is not None:
            return False
        row["valid_to"] = valid_to
        return True

    async def fetch_active(self, memory_ids: list[str], *, db=None) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for mid_str in memory_ids:
            try:
                mid = uuid.UUID(str(mid_str))
            except (ValueError, TypeError):
                continue
            row = self.rows.get(mid)
            if row is None or row.get("valid_to") is not None:
                continue
            out[str(mid)] = {
                "content": row["content"],
                "properties": row["properties"],
            }
        return out


@pytest.fixture
def pg_store(monkeypatch):
    """Wire an in-memory ``_FakePGStore`` over kg_writer's PG helpers.

    Use in tests that need PG-backed semantics (idempotency check, AC3
    supersession). Leaving the fixture out keeps PG unavailable so the
    writer falls back to the no-PG degraded path (relations get no
    memory_id, supersession can't be tracked).
    """
    store = _FakePGStore()
    monkeypatch.setattr(kg_writer, "_create_relation_memory", store.create)
    monkeypatch.setattr(kg_writer, "_close_memory", store.close)
    monkeypatch.setattr(kg_writer, "_fetch_active_memory_meta", store.fetch_active)
    return store


@pytest.mark.asyncio
async def test_create_relation_memory_populates_content_hash():
    captured: dict = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _stmt, params):
            captured["params"] = params

        async def commit(self):
            captured["committed"] = True

    class FakeDB:
        def get_session(self):
            return FakeSession()

    content = "Paradigm.foo -[BELONGS_TO]-> Paradigm.bar"

    memory_id = await kg_writer._create_relation_memory(
        run_id=uuid.uuid4(),
        stage="researcher",
        content=content,
        confidence=0.7,
        importance=5.0,
        properties={"source": "test"},
        valid_from=datetime.now(UTC),
        db=FakeDB(),
    )

    assert memory_id is not None
    assert captured["params"]["content_hash"] == memory_content_hash(content)
    assert captured["committed"] is True


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

    def __aiter__(self):
        async def _agen():
            for r in self._records:
                yield r

        return _agen()


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
        elif cypher_upper.startswith("MATCH (F:FORMULATION)"):
            return self._handle_formulation_local_lookup(params)
        elif "RETURN R.MEMORY_ID AS MEMORY_ID, PROPERTIES(R)" in cypher_upper:
            return self._handle_relation_list(cypher, params)
        elif cypher_upper.startswith("MATCH") and "MERGE (a)-[r:" in cypher:
            return self._handle_merge_relation(cypher, params)
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
            # ON MATCH path: lifecycle refresh plus fill-only semantic props.
            now = params.get("now")
            if now is not None:
                self.nodes[nk]["updated_at"] = now
                self.nodes[nk]["last_run_at"] = now
            for prop, value in params.get("match_props", {}).items():
                if self.nodes[nk].get(prop) is None:
                    self.nodes[nk][prop] = value
            self.nodes[nk]["run_count"] = self.nodes[nk].get("run_count", 0) + 1
            return [{"was_created": False}]
        else:
            # ON CREATE path
            create_props = params.get("create_props", {})
            self.nodes[nk] = dict(create_props)
            return [{"was_created": True}]

    def _handle_relation_list(self, cypher: str, params: dict) -> list[dict]:
        """Return all relations matching identity (P4-004 list query)."""
        from_val = params.get("from_val")
        to_val = params.get("to_val")
        rm = re.search(r"-\[r:(\w+)\]->", cypher)
        rel_type = rm.group(1) if rm else None
        out: list[dict] = []
        for rel in self.relations:
            if (
                rel["from_val"] == from_val
                and rel["to_val"] == to_val
                and (rel_type is None or rel.get("rel_type") == rel_type)
            ):
                props = dict(rel["props"])
                out.append(
                    {
                        "memory_id": props.get("memory_id"),
                        "props": props,
                    }
                )
        return out

    def _handle_formulation_local_lookup(self, params: dict) -> list[dict]:
        local_id = params.get("local_id")
        scoped_suffix = params.get("scoped_suffix")
        out: list[dict] = []
        for key, props in self.nodes.items():
            if not key.startswith("Formulation:"):
                continue
            formulation_id = props.get("id")
            if (
                props.get("local_id") == local_id
                or formulation_id == local_id
                or (
                    isinstance(formulation_id, str)
                    and isinstance(scoped_suffix, str)
                    and formulation_id.endswith(scoped_suffix)
                )
            ):
                out.append({"id": formulation_id})
            if len(out) >= 2:
                break
        return out

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
                "from_label": from_label,
                "from_key": from_key,
                "from_val": from_val,
                "to_label": to_label,
                "to_key": to_key,
                "to_val": to_val,
                "rel_type": rel_type,
                "props": props,
                "valid_to": None,
            }
        )
        return [{"rid": rid}]

    def _handle_merge_relation(self, cypher: str, params: dict) -> list[dict]:
        """Handle MERGE (a)-[r:TYPE {identity_hash: $identity_hash}]->(b)."""
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
        from_nk = self._node_key(from_label, from_key, from_val)
        to_nk = self._node_key(to_label, to_key, to_val)
        if from_nk not in self.nodes or to_nk not in self.nodes:
            return []

        rm = re.search(r"MERGE \(a\)-\[r:(\w+)", cypher)
        rel_type = rm.group(1) if rm else "UNKNOWN"
        identity_hash = params.get("identity_hash")
        for rel in self.relations:
            if (
                rel["from_val"] == from_val
                and rel["to_val"] == to_val
                and rel["rel_type"] == rel_type
                and rel["props"].get("identity_hash") == identity_hash
            ):
                return [{"rid": rel["rid"], "created": False}]

        self._rel_counter += 1
        rid = f"rel-{self._rel_counter}"
        props = dict(params.get("props", {}))
        props.setdefault("identity_hash", identity_hash)
        self.relations.append(
            {
                "rid": rid,
                "from_label": from_label,
                "from_key": from_key,
                "from_val": from_val,
                "to_label": to_label,
                "to_key": to_key,
                "to_val": to_val,
                "rel_type": rel_type,
                "props": props,
                "valid_to": None,
            }
        )
        return [{"rid": rid, "created": True}]


class FakeKnowledgeGraph:
    """Fake KnowledgeGraph that uses an in-memory store."""

    def __init__(self, store: FakeNeo4jStore | None = None) -> None:
        self.store = store or FakeNeo4jStore()

    @staticmethod
    def unique_key_for(label: str) -> str:
        schema = {
            "Paradigm": "slug",
            "Variable": "id",
            "Equation": "latex",
            "BrainRegion": "name",
            "Author": "name",
            "Paper": "doi",
            "Postulate": "id",
            "Formulation": "id",
            "Parameter": "id",
            "Model": "formulation_id",
        }
        if label not in schema:
            raise ValueError(f"Unknown label: {label!r}")
        return schema[label]

    async def execute_write(self, work):
        tx = FakeTransaction(self.store)
        return await work(tx)

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        return self.store.execute(cypher, params or {})


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
                    "paradigm_slug": "homeostatic-regulation",
                    "type": "state",
                    "range": "[0,100]",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "ghrelin",
                    "paradigm_slug": "homeostatic-regulation",
                    "type": "molecular",
                    "range": "positive",
                },
                natural_key="id",
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
                from_key_value="homeostatic-regulation:ghrelin",
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
    assert "Variable:id=homeostatic-regulation:energy-level" in store.nodes
    assert "Variable:id=homeostatic-regulation:ghrelin" in store.nodes
    assert "BrainRegion:name=hypothalamus" in store.nodes
    assert "Paper:doi=10.1234/twotb" in store.nodes
    assert "Postulate:id=homeostatic-regulation:P1" in store.nodes
    assert "Postulate:id=homeostatic-regulation:P2" in store.nodes


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
async def test_relation_endpoint_aliases_paper_title_to_doi():
    """Paper nodes are keyed by DOI, but extractor relations may use titles."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()
    extraction.relations[2].from_key_value = "The Wisdom of the Body"

    result = await populate_kg(extraction, kg)

    assert result.errors == []
    support = next(r for r in kg.store.relations if r["rel_type"] == "SUPPORTS")
    assert support["from_key"] == "doi"
    assert support["from_val"] == "10.1234/twotb"


@pytest.mark.asyncio
async def test_relation_endpoint_aliases_variable_name_to_composite_id():
    """Variable display names should resolve to the paradigm-scoped id."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction()
    extraction.relations[3].from_key_value = "ghrelin"

    result = await populate_kg(extraction, kg)

    assert result.errors == []
    measures = next(r for r in kg.store.relations if r["rel_type"] == "MEASURES")
    assert measures["from_key"] == "id"
    assert measures["from_val"] == "homeostatic-regulation:ghrelin"


@pytest.mark.asyncio
async def test_relation_endpoint_aliases_equation_plaintext_to_latex():
    """Equation nodes are keyed by latex, but formalizer edges may use plaintext."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={"id": "f1", "name": "Formulation 1"},
                natural_key="id",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": "e(t) = s - A(t)",
                    "plaintext": "error = setpoint minus energy",
                    "type": "algebraic",
                },
                natural_key="plaintext",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="f1",
                to_label="Equation",
                to_key_value="error = setpoint minus energy",
                rel_type="USES_EQUATION",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    result = await populate_kg(extraction, kg)

    assert result.errors == []
    edge = kg.store.relations[0]
    assert edge["to_key"] == "latex"
    assert edge["to_val"] == "e(t) = s - A(t)"


@pytest.mark.asyncio
async def test_builder_local_formulation_id_resolves_existing_scoped_formulation():
    """Builder artifacts keep local IDs, KG writes attach to scoped Formulation."""
    kg = FakeKnowledgeGraph()
    kg.store.nodes["Formulation:id=reinforcement-learning:q-learning"] = {
        "id": "reinforcement-learning:q-learning",
        "local_id": "q-learning",
        "paradigm_slug": "reinforcement-learning",
        "name": "Q-learning",
    }
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Model",
                properties={
                    "formulation_id": "q-learning",
                    "class_name": "QLearningModel",
                },
                natural_key="formulation_id",
            )
        ],
        relations=[
            RelationSpec(
                from_label="Model",
                from_key_value="q-learning",
                to_label="Formulation",
                to_key_value="q-learning",
                rel_type="IMPLEMENTS",
            )
        ],
        facts=[],
        stage="builder",
        run_id="run-1",
    )

    result = await populate_kg(extraction, kg)

    assert result.errors == []
    assert "Model:formulation_id=reinforcement-learning:q-learning" in kg.store.nodes
    edge = kg.store.relations[0]
    assert edge["from_key"] == "formulation_id"
    assert edge["from_val"] == "reinforcement-learning:q-learning"
    assert edge["to_key"] == "id"
    assert edge["to_val"] == "reinforcement-learning:q-learning"


@pytest.mark.asyncio
async def test_relation_endpoint_aliases_scoped_postulate_suffix_when_unambiguous():
    """A local P1 relation can resolve to a scoped Postulate id in the same batch."""
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"slug": "reinforcement-learning", "name": "RL"},
                natural_key="slug",
            ),
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "reinforcement-learning:P1",
                    "statement": "RPE drives learning",
                    "falsifiable": True,
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Postulate",
                from_key_value="P1",
                to_label="Paradigm",
                to_key_value="reinforcement-learning",
                rel_type="BELONGS_TO",
            )
        ],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )

    result = await populate_kg(extraction, kg)

    assert result.errors == []
    edge = kg.store.relations[0]
    assert edge["from_key"] == "id"
    assert edge["from_val"] == "reinforcement-learning:P1"


@pytest.mark.asyncio
async def test_ac1_relations_carry_memory_id_when_pg_available(pg_store):
    """P4-004 / AC1: Each relation written under a UUID run_id carries
    ``memory_id`` linking back to a fresh ``pipeline_memories`` row.

    No legacy ``run_id`` / ``created_at`` / ``valid_from`` is stamped on
    the relation — Postgres is the temporal source of truth now.
    """
    kg = FakeKnowledgeGraph()
    run_uuid = str(uuid.uuid4())
    extraction = _research_extraction(run_id=run_uuid)

    await populate_kg(extraction, kg)

    for rel in kg.store.relations:
        props = rel["props"]
        assert "memory_id" in props, f"Relation missing memory_id: {rel}"
        assert "run_id" not in props
        assert "created_at" not in props
        assert "valid_from" not in props
        assert "valid_to" not in props
        # The memory row exists in PG with the expected run_id.
        mem_row = pg_store.rows[uuid.UUID(props["memory_id"])]
        assert mem_row["run_id"] == uuid.UUID(run_uuid)


@pytest.mark.asyncio
async def test_ac1_seed_run_skips_pg_insert():
    """Non-UUID seed runs skip PG entirely; relations get no memory_id."""
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction(run_id="canonical-paradigms-seed")

    await populate_kg(extraction, kg)

    for rel in kg.store.relations:
        assert "memory_id" not in rel["props"]
        assert "run_id" not in rel["props"]
        assert "valid_from" not in rel["props"]


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
async def test_ac2_second_run_skips_duplicate_relations(pg_store):
    """AC2: Second run with identical content is idempotent — content-based
    dedup against existing Neo4j relations skips the write entirely. No
    second ``pipeline_memories`` row is created.
    """
    kg = FakeKnowledgeGraph()
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())

    result1 = await populate_kg(_research_extraction(run_id=run_a), kg)
    assert result1.relations_created == 4
    assert len(pg_store.rows) == 4

    result2 = await populate_kg(_research_extraction(run_id=run_b), kg)
    assert result2.relations_created == 0
    assert result2.relations_superseded == 0
    # No new PG rows minted on the idempotent pass.
    assert len(pg_store.rows) == 4


@pytest.mark.asyncio
async def test_relation_provenance_props_do_not_create_duplicate_edge(pg_store):
    kg = FakeKnowledgeGraph()
    run_id = str(uuid.uuid4())
    formulation_id = "reinforcement-learning:q-learning"
    variable_id = f"{formulation_id}:reward"
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={
                    "id": formulation_id,
                    "name": "Q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "reward",
                    "formulation_id": formulation_id,
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Variable",
                to_key_value=variable_id,
                rel_type="USES_VARIABLE",
                properties={},
            ),
            RelationSpec(
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Variable",
                to_key_value=variable_id,
                rel_type="USES_VARIABLE",
                properties={
                    "source": "memory_structural",
                    "reason": "child formulation_id",
                },
            ),
        ],
        facts=[],
        stage="formalizer",
        run_id=run_id,
    )

    result = await populate_kg(extraction, kg)

    assert result.relations_created == 1
    assert len(pg_store.rows) == 1
    uses_variable = [r for r in kg.store.relations if r["rel_type"] == "USES_VARIABLE"]
    assert len(uses_variable) == 1
    assert "memory_id" in uses_variable[0]["props"]
    assert "identity_hash" in uses_variable[0]["props"]


# ---------------------------------------------------------------------------
# AC3: Modified ExtractionResult supersedes old relations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac3_modified_relation_supersedes_old(pg_store):
    """AC3 (P4-004): Changed relation content → old PG row gets valid_to,
    new ``pipeline_memories`` row + new Neo4j relation created.

    Both Neo4j relations remain (each with its own memory_id); PG holds
    the supersession truth via valid_to.
    """
    kg = FakeKnowledgeGraph()
    extraction1 = _research_extraction(run_id=str(uuid.uuid4()))
    await populate_kg(extraction1, kg)
    assert len(pg_store.rows) == 4

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
        run_id=str(uuid.uuid4()),
    )
    result2 = await populate_kg(extraction2, kg)

    assert result2.relations_superseded == 1
    assert result2.relations_created == 1

    # Two SUPPORTS relations now in Neo4j: each with its own memory_id.
    supports_rels = [r for r in kg.store.relations if r["rel_type"] == "SUPPORTS"]
    assert len(supports_rels) == 2
    mids = [uuid.UUID(r["props"]["memory_id"]) for r in supports_rels]

    # In PG: exactly one of those rows is closed (valid_to set), the other
    # is the live successor.
    closed = [pg_store.rows[m] for m in mids if pg_store.rows[m]["valid_to"]]
    live = [pg_store.rows[m] for m in mids if pg_store.rows[m]["valid_to"] is None]
    assert len(closed) == 1
    assert len(live) == 1
    assert live[0]["properties"].get("quote") == "updated evidence for set points"


# ---------------------------------------------------------------------------
# AC4: All relations carry temporal and provenance metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac4_relations_carry_pg_metadata_via_memory_id(pg_store):
    """P4-004: Provenance/temporal/confidence live in ``pipeline_memories``,
    reachable from each relation via ``r.memory_id``.
    """
    kg = FakeKnowledgeGraph()
    run_uuid = str(uuid.uuid4())
    extraction = _research_extraction(run_id=run_uuid)

    await populate_kg(extraction, kg)

    for rel in kg.store.relations:
        mid = uuid.UUID(rel["props"]["memory_id"])
        row = pg_store.rows[mid]
        assert row["run_id"] == uuid.UUID(run_uuid)
        assert row["valid_from"] is not None
        assert row["valid_to"] is None
        assert row["confidence"] is not None

    # The SUPPORTS relation's PG row preserves the explicit confidence
    # passed via RelationSpec.properties (overrides the stage default).
    supports = [r for r in kg.store.relations if r["rel_type"] == "SUPPORTS"]
    assert len(supports) == 1
    supports_row = pg_store.rows[uuid.UUID(supports[0]["props"]["memory_id"])]
    assert supports_row["confidence"] == 0.9


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
                properties={
                    "name": "dopamine",
                    "paradigm_slug": "reinforcement-learning",
                    "type": "molecular",
                },
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    await populate_kg(ext1, kg)

    original_created = kg.store.nodes["Variable:id=reinforcement-learning:dopamine"][
        "created_at"
    ]

    ext2 = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Variable",
                properties={
                    "name": "dopamine",
                    "paradigm_slug": "reinforcement-learning",
                    "type": "neurotransmitter",
                },
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-2",
    )
    await populate_kg(ext2, kg)

    node = kg.store.nodes["Variable:id=reinforcement-learning:dopamine"]
    assert node["created_at"] == original_created  # preserved from first creation
    assert node["type"] == "molecular"  # semantic property preserved
    # P0-004: run provenance moved off the node — count + recency only.
    assert node["run_count"] == 2
    assert node.get("last_run_at") is not None
    # Legacy `run_ids` array no longer accumulates.
    assert "run_ids" not in node


@pytest.mark.asyncio
async def test_node_merge_fills_missing_semantic_props_without_overwriting_existing():
    """Existing node semantics are preserved; absent safe props can be enriched."""
    kg = FakeKnowledgeGraph()
    ext1 = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "reinforcement-learning",
                    "name": "Reinforcement Learning",
                    "description": "Original rich description",
                },
                natural_key="slug",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    await populate_kg(ext1, kg)

    ext2 = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "reinforcement-learning",
                    "name": "RL",
                    "description": "Weaker later wording",
                    "family": "learning",
                },
                natural_key="slug",
            ),
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id="run-2",
    )

    result = await populate_kg(ext2, kg)

    node = kg.store.nodes["Paradigm:slug=reinforcement-learning"]
    assert result.nodes_merged == 1
    assert node["name"] == "Reinforcement Learning"
    assert node["description"] == "Original rich description"
    assert node["family"] == "learning"
    assert node["run_count"] == 2
    assert node.get("updated_at") is not None


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
async def test_oversized_natural_key_rejected():
    """Natural-key value exceeding the sanity ceiling is refused.

    A 200-char "slug" is almost certainly an LLM blob accidentally promoted
    to a key (e.g. an entire postulate statement).
    """
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"slug": "x" * 200, "name": "Long Slug"},
                natural_key="slug",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-long",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 0
    assert len(result.errors) == 1
    assert "exceeds" in result.errors[0]


@pytest.mark.asyncio
async def test_long_paper_title_allowed():
    """Paper.title bypasses the slug-length ceiling.

    When DOI is null, the writer falls back to ``title`` per
    ``_resolve_natural_key`` precedence. Real paper titles routinely exceed
    80 chars; the length guard must be scoped to slug-like labels so it
    doesn't reject legitimate Paper writes (8 such false positives observed
    in the 2026-05-07 big-suites run).
    """
    kg = FakeKnowledgeGraph()
    long_title = (
        "A very long but entirely legitimate paper title about reinforcement "
        "learning, drift-diffusion processes, and the intricate dynamics of "
        "evidence accumulation under uncertainty in two-alternative tasks"
    )
    assert len(long_title) > 80
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paper",
                properties={"title": long_title, "year": 2024},
                natural_key="title",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-long-title",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_postulate_id_paradigm_scoping_prevents_collision():
    """Postulates with the same per-paradigm slot id (P1) but different paradigms
    must not collide in MERGE. The fix scopes Postulate.id to "{paradigm-slug}:P1"
    in the extraction prompt; this test asserts the writer keeps both nodes
    when IDs are properly scoped (no silent ON MATCH overwrite of the second
    paradigm's statement).
    """
    kg = FakeKnowledgeGraph()
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "reinforcement-learning:P1",
                    "statement": "reward prediction errors drive learning",
                    "falsifiable": True,
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "prospect-theory:P1",
                    "statement": "losses loom larger than gains",
                    "falsifiable": True,
                    "paradigm_slug": "prospect-theory",
                },
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-scope",
    )

    result = await populate_kg(extraction, kg)

    assert result.nodes_created == 2
    assert result.errors == []
    rl = kg.store.nodes["Postulate:id=reinforcement-learning:P1"]
    pt = kg.store.nodes["Postulate:id=prospect-theory:P1"]
    assert rl["statement"] == "reward prediction errors drive learning"
    assert pt["statement"] == "losses loom larger than gains"


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


# ---------------------------------------------------------------------------
# P0-004: run_count / last_run_at + node_run_observations replace run_ids array
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_p0004_first_merge_sets_run_count_and_last_run_at():
    """Newly created nodes carry ``run_count = 1`` and a ``last_run_at`` stamp.

    No legacy ``run_ids`` array is written.
    """
    kg = FakeKnowledgeGraph()
    extraction = _research_extraction(run_id=str(uuid.uuid4()))

    await populate_kg(extraction, kg)

    paradigm = kg.store.nodes["Paradigm:slug=homeostatic-regulation"]
    assert paradigm["run_count"] == 1
    assert isinstance(paradigm.get("last_run_at"), str)
    assert "run_ids" not in paradigm


@pytest.mark.asyncio
async def test_p0004_second_merge_increments_run_count_and_refreshes_recency():
    """Re-MERGEing the same node with a fresh run_id bumps run_count and
    overwrites last_run_at — replacing the unbounded ``run_ids`` accumulation."""
    kg = FakeKnowledgeGraph()
    run_a, run_b = str(uuid.uuid4()), str(uuid.uuid4())

    await populate_kg(_research_extraction(run_id=run_a), kg)
    paradigm = kg.store.nodes["Paradigm:slug=homeostatic-regulation"]
    last_run_first = paradigm["last_run_at"]

    await populate_kg(_research_extraction(run_id=run_b), kg)
    paradigm = kg.store.nodes["Paradigm:slug=homeostatic-regulation"]

    assert paradigm["run_count"] == 2
    assert paradigm["last_run_at"] is not None
    # last_run_at refresh stamps the current write — for two writes inside the
    # same `now()` it may match, but the property must always be set.
    assert paradigm["last_run_at"] >= last_run_first
    assert "run_ids" not in paradigm


@pytest.mark.asyncio
async def test_node_run_observation_records_per_merge(monkeypatch):
    """Every successful MERGE triggers one ``_record_node_run_observation``
    call carrying (label, key_value, run_id). The seed run_id (non-UUID) and
    Postgres unavailability are handled inside the helper itself; here we
    only verify the helper is invoked once per MERGE."""
    captured: list[dict] = []

    async def _capture(*, label, key_value, run_id, db):
        del db
        captured.append({"label": label, "key_value": key_value, "run_id": run_id})

    monkeypatch.setattr(kg_writer, "_record_node_run_observation", _capture)

    kg = FakeKnowledgeGraph()
    run_id = str(uuid.uuid4())
    extraction = _research_extraction(run_id=run_id)

    result = await populate_kg(extraction, kg)

    # One observation per accepted node (7 in the realistic extraction).
    assert len(captured) == result.nodes_created + result.nodes_merged
    assert all(call["run_id"] == run_id for call in captured)
    labels = {call["label"] for call in captured}
    assert "Paradigm" in labels and "Postulate" in labels


@pytest.mark.asyncio
async def test_record_node_run_observation_skips_non_uuid_run_id():
    """Non-UUID run_ids (e.g. ``canonical-paradigms-seed``) silently skip
    the Postgres insert — no FK violation, no log spam at error level."""
    db_called = False

    class _SentinelDB:
        def get_session(self):
            nonlocal db_called
            db_called = True
            raise AssertionError("DB must not be touched for non-UUID run_id")

    await kg_writer._record_node_run_observation(
        label="Paradigm",
        key_value="reinforcement-learning",
        run_id="canonical-paradigms-seed",
        db=_SentinelDB(),
    )

    assert db_called is False


@pytest.mark.asyncio
async def test_record_node_run_observation_skips_when_db_unavailable():
    """When ``db`` is None the helper is a quiet no-op."""
    # No exception, no return value required.
    await kg_writer._record_node_run_observation(
        label="Paradigm",
        key_value="reinforcement-learning",
        run_id=str(uuid.uuid4()),
        db=None,
    )


@pytest.mark.asyncio
async def test_record_node_run_observation_swallows_pg_failure():
    """Postgres exceptions inside the helper must not propagate — the KG
    write must still report success even if the audit row insert fails."""

    class _BrokenSession:
        async def execute(self, *_a, **_kw):
            raise RuntimeError("postgres down")

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return None

    class _BrokenDB:
        def get_session(self):
            return _BrokenSession()

    # Must not raise.
    await kg_writer._record_node_run_observation(
        label="Paradigm",
        key_value="reinforcement-learning",
        run_id=str(uuid.uuid4()),
        db=_BrokenDB(),
    )
