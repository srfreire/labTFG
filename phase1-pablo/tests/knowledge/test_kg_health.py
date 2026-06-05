"""Tests for post-memory KG health/readability repair."""

from __future__ import annotations

import re
import uuid

import pytest

from decisionlab.knowledge.kg_health import repair_kg_health
from decisionlab.knowledge.models import ExtractionResult, NodeSpec


class _HealthFakeKG:
    def __init__(self) -> None:
        self.nodes: dict[tuple[str, str, object], dict] = {}
        self.relations: set[tuple[str, str, object, str, str, str, object]] = set()

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
            "Parameter": "name",
            "Model": "formulation_id",
        }
        if label not in schema:
            raise ValueError(f"Unknown label: {label!r}")
        return schema[label]

    def add_node(self, label: str, key: str, value: object, **props) -> None:
        self.nodes[(label, key, value)] = {key: value, **props}

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
                properties={"name": "alpha"},
                natural_key="name",
            ),
            NodeSpec(
                label="Equation",
                properties={"latex": r"\delta_t = r_t + V(s') - V(s)"},
                natural_key="latex",
            ),
            NodeSpec(
                label="Model",
                properties={"formulation_id": "actor-critic"},
                natural_key="formulation_id",
            ),
        ],
        relations=[],
        facts=[],
        stage="reasoner",
        run_id=run_id,
    )


@pytest.mark.asyncio
async def test_kg_health_repairs_readability_spine_for_stage_nodes():
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node("Variable", "id", "reinforcement-learning:td-error")
    kg.add_node("Formulation", "id", "actor-critic")
    kg.add_node("Parameter", "name", "alpha")
    kg.add_node("Equation", "latex", r"\delta_t = r_t + V(s') - V(s)")
    kg.add_node("Model", "formulation_id", "actor-critic")

    result = await repair_kg_health(_extraction(), kg)

    assert result.checked_nodes == 6
    assert result.isolated_before == 6
    assert result.isolated_after == 0
    assert result.global_isolated_after == 0
    assert result.warnings == []
    assert result.inferred_relations_created == 8

    assert (
        "Model",
        "formulation_id",
        "actor-critic",
        "IMPLEMENTS",
        "Formulation",
        "id",
        "actor-critic",
    ) in kg.relations
    assert (
        "Formulation",
        "id",
        "actor-critic",
        "HAS_PARAMETER",
        "Parameter",
        "name",
        "alpha",
    ) in kg.relations


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
async def test_kg_health_repairs_multi_formulation_scoped_nodes():
    kg = _HealthFakeKG()
    kg.add_node("Formulation", "id", "q-learning")
    kg.add_node("Formulation", "id", "actor-critic")
    kg.add_node("Parameter", "name", "alpha")
    kg.add_node("Equation", "latex", "Q <- Q + alpha * delta")
    kg.add_node("Parameter", "name", "tau")
    kg.add_node("Equation", "latex", "pi = softmax(H / tau)")

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={"id": "q-learning", "name": "Q-learning"},
                natural_key="id",
            ),
            NodeSpec(
                label="Formulation",
                properties={"id": "actor-critic", "name": "Actor-Critic"},
                natural_key="id",
            ),
            NodeSpec(
                label="Parameter",
                properties={"name": "alpha", "formulation_id": "q-learning"},
                natural_key="name",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": "Q <- Q + alpha * delta",
                    "formulation_id": "q-learning",
                },
                natural_key="latex",
            ),
            NodeSpec(
                label="Parameter",
                properties={"name": "tau", "formulation_id": "actor-critic"},
                natural_key="name",
            ),
            NodeSpec(
                label="Equation",
                properties={
                    "latex": "pi = softmax(H / tau)",
                    "formulation_id": "actor-critic",
                },
                natural_key="latex",
            ),
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id=str(uuid.uuid4()),
    )

    result = await repair_kg_health(extraction, kg)

    assert result.isolated_after == 0
    assert result.global_isolated_after == 0
    assert result.inferred_relations_created == 4
    assert (
        "Formulation",
        "id",
        "actor-critic",
        "USES_EQUATION",
        "Equation",
        "latex",
        "pi = softmax(H / tau)",
    ) in kg.relations


@pytest.mark.asyncio
async def test_kg_health_skips_wrong_belongs_to_when_stored_scope_conflicts():
    kg = _HealthFakeKG()
    kg.add_node("Paradigm", "slug", "reinforcement-learning")
    kg.add_node(
        "Formulation",
        "id",
        "Formulation 1",
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
                    "id": "Formulation 1",
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

    result = await repair_kg_health(extraction, kg)

    assert result.inferred_relations_created == 0
    assert (
        "Formulation",
        "id",
        "Formulation 1",
        "BELONGS_TO",
        "Paradigm",
        "slug",
        "reinforcement-learning",
    ) not in kg.relations
