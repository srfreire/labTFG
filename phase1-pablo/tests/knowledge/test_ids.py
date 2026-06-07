"""Tests for deterministic KG identity normalization."""

from __future__ import annotations

from decisionlab.knowledge.ids import (
    align_to_approved_formulations,
    materialize_structural_relations,
    normalize_extraction_ids,
    prune_relationless_leaf_nodes,
    prune_to_approved_context,
    prune_unresolvable_relations,
)
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec


def test_parameter_relation_resolves_original_local_parameter_id_alias():
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
                label="Parameter",
                properties={
                    "id": "q-learning:alpha",
                    "name": "alpha",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="q-learning:alpha",
                rel_type="HAS_PARAMETER",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)

    parameter = next(node for node in extraction.nodes if node.label == "Parameter")
    relation = extraction.relations[0]
    assert parameter.properties["id"] == "reinforcement-learning:q-learning:alpha"
    assert relation.from_key_value == "reinforcement-learning:q-learning"
    assert relation.to_key_value == "reinforcement-learning:q-learning:alpha"


def test_parameter_derives_from_resolves_formulation_local_postulate_reference():
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
                label="Parameter",
                properties={
                    "id": "q-learning:alpha",
                    "name": "alpha",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Postulate",
                properties={
                    "id": "reinforcement-learning:P1",
                    "statement": "Prediction errors drive value updates.",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Parameter",
                from_key_value="q-learning:alpha",
                to_label="Postulate",
                to_key_value="q-learning:P1",
                rel_type="DERIVES_FROM",
            )
        ],
        facts=[],
        stage="reasoner",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)

    relation = extraction.relations[0]
    assert relation.from_key_value == "reinforcement-learning:q-learning:alpha"
    assert relation.to_key_value == "reinforcement-learning:P1"


def test_parameter_derives_from_short_postulate_uses_parameter_paradigm_scope():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Parameter",
                properties={
                    "id": "q-learning:gamma",
                    "name": "gamma",
                    "formulation_id": "reinforcement-learning:q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            )
        ],
        relations=[
            RelationSpec(
                from_label="Parameter",
                from_key_value="q-learning:gamma",
                to_label="Postulate",
                to_key_value="P3",
                rel_type="DERIVES_FROM",
            )
        ],
        facts=[],
        stage="reasoner",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)

    relation = extraction.relations[0]
    assert relation.from_key_value == "reinforcement-learning:q-learning:gamma"
    assert relation.to_key_value == "reinforcement-learning:P3"


def test_prune_relationless_leaf_nodes_keeps_connected_literature_nodes():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Author",
                properties={"name": "Connected Author"},
                natural_key="name",
            ),
            NodeSpec(
                label="Author",
                properties={"name": "Loose Author"},
                natural_key="name",
            ),
            NodeSpec(
                label="Paper",
                properties={"title": "Loose Paper"},
                natural_key="title",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "reward",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Author",
                from_key_value="Connected Author",
                to_label="Paper",
                to_key_value="Connected Paper",
                rel_type="AUTHORED",
            )
        ],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )

    prune_relationless_leaf_nodes(extraction)

    labels_and_names = {
        (node.label, node.properties.get("name") or node.properties.get("title"))
        for node in extraction.nodes
    }
    assert ("Author", "Connected Author") in labels_and_names
    assert ("Author", "Loose Author") not in labels_and_names
    assert ("Paper", "Loose Paper") not in labels_and_names
    assert ("Variable", "reward") in labels_and_names


def test_parameter_alias_resolves_symbol_display_name_relation_endpoint():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "actor-critic-softmax-policy",
                    "name": "Actor-Critic Softmax Policy",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Parameter",
                properties={
                    "id": "actor-critic-softmax-policy:alpha-v",
                    "name": "alpha_V",
                    "symbol": "alpha_V",
                    "display_name": "critic learning rate",
                    "formulation_id": "actor-critic-softmax-policy",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="actor-critic-softmax-policy",
                to_label="Parameter",
                to_key_value="alpha-V-critic-learning-rate",
                rel_type="HAS_PARAMETER",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)
    prune_unresolvable_relations(extraction)

    relation = extraction.relations[0]
    assert (
        relation.from_key_value == "reinforcement-learning:actor-critic-softmax-policy"
    )
    assert (
        relation.to_key_value
        == "reinforcement-learning:actor-critic-softmax-policy:alpha-v"
    )


def test_prune_unresolvable_relations_drops_bad_local_endpoint():
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
                label="Parameter",
                properties={
                    "id": "q-learning:alpha",
                    "name": "alpha",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="alpha",
                rel_type="HAS_PARAMETER",
            ),
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="does-not-exist",
                rel_type="HAS_PARAMETER",
            ),
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)
    prune_unresolvable_relations(extraction)

    assert len(extraction.relations) == 1
    assert (
        extraction.relations[0].to_key_value
        == "reinforcement-learning:q-learning:alpha"
    )


def test_prune_unresolvable_relations_keeps_builder_external_formulation():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Model",
                properties={
                    "formulation_id": "reinforcement-learning:q-learning",
                    "class_name": "QLearningModel",
                },
                natural_key="formulation_id",
            )
        ],
        relations=[
            RelationSpec(
                from_label="Model",
                from_key_value="reinforcement-learning:q-learning",
                to_label="Formulation",
                to_key_value="reinforcement-learning:q-learning",
                rel_type="IMPLEMENTS",
            )
        ],
        facts=[],
        stage="builder",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)
    prune_unresolvable_relations(extraction)

    assert len(extraction.relations) == 1


def test_prune_unresolvable_relations_drops_ambiguous_local_alias():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Variable",
                properties={
                    "id": "reinforcement-learning:q-learning:value",
                    "name": "value",
                    "formulation_id": "reinforcement-learning:q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "id": "optimal-foraging-theory:mvt:value",
                    "name": "value",
                    "formulation_id": "optimal-foraging-theory:mvt",
                    "paradigm_slug": "optimal-foraging-theory",
                },
                natural_key="id",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Variable",
                from_key_value="value",
                to_label="Variable",
                to_key_value="value",
                rel_type="MODULATES",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)
    prune_unresolvable_relations(extraction)

    assert extraction.relations == []


def test_materialize_structural_relations_adds_formulation_spine():
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
                label="Variable",
                properties={
                    "name": "value",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
            NodeSpec(
                label="Parameter",
                properties={
                    "name": "alpha",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
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
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    materialize_structural_relations(extraction)

    triples = {
        (
            rel.from_label,
            rel.from_key_value,
            rel.rel_type,
            rel.to_label,
            rel.to_key_value,
        )
        for rel in extraction.relations
    }
    formulation_id = "reinforcement-learning:q-learning"
    assert (
        "Formulation",
        formulation_id,
        "BELONGS_TO",
        "Paradigm",
        "reinforcement-learning",
    ) in triples
    assert (
        "Formulation",
        formulation_id,
        "USES_VARIABLE",
        "Variable",
        "reinforcement-learning:value",
    ) in triples
    assert (
        "Formulation",
        formulation_id,
        "HAS_PARAMETER",
        "Parameter",
        f"{formulation_id}:alpha",
    ) in triples
    assert (
        "Formulation",
        formulation_id,
        "USES_EQUATION",
        "Equation",
        "Q <- Q + alpha * delta",
    ) in triples
    assert not any(
        rel.from_label == "Parameter" and rel.rel_type == "BELONGS_TO"
        for rel in extraction.relations
    )


def test_variables_are_paradigm_scoped_across_formulations():
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
                    "name": "Actor Critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "delta_t",
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "δ_t (Formulation 2)",
                    "formulation_id": "actor-critic",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Variable",
                to_key_value="q-learning:delta-t",
                rel_type="USES_VARIABLE",
            ),
            RelationSpec(
                from_label="Formulation",
                from_key_value="actor-critic",
                to_label="Variable",
                to_key_value="actor-critic:delta-t",
                rel_type="USES_VARIABLE",
            ),
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)

    variable_ids = {
        node.properties["id"] for node in extraction.nodes if node.label == "Variable"
    }
    assert variable_ids == {"reinforcement-learning:delta-t"}
    assert {
        (rel.from_key_value, rel.to_key_value)
        for rel in extraction.relations
        if rel.rel_type == "USES_VARIABLE"
    } == {
        ("reinforcement-learning:q-learning", "reinforcement-learning:delta-t"),
        ("reinforcement-learning:actor-critic", "reinforcement-learning:delta-t"),
    }


def test_materialize_structural_relations_links_model_to_paradigm():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Model",
                properties={
                    "formulation_id": "reinforcement-learning:q-learning",
                    "class_name": "QLearningModel",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="formulation_id",
            )
        ],
        relations=[],
        facts=[],
        stage="builder",
        run_id="run-1",
    )

    materialize_structural_relations(extraction)

    triples = {
        (
            rel.from_label,
            rel.from_key_value,
            rel.rel_type,
            rel.to_label,
            rel.to_key_value,
        )
        for rel in extraction.relations
    }
    assert (
        "Model",
        "reinforcement-learning:q-learning",
        "IMPLEMENTS",
        "Formulation",
        "reinforcement-learning:q-learning",
    ) in triples
    assert (
        "Model",
        "reinforcement-learning:q-learning",
        "BELONGS_TO",
        "Paradigm",
        "reinforcement-learning",
    ) in triples


def test_prune_to_approved_context_drops_unapproved_scoped_nodes():
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
                    "id": "bayes-threshold",
                    "name": "Bayes Threshold",
                    "paradigm_slug": "active-inference",
                },
                natural_key="id",
            ),
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    normalize_extraction_ids(extraction)
    prune_to_approved_context(
        extraction,
        approved_paradigms=["reinforcement-learning"],
        approved_specs={"reinforcement-learning": ["q-learning"]},
    )

    assert [node.properties["id"] for node in extraction.nodes] == [
        "reinforcement-learning:q-learning"
    ]


def test_align_to_approved_formulations_rewrites_wrong_paradigm_scope():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "reinforcement-learning-forager-td-learning-with-average-reward",
                    "name": "Reinforcement Learning Forager TD Learning With Average Reward",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            NodeSpec(
                label="Variable",
                properties={
                    "name": "average reward",
                    "formulation_id": "reinforcement-learning:reinforcement-learning-forager-td-learning-with-average-reward",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="name",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="reinforcement-learning:reinforcement-learning-forager-td-learning-with-average-reward",
                to_label="Variable",
                to_key_value="reinforcement-learning:reinforcement-learning-forager-td-learning-with-average-reward:average-reward",
                rel_type="USES_VARIABLE",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    align_to_approved_formulations(
        extraction,
        approved_specs={
            "optimal-foraging-theory": [
                "reinforcement-learning-forager-td-learning-with-average-reward"
            ]
        },
    )
    normalize_extraction_ids(extraction)

    formulation_id = (
        "optimal-foraging-theory:"
        "reinforcement-learning-forager-td-learning-with-average-reward"
    )
    formulation = next(node for node in extraction.nodes if node.label == "Formulation")
    variable = next(node for node in extraction.nodes if node.label == "Variable")
    relation = extraction.relations[0]

    assert formulation.properties["id"] == formulation_id
    assert formulation.properties["paradigm_slug"] == "optimal-foraging-theory"
    assert variable.properties["formulation_id"] == formulation_id
    assert variable.properties["id"] == "optimal-foraging-theory:average-reward"
    assert relation.from_key_value == formulation_id
    assert relation.to_key_value == "optimal-foraging-theory:average-reward"


def test_prune_to_approved_context_drops_wrong_scoped_formulation_even_if_local_approved():
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "reinforcement-learning:shared-local",
                    "name": "Shared Local",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            )
        ],
        relations=[],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )

    prune_to_approved_context(
        extraction,
        approved_paradigms=["reinforcement-learning", "optimal-foraging-theory"],
        approved_specs={"optimal-foraging-theory": ["shared-local"]},
    )

    assert extraction.nodes == []
