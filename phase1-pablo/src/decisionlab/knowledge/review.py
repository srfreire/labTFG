"""LLM review/correction pass for generated KG extractions.

The extractor is the generation pass. This module is the second pass: ask an
LLM to review the generated nodes/relations against the source artifact, then
apply small, structured corrections before Neo4j writes happen.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from decisionlab.config import SETTINGS
from decisionlab.knowledge.ids import normalize_extraction_ids
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.structured import call_structured

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_SOURCE_MAX_CHARS = int(os.getenv("DECISIONLAB_MEMORY_REVIEW_SOURCE_CHARS", "14000"))
_EXTRACTION_MAX_CHARS = int(
    os.getenv("DECISIONLAB_MEMORY_REVIEW_EXTRACTION_CHARS", "12000")
)
_REVIEW_MAX_TOKENS = int(os.getenv("DECISIONLAB_MEMORY_REVIEW_MAX_TOKENS", "8192"))
_REVIEW_CHUNK_MAX_NODES = int(
    os.getenv("DECISIONLAB_MEMORY_REVIEW_CHUNK_MAX_NODES", "70")
)
_REVIEW_CHUNK_MAX_RELATIONS = int(
    os.getenv("DECISIONLAB_MEMORY_REVIEW_CHUNK_MAX_RELATIONS", "90")
)
_REVIEW_MAX_FACTS = int(os.getenv("DECISIONLAB_MEMORY_REVIEW_MAX_FACTS", "20"))

_ALLOWED_REVIEW_LABELS = frozenset(
    {
        "Paradigm",
        "Author",
        "Paper",
        "BrainRegion",
        "Variable",
        "Postulate",
        "Equation",
        "Parameter",
        "Formulation",
        "Model",
    }
)

_REVIEW_SYSTEM = """\
You are the review-and-correction pass for a scientific knowledge graph memory
pipeline.

You receive:
1. the original pipeline artifact;
2. the generated KG extraction, or a focused slice of a large extraction.

Your job is to correct graph readability and endpoint consistency before Neo4j
write time. Be conservative: add or change only connections/properties directly
supported by the artifact or by obvious local identity consistency.

Focus on:
- Formulation -> Paradigm BELONGS_TO edges.
- Formulation -> Equation USES_EQUATION edges.
- Formulation -> Variable USES_VARIABLE edges.
- Formulation -> Parameter HAS_PARAMETER edges.
- Model -> Formulation IMPLEMENTS edges.
- Parameter -> Postulate DERIVES_FROM edges when the artifact explicitly gives
  a source/rule/postulate chain.
- Filling missing formulation_id/paradigm_slug on Parameter, Variable, Equation,
  and Model nodes when the artifact makes the owner formulation clear.

Use only existing graph node labels: Paradigm, Author, Paper, BrainRegion,
Variable, Postulate, Equation, Parameter, Formulation, and Model. Do not emit
Observation, ObservationNode, SimulationObservation, or TestResult nodes. Runtime
observations belong in facts/memory; observable model inputs are Variable nodes.

Do not invent authors, papers, equations, postulates, or scientific claims. Do
not remove a relation unless it is clearly attached to the wrong endpoint.
Return only structured corrections.
"""

_REVIEW_USER = """\
Stage: {stage}
Run id: {run_id}

Original artifact:
{source}

Generated extraction or slice:
{extraction}
"""


class _ReviewNode(BaseModel):
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    natural_key: str


class _ReviewRelation(BaseModel):
    from_label: str
    from_key_value: str
    to_label: str
    to_key_value: str
    rel_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class _NodePatch(BaseModel):
    label: str
    key: str
    value: str
    properties: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class _ReviewCorrections(BaseModel):
    update_nodes: list[_NodePatch] = Field(default_factory=list)
    add_nodes: list[_ReviewNode] = Field(default_factory=list)
    add_relations: list[_ReviewRelation] = Field(default_factory=list)
    remove_relations: list[_ReviewRelation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_list_strings_on_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        coerced = dict(value)
        for field in (
            "update_nodes",
            "add_nodes",
            "add_relations",
            "remove_relations",
            "notes",
        ):
            coerced[field] = cls._coerce_json_list_string(coerced.get(field, []))
        return coerced

    @field_validator(
        "update_nodes",
        "add_nodes",
        "add_relations",
        "remove_relations",
        "notes",
        mode="before",
    )
    @classmethod
    def _coerce_json_list_string(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [] if text.startswith("[") else value
        return parsed if isinstance(parsed, list) else value


async def review_and_correct_extraction(
    extraction: ExtractionResult,
    *,
    stage_output: str,
    client: AsyncAnthropic,
) -> ExtractionResult:
    """Run an LLM correction pass and merge safe edits into *extraction*.

    This function mutates and returns *extraction*. Callers should treat failure
    as non-fatal: malformed/failed review output is logged and the generated
    extraction continues unchanged.
    """
    source = _truncate_middle(stage_output, _SOURCE_MAX_CHARS)
    totals = _ReviewCorrections()
    failures = 0

    for name, extraction_json in _review_payloads(extraction):
        try:
            corrections = await _call_review(
                stage=extraction.stage,
                run_id=extraction.run_id,
                source=source,
                extraction_json=extraction_json,
                slice_name=name,
                client=client,
            )
        except Exception:
            failures += 1
            logger.exception(
                "KG review[%s]: slice %s failed; continuing with other slices",
                extraction.stage,
                name,
            )
            continue

        _apply_corrections(extraction, corrections)
        _merge_totals(totals, corrections)
        normalize_extraction_ids(extraction)

    normalize_extraction_ids(extraction)
    logger.info(
        "KG review[%s]: %d node patches, %d nodes added, %d relations added, "
        "%d relations removed, %d failed slice(s)",
        extraction.stage,
        len(totals.update_nodes),
        len(totals.add_nodes),
        len(totals.add_relations),
        len(totals.remove_relations),
        failures,
    )
    return extraction


async def _call_review(
    *,
    stage: str,
    run_id: str,
    source: str,
    extraction_json: str,
    slice_name: str,
    client: AsyncAnthropic,
) -> _ReviewCorrections:
    return await call_structured(
        client=client,
        messages=[
            {
                "role": "user",
                "content": _REVIEW_USER.format(
                    stage=stage,
                    run_id=run_id,
                    source=source,
                    extraction=f"Slice: {slice_name}\n{extraction_json}",
                ),
            }
        ],
        system=_REVIEW_SYSTEM,
        schema=_ReviewCorrections,
        max_tokens=_REVIEW_MAX_TOKENS,
        model=SETTINGS.knowledge_structured_model,
    )


def _merge_totals(total: _ReviewCorrections, incoming: _ReviewCorrections) -> None:
    total.update_nodes.extend(incoming.update_nodes)
    total.add_nodes.extend(incoming.add_nodes)
    total.add_relations.extend(incoming.add_relations)
    total.remove_relations.extend(incoming.remove_relations)
    total.notes.extend(incoming.notes)


def _apply_corrections(
    extraction: ExtractionResult,
    corrections: _ReviewCorrections,
) -> None:
    for rel in corrections.remove_relations:
        _remove_relation(extraction, rel)

    for patch in corrections.update_nodes:
        _patch_node(extraction, patch)

    for raw_node in corrections.add_nodes:
        if not _label_is_allowed(raw_node.label):
            logger.warning(
                "KG review[%s]: ignored unsupported added node label %s",
                extraction.stage,
                raw_node.label,
            )
            continue
        _upsert_node(
            extraction,
            NodeSpec(
                label=raw_node.label,
                properties=dict(raw_node.properties),
                natural_key=raw_node.natural_key,
            ),
        )

    for raw_rel in corrections.add_relations:
        if not _relation_labels_are_allowed(raw_rel):
            logger.warning(
                "KG review[%s]: ignored unsupported relation endpoints %s -> %s",
                extraction.stage,
                raw_rel.from_label,
                raw_rel.to_label,
            )
            continue
        _add_relation(
            extraction,
            RelationSpec(
                from_label=raw_rel.from_label,
                from_key_value=raw_rel.from_key_value,
                to_label=raw_rel.to_label,
                to_key_value=raw_rel.to_key_value,
                rel_type=raw_rel.rel_type,
                properties=dict(raw_rel.properties),
            ),
        )


def _label_is_allowed(label: str) -> bool:
    return label in _ALLOWED_REVIEW_LABELS


def _relation_labels_are_allowed(rel: _ReviewRelation) -> bool:
    return _label_is_allowed(rel.from_label) and _label_is_allowed(rel.to_label)


def _patch_node(extraction: ExtractionResult, patch: _NodePatch) -> None:
    for node in extraction.nodes:
        if node.label != patch.label:
            continue
        if str(node.properties.get(patch.key)) != str(patch.value):
            continue
        for key, value in patch.properties.items():
            if value is None:
                continue
            node.properties[key] = value
        return


def _upsert_node(extraction: ExtractionResult, incoming: NodeSpec) -> None:
    incoming_key_value = incoming.properties.get(incoming.natural_key)
    for node in extraction.nodes:
        if node.label != incoming.label:
            continue
        if node.natural_key != incoming.natural_key:
            continue
        if str(node.properties.get(node.natural_key)) != str(incoming_key_value):
            continue
        for key, value in incoming.properties.items():
            if value is not None:
                node.properties.setdefault(key, value)
        return
    extraction.nodes.append(incoming)


def _add_relation(extraction: ExtractionResult, incoming: RelationSpec) -> None:
    if any(_same_relation(existing, incoming) for existing in extraction.relations):
        return
    extraction.relations.append(incoming)


def _remove_relation(extraction: ExtractionResult, incoming: _ReviewRelation) -> None:
    candidate = RelationSpec(
        from_label=incoming.from_label,
        from_key_value=incoming.from_key_value,
        to_label=incoming.to_label,
        to_key_value=incoming.to_key_value,
        rel_type=incoming.rel_type,
        properties={},
    )
    extraction.relations = [
        rel for rel in extraction.relations if not _same_relation(rel, candidate)
    ]


def _same_relation(left: RelationSpec, right: RelationSpec) -> bool:
    return (
        left.from_label == right.from_label
        and left.from_key_value == right.from_key_value
        and left.to_label == right.to_label
        and left.to_key_value == right.to_key_value
        and left.rel_type == right.rel_type
    )


def _extraction_payload(extraction: ExtractionResult) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "label": node.label,
                "properties": node.properties,
                "natural_key": node.natural_key,
            }
            for node in extraction.nodes
        ],
        "relations": [
            {
                "from_label": rel.from_label,
                "from_key_value": rel.from_key_value,
                "to_label": rel.to_label,
                "to_key_value": rel.to_key_value,
                "rel_type": rel.rel_type,
                "properties": rel.properties,
            }
            for rel in extraction.relations
        ],
        "facts": extraction.facts,
    }


def _review_payloads(extraction: ExtractionResult) -> list[tuple[str, str]]:
    full = _payload_json(_extraction_payload(extraction))
    if len(full) <= _EXTRACTION_MAX_CHARS:
        return [("full", full)]

    payloads: list[tuple[str, str]] = []
    seen_relations: set[int] = set()
    seen_nodes: set[int] = set()
    node_lookup = _node_lookup(extraction.nodes)

    for form_idx, formulation in enumerate(extraction.nodes):
        if formulation.label != "Formulation":
            continue
        node_indexes = _formulation_node_indexes(extraction, form_idx)
        relation_indexes = _relations_for_nodes(
            extraction.relations,
            extraction.nodes,
            node_indexes,
            node_lookup,
        )
        payloads.extend(
            _bounded_payloads(
                extraction,
                name=f"formulation:{_node_identity_value(formulation) or form_idx}",
                node_indexes=node_indexes,
                relation_indexes=relation_indexes,
            )
        )
        seen_nodes.update(node_indexes)
        seen_relations.update(relation_indexes)

    remaining_nodes = [
        idx for idx, _node in enumerate(extraction.nodes) if idx not in seen_nodes
    ]
    remaining_relations = [
        idx
        for idx, _rel in enumerate(extraction.relations)
        if idx not in seen_relations
    ]
    payloads.extend(
        _bounded_payloads(
            extraction,
            name="remaining",
            node_indexes=set(remaining_nodes),
            relation_indexes=set(remaining_relations),
        )
    )
    return payloads or [
        ("full-truncated", _truncate_middle(full, _EXTRACTION_MAX_CHARS))
    ]


def _bounded_payloads(
    extraction: ExtractionResult,
    *,
    name: str,
    node_indexes: set[int],
    relation_indexes: set[int],
) -> list[tuple[str, str]]:
    if not node_indexes and not relation_indexes:
        return []

    node_indexes = set(node_indexes)
    relation_indexes = set(relation_indexes)
    if (
        len(node_indexes) <= _REVIEW_CHUNK_MAX_NODES
        and len(relation_indexes) <= _REVIEW_CHUNK_MAX_RELATIONS
    ):
        return [
            (
                name,
                _payload_json(
                    _payload_from_indexes(extraction, node_indexes, relation_indexes)
                ),
            )
        ]

    payloads: list[tuple[str, str]] = []
    sorted_relation_indexes = sorted(relation_indexes)
    node_lookup = _node_lookup(extraction.nodes)

    for chunk_id, relation_chunk in enumerate(
        _chunks(sorted_relation_indexes, _REVIEW_CHUNK_MAX_RELATIONS),
        start=1,
    ):
        chunk_nodes = set(node_indexes)
        for rel_idx in relation_chunk:
            rel = extraction.relations[rel_idx]
            chunk_nodes.update(_endpoint_node_indexes(rel, node_lookup))
        limited_nodes = set(sorted(chunk_nodes)[:_REVIEW_CHUNK_MAX_NODES])
        payloads.append(
            (
                f"{name}:relations:{chunk_id}",
                _payload_json(
                    _payload_from_indexes(
                        extraction,
                        limited_nodes,
                        set(relation_chunk),
                    )
                ),
            )
        )

    relation_endpoint_nodes = set()
    for rel_idx in relation_indexes:
        relation_endpoint_nodes.update(
            _endpoint_node_indexes(extraction.relations[rel_idx], node_lookup)
        )
    node_only_indexes = sorted(node_indexes - relation_endpoint_nodes)
    for chunk_id, node_chunk in enumerate(
        _chunks(node_only_indexes, _REVIEW_CHUNK_MAX_NODES),
        start=1,
    ):
        payloads.append(
            (
                f"{name}:nodes:{chunk_id}",
                _payload_json(
                    _payload_from_indexes(extraction, set(node_chunk), set())
                ),
            )
        )

    return payloads


def _payload_from_indexes(
    extraction: ExtractionResult,
    node_indexes: set[int],
    relation_indexes: set[int],
) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "label": node.label,
                "properties": node.properties,
                "natural_key": node.natural_key,
            }
            for idx, node in enumerate(extraction.nodes)
            if idx in node_indexes
        ],
        "relations": [
            {
                "from_label": rel.from_label,
                "from_key_value": rel.from_key_value,
                "to_label": rel.to_label,
                "to_key_value": rel.to_key_value,
                "rel_type": rel.rel_type,
                "properties": rel.properties,
            }
            for idx, rel in enumerate(extraction.relations)
            if idx in relation_indexes
        ],
        "facts": extraction.facts[:_REVIEW_MAX_FACTS],
    }


def _payload_json(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    return _truncate_middle(serialized, _EXTRACTION_MAX_CHARS)


def _formulation_node_indexes(
    extraction: ExtractionResult,
    form_idx: int,
) -> set[int]:
    formulation = extraction.nodes[form_idx]
    props = formulation.properties
    formulation_id = str(props.get("id") or props.get("formulation_id") or "")
    local_id = str(props.get("local_id") or "").strip()
    paradigm_slug = str(props.get("paradigm_slug") or "").strip()
    node_indexes = {form_idx}

    for idx, node in enumerate(extraction.nodes):
        node_props = node.properties
        if node.label == "Paradigm" and paradigm_slug:
            if str(node_props.get("slug") or "").strip() == paradigm_slug:
                node_indexes.add(idx)
            continue

        node_formulation = str(node_props.get("formulation_id") or "").strip()
        node_local = str(node_props.get("local_formulation_id") or "").strip()
        if (formulation_id and node_formulation == formulation_id) or (
            local_id and node_local == local_id
        ):
            node_indexes.add(idx)

    return node_indexes


def _relations_for_nodes(
    relations: list[RelationSpec],
    nodes: list[NodeSpec],
    node_indexes: set[int],
    node_lookup: dict[tuple[str, str], set[int]],
) -> set[int]:
    identities = {
        (nodes[idx].label, value)
        for idx in node_indexes
        for value in _node_reference_values(nodes[idx])
    }
    relation_indexes: set[int] = set()
    for idx, rel in enumerate(relations):
        endpoints = {
            (rel.from_label, str(rel.from_key_value)),
            (rel.to_label, str(rel.to_key_value)),
        }
        if identities & endpoints:
            relation_indexes.add(idx)
            continue
        if _endpoint_node_indexes(rel, node_lookup) & node_indexes:
            relation_indexes.add(idx)
    return relation_indexes


def _node_lookup(nodes: list[NodeSpec]) -> dict[tuple[str, str], set[int]]:
    lookup: dict[tuple[str, str], set[int]] = {}
    for idx, node in enumerate(nodes):
        for value in _node_reference_values(node):
            lookup.setdefault((node.label, value), set()).add(idx)
    return lookup


def _endpoint_node_indexes(
    rel: RelationSpec,
    node_lookup: dict[tuple[str, str], set[int]],
) -> set[int]:
    indexes = set(node_lookup.get((rel.from_label, str(rel.from_key_value)), set()))
    indexes.update(node_lookup.get((rel.to_label, str(rel.to_key_value)), set()))
    return indexes


def _node_reference_values(node: NodeSpec) -> set[str]:
    values: set[str] = set()
    for key in {
        node.natural_key,
        "id",
        "slug",
        "doi",
        "title",
        "name",
        "latex",
        "formulation_id",
    }:
        if not key:
            continue
        value = node.properties.get(key)
        if value is not None and str(value).strip():
            values.add(str(value))
    return values


def _node_identity_value(node: NodeSpec) -> str:
    values = _node_reference_values(node)
    return next(iter(sorted(values)), "")


def _chunks(values: list[int], size: int) -> list[list[int]]:
    if size <= 0:
        return [values]
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def _truncate_middle(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"
