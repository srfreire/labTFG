"""Tests for post-memory KG health/readability repair."""

from __future__ import annotations

import re
import uuid

import pytest

from decisionlab.knowledge import kg_health
from decisionlab.knowledge.kg_health import repair_kg_health
from decisionlab.knowledge.models import ExtractionResult, NodeSpec


class _HealthFakeKG:
    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str, object], dict] = {}
        self.relations: set[tuple[str, str, object, str, str, str, object]] = set()
        self.relation_props: dict[
            tuple[str, str, object, str, str, str, object], dict
        ] = {}

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

    def add_node(self, label: str, key: str, value: object, **props) -> None:
        self.nodes[(label, key, value)] = {key: value, **props}

    def add_relation(
        self,
        from_label: str,
        from_key: str,
        from_value: object,
        rel_type: str,
        to_label: str,
        to_key: str,
        to_value: object,
        **props,
    ) -> None:
        rel = (
            from_label,
            from_key,
            from_value,
            rel_type,
            to_label,
            to_key,
            to_value,
        )
        self.relations.add(rel)
        self.relation_props[rel] = dict(props)

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        params = params or {}
        if "MATCH (n) WHERE NOT (n)--()" in cypher:
            return [{"isolated": self._isolated_count()}]

        stored_scope = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$value\}\) "
            r"RETURN a\.paradigm_slug AS paradigm_slug",
            cypher,
        )
        if stored_scope:
            label, key = stored_scope.groups()
            props = self.nodes.get((label, key, params["value"]), {})
            return [{"paradigm_slug": props.get("paradigm_slug")}]

        node_degree = re.search(
            r"MATCH \(n:(\w+) \{(\w+): \$value\}\) "
            r"RETURN COUNT \{ \(n\)--\(\) \} AS degree",
            cypher,
        )
        if node_degree:
            label, key = node_degree.groups()
            return [{"degree": self._degree(label, key, params["value"])}]

        relation_list = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$from_val\}\)"
            r"-\[r:(\w+)\]->"
            r"\(b:(\w+) \{(\w+): \$to_val\}\) "
            r"RETURN r\.memory_id AS memory_id, properties\(r\) AS props",
            cypher,
        )
        if relation_list:
            from_label, from_key, rel_type, to_label, to_key = relation_list.groups()
            out: list[dict] = []
            for rel in self.relations:
                if rel == (
                    from_label,
                    from_key,
                    params["from_val"],
                    rel_type,
                    to_label,
                    to_key,
                    params["to_val"],
                ):
                    props = dict(self.relation_props.get(rel, {}))
                    out.append({"memory_id": props.get("memory_id"), "props": props})
            return out

        delete_legacy = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$from_value\}\)"
            r"-\[r:(\w+)\]->"
            r"\(b:(\w+) \{(\w+): \$to_value\}\) "
            r"WHERE r\.source = \$source AND r\.memory_id IS NULL "
            r"WITH r DELETE r RETURN count\(\*\) AS deleted",
            cypher,
        )
        if delete_legacy:
            from_label, from_key, rel_type, to_label, to_key = delete_legacy.groups()
            deleted = 0
            for rel in list(self.relations):
                if rel != (
                    from_label,
                    from_key,
                    params["from_value"],
                    rel_type,
                    to_label,
                    to_key,
                    params["to_value"],
                ):
                    continue
                props = self.relation_props.get(rel, {})
                if props.get("source") == params["source"] and not props.get(
                    "memory_id"
                ):
                    self.relations.remove(rel)
                    self.relation_props.pop(rel, None)
                    deleted += 1
            return [{"deleted": deleted}]

        endpoint_count = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$from_value\}\), "
            r"\(b:(\w+) \{(\w+): \$to_value\}\) "
            r"RETURN count\(\*\) AS endpoints",
            cypher,
        )
        if endpoint_count:
            from_label, from_key, to_label, to_key = endpoint_count.groups()
            exists = (
                from_label,
                from_key,
                params["from_value"],
            ) in self.nodes and (
                to_label,
                to_key,
                params["to_value"],
            ) in self.nodes
            return [{"endpoints": 1 if exists else 0}]

        create_rel = re.search(
            r"MATCH \(a:(\w+) \{(\w+): \$from_value\}\), "
            r"\(b:(\w+) \{(\w+): \$to_value\}\) "
            r"WHERE NOT \(a\)-\[:(\w+)\]->\(b\) "
            r"CREATE \(a\)-\[r:\5",
            cypher,
        )
        if create_rel:
            from_label, from_key, to_label, to_key, rel_type = create_rel.groups()
            from_value = params["from_value"]
            to_value = params["to_value"]
            if (from_label, from_key, from_value) not in self.nodes or (
                to_label,
                to_key,
                to_value,
            ) not in self.nodes:
                return [{"created": 0}]
            rel = (
                from_label,
                from_key,
                from_value,
                rel_type,
                to_label,
                to_key,
                to_value,
            )
            if rel in self.relations:
                return [{"created": 0}]
            self.relations.add(rel)
            self.relation_props[rel] = dict(params.get("props", {}))
            return [{"created": 1}]

        return []

    def _degree(self, label: str, key: str, value: object) -> int:
        node = (label, key, value)
        degree = 0
        for rel in self.relations:
            if rel[:3] == node or rel[4:] == node:
                degree += 1
        return degree

    def _isolated_count(self) -> int:
        return sum(
            1
            for label, key, value in self.nodes
            if self._degree(label, key, value) == 0
        )


class _HealthPGStore:
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
        del db
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
        del db
        row = self.rows.get(memory_id)
        if row is None or row.get("valid_to") is not None:
            return False
        row["valid_to"] = valid_to
        return True


@pytest.fixture
def lifecycle_store(monkeypatch):
    store = _HealthPGStore()
    monkeypatch.setattr(kg_health, "_create_relation_memory", store.create)
    monkeypatch.setattr(kg_health, "_close_memory", store.close)
    return store


def _extraction() -> ExtractionResult:
    run_id = str(uuid.uuid4())
    return ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"slug": "reinforcement-learning", "name": "RL"},
                natural_key="slug",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "TD error",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "actor-critic",
                    "name": "Actor-Critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Parameter",
                properties={
                    "name": "alpha",
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": r"\delta_t = r_t + V(s') - V(s)",
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="latex",
            ),
            NodeSpec(
                label="Model",
                properties={
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="formulation_id",
            ),
        ],
        relations=[],
        facts=[],
        stage="reasoner",
        run_id=run_id,
    )


@pytest.mark.asyncio
async def test_kg_health_repairs_readability_spine_for_stage_nodes(lifecycle_store):
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node("Variable", "id", "reinforcement-learning:td-error")
    kg.add_node("Formulation", "id", "reinforcement-learning:actor-critic")
    kg.add_node("Parameter", "id", "reinforcement-learning:actor-critic:alpha")
    kg.add_node("Equation", "latex", r"\delta_t = r_t + V(s') - V(s)")
    kg.add_node("Model", "formulation_id", "reinforcement-learning:actor-critic")
    extraction = _extraction()

    result = await repair_kg_health(extraction, kg, db=object())

    assert result.checked_nodes == 6
    assert result.isolated_before == 6
    assert result.isolated_after == 0
    assert result.global_isolated_after == 0
    assert result.warnings == []
    assert result.inferred_relations_created == 8

    assert (
        "Model",
        "formulation_id",
        "reinforcement-learning:actor-critic",
        "IMPLEMENTS",
        "Formulation",
        "id",
        "reinforcement-learning:actor-critic",
    ) in kg.relations
    assert (
        "Formulation",
        "id",
        "reinforcement-learning:actor-critic",
        "HAS_PARAMETER",
        "Parameter",
        "id",
        "reinforcement-learning:actor-critic:alpha",
    ) in kg.relations

    assert len(lifecycle_store.rows) == 8
    for props in kg.relation_props.values():
        assert uuid.UUID(props["memory_id"]) in lifecycle_store.rows
        assert props["source"] == "kg_health"
        assert "run_id" not in props
        assert "valid_from" not in props
        assert "valid_to" not in props
    assert all(
        row["run_id"] == uuid.UUID(extraction.run_id)
        and row["valid_to"] is None
        and row["properties"]["source"] == "kg_health"
        for row in lifecycle_store.rows.values()
    )


@pytest.mark.asyncio
async def test_kg_health_skips_inferred_edges_without_db():
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node("Variable", "id", "reinforcement-learning:td-error")
    kg.add_node("Formulation", "id", "reinforcement-learning:actor-critic")
    kg.add_node("Parameter", "id", "reinforcement-learning:actor-critic:alpha")
    kg.add_node("Equation", "latex", r"\delta_t = r_t + V(s') - V(s)")
    kg.add_node("Model", "formulation_id", "reinforcement-learning:actor-critic")

    result = await repair_kg_health(_extraction(), kg)

    assert result.inferred_relations_created == 0
    assert kg.relations == set()
    assert result.isolated_after == 6


@pytest.mark.asyncio
async def test_kg_health_removes_legacy_timeless_health_edge_without_db():
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node("Variable", "id", "reinforcement-learning:td-error")
    kg.add_relation(
        "Variable",
        "id",
        "reinforcement-learning:td-error",
        "BELONGS_TO",
        "Paradigm",
        "slug",
        "reinforcement-learning",
        source="kg_health",
        reason="legacy",
    )

    result = await repair_kg_health(_extraction(), kg)

    assert result.inferred_relations_created == 0
    assert kg.relations == set()


@pytest.mark.asyncio
async def test_kg_health_preserves_seed_memoryless_edge(lifecycle_store):
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node("Variable", "id", "reinforcement-learning:td-error")
    kg.add_relation(
        "Variable",
        "id",
        "reinforcement-learning:td-error",
        "BELONGS_TO",
        "Paradigm",
        "slug",
        "reinforcement-learning",
    )

    result = await repair_kg_health(_extraction(), kg, db=object())

    assert result.inferred_relations_created == 0
    assert (
        "Variable",
        "id",
        "reinforcement-learning:td-error",
        "BELONGS_TO",
        "Paradigm",
        "slug",
        "reinforcement-learning",
    ) in kg.relations
    assert lifecycle_store.rows == {}


@pytest.mark.asyncio
async def test_kg_health_reports_unrepairable_unscoped_nodes():
    kg = _HealthFakeKG()
    kg.add_node("Author", "name", "Ada Lovelace")
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Author",
                properties={"name": "Ada Lovelace"},
                natural_key="name",
            )
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id=str(uuid.uuid4()),
    )

    result = await repair_kg_health(extraction, kg)

    assert result.isolated_before == 1
    assert result.isolated_after == 1
    assert result.global_isolated_after == 1
    assert result.inferred_relations_created == 0
    assert result.warnings == [
        "1 node(s) from this extraction remain isolated",
        "1 total KG node(s) remain isolated",
    ]


@pytest.mark.asyncio
async def test_kg_health_repairs_multi_formulation_scoped_nodes(lifecycle_store):
    kg = _HealthFakeKG()
    kg.add_node("Formulation", "id", "reinforcement-learning:q-learning")
    kg.add_node("Formulation", "id", "reinforcement-learning:actor-critic")
    kg.add_node("Parameter", "id", "reinforcement-learning:q-learning:alpha")
    kg.add_node("Equation", "latex", "Q <- Q + alpha * delta")
    kg.add_node("Parameter", "id", "reinforcement-learning:actor-critic:tau")
    kg.add_node("Equation", "latex", "pi = softmax(H / tau)")

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "q-learning",
                    "name": "Q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "actor-critic",
                    "name": "Actor-Critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Parameter",
                properties={
                    "name": "alpha",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": "Q <- Q + alpha * delta",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="latex",
            ),
            NodeSpec(
                label="Parameter",
                properties={
                    "name": "tau",
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": "pi = softmax(H / tau)",
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="latex",
            ),
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id=str(uuid.uuid4()),
    )

    result = await repair_kg_health(extraction, kg, db=object())

    assert result.isolated_after == 0
    assert result.global_isolated_after == 0
    assert result.inferred_relations_created == 4
    assert len(lifecycle_store.rows) == 4
    assert (
        "Formulation",
        "id",
        "reinforcement-learning:actor-critic",
        "USES_EQUATION",
        "Equation",
        "latex",
        "pi = softmax(H / tau)",
    ) in kg.relations


@pytest.mark.asyncio
async def test_kg_health_skips_wrong_belongs_to_when_stored_scope_conflicts(
    lifecycle_store,
):
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node(
        "Formulation",
        "id",
        "reinforcement-learning:colliding-formulation-id",
        paradigm_slug="optimal-foraging-theory",
    )

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "reinforcement-learning",
                    "name": "Reinforcement Learning",
                },
                natural_key="slug",
            ),
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "reinforcement-learning:colliding-formulation-id",
                    "name": "Colliding formulation id",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id=str(uuid.uuid4()),
    )

    result = await repair_kg_health(extraction, kg, db=object())

    assert result.inferred_relations_created == 0
    assert lifecycle_store.rows == {}
    assert (
        "Formulation",
        "id",
        "reinforcement-learning:colliding-formulation-id",
        "BELONGS_TO",
        "Paradigm",
        "slug",
        "reinforcement-learning",
    ) not in kg.relations
