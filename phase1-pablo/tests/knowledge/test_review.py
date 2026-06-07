"""Tests for the LLM review/correction memory pass."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import decisionlab.knowledge.review as review_module
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.knowledge.review import (
    _apply_corrections,
    _NodePatch,
    _ReviewCorrections,
    _ReviewNode,
    _ReviewRelation,
    review_and_correct_extraction,
)


def _extraction() -> ExtractionResult:
    return ExtractionResult(
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
                properties={"name": "alpha"},
                natural_key="name",
            ),
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="beta",
                rel_type="HAS_PARAMETER",
            )
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )


def test_review_corrections_coerces_json_list_strings():
    corrections = _ReviewCorrections.model_validate(
        {
            "add_nodes": '[{"label":"Variable","properties":{"id":"v1"},"natural_key":"id"}]',
            "add_relations": "[]",
            "notes": '["coerced"]',
        }
    )

    assert corrections.add_nodes[0].label == "Variable"
    assert corrections.add_relations == []
    assert corrections.notes == ["coerced"]


def test_review_corrections_drops_malformed_json_list_strings():
    corrections = _ReviewCorrections.model_validate(
        {
            "add_nodes": '[{"label": "Variable", bad json]',
            "add_relations": "[]",
        }
    )

    assert corrections.add_nodes == []
    assert corrections.add_relations == []


@pytest.mark.asyncio
async def test_review_applies_node_patch_relation_remove_and_relation_add():
    corrections = _ReviewCorrections(
        update_nodes=[
            _NodePatch(
                label="Parameter",
                key="name",
                value="alpha",
                properties={
                    "formulation_id": "q-learning",
                    "paradigm_slug": "reinforcement-learning",
                    "source": "Sutton & Barto",
                },
                reason="Parameter table belongs to Q-learning formulation.",
            )
        ],
        remove_relations=[
            _ReviewRelation(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="beta",
                rel_type="HAS_PARAMETER",
            )
        ],
        add_relations=[
            _ReviewRelation(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="alpha",
                rel_type="HAS_PARAMETER",
            )
        ],
    )

    with patch(
        "decisionlab.knowledge.review.call_structured",
        new_callable=AsyncMock,
        return_value=corrections,
    ) as mocked:
        result = await review_and_correct_extraction(
            _extraction(),
            stage_output="## Formulation 1: Q-learning\n| alpha |",
            client=AsyncMock(),
        )

    mocked.assert_awaited_once()
    parameter = next(node for node in result.nodes if node.label == "Parameter")
    formulation_id = "reinforcement-learning:q-learning"
    assert parameter.natural_key == "id"
    assert parameter.properties["formulation_id"] == formulation_id
    assert parameter.properties["id"] == f"{formulation_id}:alpha"
    assert parameter.properties["source"] == "Sutton & Barto"

    assert all(rel.to_key_value != "beta" for rel in result.relations)
    assert any(
        rel.from_label == "Formulation"
        and rel.from_key_value == formulation_id
        and rel.rel_type == "HAS_PARAMETER"
        and rel.to_label == "Parameter"
        and rel.to_key_value == f"{formulation_id}:alpha"
        for rel in result.relations
    )


def test_review_does_not_add_observation_nodes_or_relations():
    extraction = _extraction()
    corrections = _ReviewCorrections(
        add_nodes=[
            _ReviewNode(
                label="Observation",
                properties={"content": "Agent saw high reward."},
                natural_key="content",
            )
        ],
        add_relations=[
            _ReviewRelation(
                from_label="Observation",
                from_key_value="Agent saw high reward.",
                to_label="Formulation",
                to_key_value="q-learning",
                rel_type="OBSERVED_IN",
            ),
            _ReviewRelation(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value="alpha",
                rel_type="HAS_PARAMETER",
            ),
        ],
    )

    _apply_corrections(extraction, corrections)

    assert not any(node.label == "Observation" for node in extraction.nodes)
    assert not any(
        rel.from_label == "Observation" or rel.to_label == "Observation"
        for rel in extraction.relations
    )
    assert any(
        rel.from_label == "Formulation"
        and rel.to_label == "Parameter"
        and rel.to_key_value == "alpha"
        and rel.rel_type == "HAS_PARAMETER"
        for rel in extraction.relations
    )


@pytest.mark.asyncio
async def test_review_chunks_large_extraction(monkeypatch):
    monkeypatch.setattr(review_module, "_EXTRACTION_MAX_CHARS", 300)
    monkeypatch.setattr(review_module, "_REVIEW_CHUNK_MAX_NODES", 5)
    monkeypatch.setattr(review_module, "_REVIEW_CHUNK_MAX_RELATIONS", 4)

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={"slug": "reinforcement-learning"},
                natural_key="slug",
            ),
            NodeSpec(
                label="Formulation",
                properties={
                    "id": "q-learning",
                    "name": "Q-learning",
                    "paradigm_slug": "reinforcement-learning",
                },
                natural_key="id",
            ),
            *[
                NodeSpec(
                    label="Parameter",
                    properties={
                        "name": f"alpha_{idx}",
                        "formulation_id": "q-learning",
                    },
                    natural_key="name",
                )
                for idx in range(12)
            ],
        ],
        relations=[
            RelationSpec(
                from_label="Formulation",
                from_key_value="q-learning",
                to_label="Parameter",
                to_key_value=f"alpha_{idx}",
                rel_type="HAS_PARAMETER",
            )
            for idx in range(12)
        ],
        facts=[],
        stage="formalizer",
        run_id="run-1",
    )
    calls: list[str] = []

    async def _fake_call_structured(**kwargs):
        calls.append(kwargs["messages"][0]["content"])
        return _ReviewCorrections()

    with patch(
        "decisionlab.knowledge.review.call_structured",
        side_effect=_fake_call_structured,
    ):
        await review_and_correct_extraction(
            extraction,
            stage_output="large formalizer output",
            client=AsyncMock(),
        )

    assert len(calls) > 1
    assert all("Slice:" in call for call in calls)
