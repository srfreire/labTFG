"""Tests for post-write graph review guardrails."""

from __future__ import annotations

import pytest

from decisionlab.knowledge.graph_review import (
    _approved_formulations,
    _deterministic_structural_patches,
    _GraphCorrections,
    _GraphRelationPatch,
    _relation_patch_is_skip,
    _validate_relation_patch,
)


def test_graph_review_corrections_coerces_json_list_strings():
    corrections = _GraphCorrections.model_validate(
        {
            "add_relations": (
                '[{"from_label":"Formulation","from_key":"id",'
                '"from_value":"reinforcement-learning:q-learning",'
                '"rel_type":"BELONGS_TO",'
                '"to_label":"Paradigm","to_key":"slug",'
                '"to_value":"reinforcement-learning"}]'
            ),
            "warnings": '["checked"]',
        }
    )

    assert corrections.add_relations[0].rel_type == "BELONGS_TO"
    assert corrections.warnings == ["checked"]


def test_graph_review_rejects_unapproved_paradigm_relation():
    relation = _GraphRelationPatch(
        from_label="Formulation",
        from_key="id",
        from_value="active-inference:bayes-threshold",
        rel_type="BELONGS_TO",
        to_label="Paradigm",
        to_key="slug",
        to_value="active-inference",
    )

    with pytest.raises(ValueError, match="outside approved context"):
        _validate_relation_patch(
            relation,
            approved_slugs={"reinforcement-learning"},
            approved_formulations=set(),
        )


def test_graph_review_rejects_noncanonical_endpoint_key():
    relation = _GraphRelationPatch(
        from_label="Formulation",
        from_key="name",
        from_value="Q-learning",
        rel_type="BELONGS_TO",
        to_label="Paradigm",
        to_key="slug",
        to_value="reinforcement-learning",
    )

    with pytest.raises(ValueError, match="not canonical"):
        _validate_relation_patch(
            relation,
            approved_slugs={"reinforcement-learning"},
            approved_formulations=set(),
        )


def test_graph_review_rejects_unknown_relation_type():
    relation = _GraphRelationPatch(
        from_label="Variable",
        from_key="id",
        from_value="reinforcement-learning:td-error-delta",
        rel_type="UPDATES",
        to_label="Variable",
        to_key="id",
        to_value="reinforcement-learning:policy",
    )

    with pytest.raises(ValueError, match="unknown relation type"):
        _validate_relation_patch(
            relation,
            approved_slugs={"reinforcement-learning"},
            approved_formulations=set(),
        )


def test_graph_review_rejects_skip_marked_relation():
    relation = _GraphRelationPatch(
        from_label="Author",
        from_key="name",
        from_value="Richard S. Sutton",
        rel_type="AUTHORED",
        to_label="Paper",
        to_key="doi",
        to_value="10.1613/jair.301",
        reason="SKIP - would require inventing authorship not directly evidenced",
    )

    assert _relation_patch_is_skip(relation)
    with pytest.raises(ValueError, match="marked as skipped"):
        _validate_relation_patch(
            relation,
            approved_slugs={"reinforcement-learning"},
            approved_formulations=set(),
        )


def test_approved_formulations_includes_local_and_scoped_ids():
    assert _approved_formulations({"reinforcement-learning": ["q-learning"]}) == {
        "q-learning",
        "reinforcement-learning:q-learning",
    }


def test_deterministic_structural_patches_anchor_isolated_variables():
    patches = _deterministic_structural_patches(
        {
            "nodes": [
                {
                    "label": "Variable",
                    "degree": 0,
                    "properties": {
                        "id": "reinforcement-learning:s-t",
                        "paradigm_slug": "reinforcement-learning",
                    },
                }
            ]
        },
        approved_slugs={"reinforcement-learning"},
    )

    assert len(patches) == 1
    assert patches[0].from_label == "Variable"
    assert patches[0].from_key == "id"
    assert patches[0].from_value == "reinforcement-learning:s-t"
    assert patches[0].rel_type == "BELONGS_TO"
    assert patches[0].to_label == "Paradigm"
    assert patches[0].to_key == "slug"
    assert patches[0].to_value == "reinforcement-learning"


def test_deterministic_structural_patches_skip_connected_or_unapproved_variables():
    patches = _deterministic_structural_patches(
        {
            "nodes": [
                {
                    "label": "Variable",
                    "degree": 1,
                    "properties": {
                        "id": "reinforcement-learning:s-t",
                        "paradigm_slug": "reinforcement-learning",
                    },
                },
                {
                    "label": "Variable",
                    "degree": 0,
                    "properties": {
                        "id": "active-inference:prediction-error",
                        "paradigm_slug": "active-inference",
                    },
                },
            ]
        },
        approved_slugs={"reinforcement-learning"},
    )

    assert patches == []
