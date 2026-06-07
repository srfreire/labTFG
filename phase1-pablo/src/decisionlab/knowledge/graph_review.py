"""Post-write graph reviewer for KG ingestion.

The memory extractor writes first; this reviewer inspects the actual graph
state that Neo4j accepted and applies only typed, validated corrections.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text as sql_text

from decisionlab.config import SETTINGS
from decisionlab.knowledge.ids import canonical_key_for_label
from decisionlab.knowledge.kg_writer import (
    _DEFAULT_RELATION_CONFIDENCE,
    _DEFAULT_RELATION_IMPORTANCE,
    _SAFE_IDENT,
    _STAGE_RELATION_CONFIDENCE,
    _STAGE_RELATION_IMPORTANCE,
    KG_RELATION_NAMESPACE,
    _close_memory,
    _create_relation_memory,
    _list_existing_relations,
    _relation_content,
)
from decisionlab.knowledge.models import KGReviewResult
from decisionlab.structured import call_structured
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from shared.database import DatabaseService
    from shared.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_SOURCE_MAX_CHARS = int(os.getenv("DECISIONLAB_GRAPH_REVIEW_SOURCE_CHARS", "14000"))
_SNAPSHOT_MAX_CHARS = int(os.getenv("DECISIONLAB_GRAPH_REVIEW_SNAPSHOT_CHARS", "22000"))
_MAX_TOUCHED_NODES = int(os.getenv("DECISIONLAB_GRAPH_REVIEW_MAX_NODES", "120"))
_MAX_NEIGHBORS_PER_NODE = int(os.getenv("DECISIONLAB_GRAPH_REVIEW_MAX_NEIGHBORS", "8"))
_REVIEW_MAX_TOKENS = int(os.getenv("DECISIONLAB_GRAPH_REVIEW_MAX_TOKENS", "8192"))
_GRAPH_REVIEW_SOURCE = "graph_review"

_SYSTEM = """\
You are the post-write reviewer for a scientific knowledge graph.

You receive:
1. the original pipeline artifact;
2. the actual Neo4j subgraph touched by this run after the Memory Agent write;
3. the approved paradigms/formulations for this pipeline stage.

Review graph readability and endpoint correctness. Only suggest corrections
directly supported by the artifact and visible graph state.

Allowed corrections:
- add missing structural or explicit scientific relations between existing nodes;
- warn about orphan/island nodes that cannot be corrected safely.

Forbidden:
- do not invent new nodes;
- do not emit Cypher;
- do not connect to paradigms outside the approved context;
- do not delete or weaken old/seed relations;
- do not add a relation unless both endpoint key/value pairs appear in the graph
  snapshot or approved anchor context.

Return only structured corrections.
"""

_USER = """\
Stage: {stage}
Run id: {run_id}
Approved paradigms: {approved_paradigms}
Approved formulations: {approved_formulations}

Original artifact:
{source}

Post-write graph snapshot:
{snapshot}
"""


class _GraphRelationPatch(BaseModel):
    from_label: str
    from_key: str
    from_value: str
    rel_type: str
    to_label: str
    to_key: str
    to_value: str
    reason: str = ""
    evidence: str = ""


class _GraphCorrections(BaseModel):
    add_relations: list[_GraphRelationPatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_list_strings_on_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        coerced = dict(value)
        for field in ("add_relations", "warnings"):
            coerced[field] = cls._coerce_json_list_string(coerced.get(field, []))
        return coerced

    @field_validator("add_relations", "warnings", mode="before")
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


async def review_written_graph(
    *,
    stage: str,
    run_id: str,
    stage_output: str,
    kg: KnowledgeGraph | None,
    db: DatabaseService | None,
    client: AsyncAnthropic,
    approved_paradigms: list[str] | tuple[str, ...] | set[str] | None = None,
    approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]] | None = None,
) -> KGReviewResult:
    """Review the persisted graph delta and apply validated corrections."""
    if kg is None or db is None:
        return KGReviewResult(corrections_applied=0)

    approved_slugs = {slugify(slug) for slug in approved_paradigms or [] if slug}
    approved_formulations = _approved_formulations(approved_specs or {})
    try:
        snapshot = await _snapshot_written_subgraph(
            run_id=run_id,
            stage=stage,
            kg=kg,
            db=db,
        )
    except Exception as exc:
        logger.exception("Graph reviewer snapshot failed for stage=%s", stage)
        return KGReviewResult(
            corrections_applied=0,
            failed=True,
            error=f"snapshot: {exc}",
        )

    if not snapshot.get("nodes"):
        return KGReviewResult(corrections_applied=0)

    applied = 0
    warnings: list[str] = []
    for relation in _deterministic_structural_patches(
        snapshot,
        approved_slugs=approved_slugs,
    ):
        try:
            if await _apply_relation(
                relation,
                stage=stage,
                run_id=run_id,
                kg=kg,
                db=db,
                approved_slugs=approved_slugs,
                approved_formulations=approved_formulations,
            ):
                applied += 1
        except Exception as exc:
            warnings.append(
                f"{relation.from_label} -[{relation.rel_type}]-> "
                f"{relation.to_label}: {exc}"
            )
            logger.warning("Graph reviewer structural correction skipped: %s", exc)

    if applied:
        try:
            snapshot = await _snapshot_written_subgraph(
                run_id=run_id,
                stage=stage,
                kg=kg,
                db=db,
            )
        except Exception as exc:
            logger.exception(
                "Graph reviewer snapshot refresh failed for stage=%s", stage
            )
            return KGReviewResult(
                corrections_applied=applied,
                warnings=warnings,
                failed=True,
                error=f"snapshot_refresh: {exc}",
            )

    try:
        corrections = await call_structured(
            client=client,
            messages=[
                {
                    "role": "user",
                    "content": _USER.format(
                        stage=stage,
                        run_id=run_id,
                        approved_paradigms=sorted(approved_slugs),
                        approved_formulations=sorted(approved_formulations),
                        source=_truncate_middle(stage_output, _SOURCE_MAX_CHARS),
                        snapshot=_truncate_middle(
                            json.dumps(snapshot, ensure_ascii=False, default=str),
                            _SNAPSHOT_MAX_CHARS,
                        ),
                    ),
                }
            ],
            system=_SYSTEM,
            schema=_GraphCorrections,
            max_tokens=_REVIEW_MAX_TOKENS,
            model=SETTINGS.knowledge_structured_model,
        )
    except Exception as exc:
        logger.exception("Graph reviewer LLM failed for stage=%s", stage)
        return KGReviewResult(
            corrections_applied=applied,
            warnings=warnings,
            failed=True,
            error=f"review: {exc}",
        )

    warnings.extend(corrections.warnings)
    for relation in corrections.add_relations:
        try:
            if await _apply_relation(
                relation,
                stage=stage,
                run_id=run_id,
                kg=kg,
                db=db,
                approved_slugs=approved_slugs,
                approved_formulations=approved_formulations,
            ):
                applied += 1
        except Exception as exc:
            warnings.append(
                f"{relation.from_label} -[{relation.rel_type}]-> "
                f"{relation.to_label}: {exc}"
            )
            logger.warning("Graph reviewer correction skipped: %s", exc)

    return KGReviewResult(corrections_applied=applied, warnings=warnings)


def _deterministic_structural_patches(
    snapshot: dict[str, Any],
    *,
    approved_slugs: set[str],
) -> list[_GraphRelationPatch]:
    """Return safe post-write structural anchors for visible island nodes."""
    patches: list[_GraphRelationPatch] = []
    for node in snapshot.get("nodes") or []:
        if node.get("label") != "Variable" or int(node.get("degree") or 0) != 0:
            continue
        props = node.get("properties") or {}
        variable_id = str(props.get("id") or "").strip()
        paradigm_slug = slugify(props.get("paradigm_slug") or "")
        if not variable_id or not paradigm_slug:
            continue
        if approved_slugs and paradigm_slug not in approved_slugs:
            continue
        patches.append(
            _GraphRelationPatch(
                from_label="Variable",
                from_key="id",
                from_value=variable_id,
                rel_type="BELONGS_TO",
                to_label="Paradigm",
                to_key="slug",
                to_value=paradigm_slug,
                reason="post-write structural anchor for paradigm-level variable",
                evidence=(
                    "Variable node has an approved paradigm_slug and degree 0 "
                    "in the persisted graph snapshot."
                ),
            )
        )
    return patches


async def _snapshot_written_subgraph(
    *,
    run_id: str,
    stage: str,
    kg: KnowledgeGraph,
    db: DatabaseService,
) -> dict[str, Any]:
    parsed_run_id = uuid.UUID(run_id)
    async with db.get_session() as session:
        node_rows = (
            (
                await session.execute(
                    sql_text(
                        "SELECT DISTINCT label, key_value "
                        "FROM node_run_observations "
                        "WHERE run_id = :run_id "
                        "ORDER BY label, key_value "
                        "LIMIT :limit"
                    ),
                    {"run_id": parsed_run_id, "limit": _MAX_TOUCHED_NODES},
                )
            )
            .mappings()
            .all()
        )
        rel_rows = (
            (
                await session.execute(
                    sql_text(
                        "SELECT content, metadata "
                        "FROM pipeline_memories "
                        "WHERE namespace = :namespace "
                        "  AND run_id = :run_id "
                        "  AND source_stage = :stage "
                        "  AND valid_to IS NULL "
                        "ORDER BY created_at DESC "
                        "LIMIT 120"
                    ),
                    {
                        "namespace": KG_RELATION_NAMESPACE,
                        "run_id": parsed_run_id,
                        "stage": stage,
                    },
                )
            )
            .mappings()
            .all()
        )

    nodes = []
    for row in node_rows:
        label = str(row["label"])
        key_value = str(row["key_value"])
        lookup_props = _node_lookup_props(label)
        if not lookup_props or not _SAFE_IDENT.match(label):
            continue
        rows = await kg.query(
            f"MATCH (n:{label}) "
            "WHERE any(prop IN $lookup_props WHERE n[prop] = $value) "
            "OPTIONAL MATCH (n)-[r]-(m) "
            "WITH n, r, m LIMIT $neighbor_limit "
            "RETURN labels(n) AS labels, properties(n) AS properties, "
            "COUNT { (n)--() } AS degree, "
            "collect(CASE WHEN r IS NULL THEN NULL ELSE {"
            "type: type(r), "
            "direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END, "
            "other_labels: labels(m), "
            "other_properties: properties(m), "
            "properties: properties(r)"
            "} END) AS neighbors",
            {
                "value": key_value,
                "lookup_props": lookup_props,
                "neighbor_limit": _MAX_NEIGHBORS_PER_NODE,
            },
        )
        if not rows:
            continue
        item = rows[0]
        props = item.get("properties") or {}
        key = _display_key_for_snapshot(label, props, fallback_value=key_value)
        nodes.append(
            {
                "label": label,
                "key": key,
                "value": str(props.get(key, key_value)),
                "labels": item.get("labels") or [],
                "properties": _strip_large_props(props),
                "degree": item.get("degree") or 0,
                "neighbors": [
                    _strip_neighbor(neighbor)
                    for neighbor in item.get("neighbors") or []
                    if neighbor
                ],
            }
        )

    return {
        "nodes": nodes,
        "relations_from_stage": [dict(row) for row in rel_rows],
    }


def _node_lookup_props(label: str) -> list[str]:
    canonical = canonical_key_for_label(label)
    props = [
        canonical,
        "slug",
        "id",
        "doi",
        "name",
        "title",
        "latex",
        "url",
        "formulation_id",
        "_synthetic_id",
    ]
    return [prop for prop in dict.fromkeys(props) if prop and _SAFE_IDENT.match(prop)]


def _display_key_for_snapshot(
    label: str, props: dict[str, Any], *, fallback_value: str
) -> str:
    canonical = canonical_key_for_label(label)
    if canonical and props.get(canonical) not in (None, ""):
        return canonical
    for prop in _node_lookup_props(label):
        if str(props.get(prop, "")) == fallback_value:
            return prop
    return canonical or "id"


async def _apply_relation(
    relation: _GraphRelationPatch,
    *,
    stage: str,
    run_id: str,
    kg: KnowledgeGraph,
    db: DatabaseService,
    approved_slugs: set[str],
    approved_formulations: set[str],
) -> bool:
    _validate_relation_patch(
        relation,
        approved_slugs=approved_slugs,
        approved_formulations=approved_formulations,
    )
    existing = await _list_existing_relations(
        kg=kg,
        from_label=relation.from_label,
        from_key=relation.from_key,
        from_value=relation.from_value,
        to_label=relation.to_label,
        to_key=relation.to_key,
        to_value=relation.to_value,
        rel_type=relation.rel_type,
    )
    if existing:
        return False

    valid_from = datetime.now(UTC)
    props = {
        "source": _GRAPH_REVIEW_SOURCE,
        "source_stage": stage,
        "reason": relation.reason,
        "evidence": relation.evidence,
    }
    memory_id = await _create_relation_memory(
        run_id=uuid.UUID(run_id),
        stage=stage,
        content=_relation_content(
            from_label=relation.from_label,
            from_key_value=relation.from_value,
            rel_type=relation.rel_type,
            to_label=relation.to_label,
            to_key_value=relation.to_value,
        ),
        confidence=_STAGE_RELATION_CONFIDENCE.get(stage, _DEFAULT_RELATION_CONFIDENCE),
        importance=_STAGE_RELATION_IMPORTANCE.get(stage, _DEFAULT_RELATION_IMPORTANCE),
        properties=props,
        valid_from=valid_from,
        db=db,
    )
    if memory_id is None:
        return False

    rows = await kg.query(
        f"MATCH (a:{relation.from_label} {{{relation.from_key}: $from_value}}), "
        f"(b:{relation.to_label} {{{relation.to_key}: $to_value}}) "
        f"WHERE NOT (a)-[:{relation.rel_type}]->(b) "
        f"CREATE (a)-[r:{relation.rel_type} $props]->(b) "
        "RETURN count(r) AS created",
        {
            "from_value": relation.from_value,
            "to_value": relation.to_value,
            "props": {**props, "memory_id": str(memory_id)},
        },
    )
    created = bool(rows and rows[0].get("created"))
    if not created:
        await _close_memory(memory_id, valid_to=valid_from, db=db)
    return created


def _validate_relation_patch(
    relation: _GraphRelationPatch,
    *,
    approved_slugs: set[str],
    approved_formulations: set[str],
) -> None:
    for value, name in (
        (relation.from_label, "from_label"),
        (relation.from_key, "from_key"),
        (relation.to_label, "to_label"),
        (relation.to_key, "to_key"),
        (relation.rel_type, "rel_type"),
    ):
        if not _SAFE_IDENT.match(value):
            raise ValueError(f"invalid {name}: {value!r}")

    if relation.from_key != (canonical_key_for_label(relation.from_label) or ""):
        raise ValueError("source endpoint key is not canonical for its label")
    if relation.to_key != (canonical_key_for_label(relation.to_label) or ""):
        raise ValueError("target endpoint key is not canonical for its label")

    for label, value in (
        (relation.from_label, relation.from_value),
        (relation.to_label, relation.to_value),
    ):
        if label == "Paradigm" and approved_slugs:
            slug = slugify(value)
            if slug not in approved_slugs:
                raise ValueError(f"paradigm {slug!r} is outside approved context")
        if label == "Formulation" and approved_formulations:
            text = str(value)
            local = text.rsplit(":", 1)[-1]
            if text not in approved_formulations and local not in approved_formulations:
                raise ValueError(f"formulation {text!r} is outside approved context")


def _approved_formulations(
    approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]],
) -> set[str]:
    out: set[str] = set()
    for paradigm, raw_ids in approved_specs.items():
        scope = slugify(paradigm)
        for raw_id in raw_ids or []:
            local = slugify(raw_id)
            if not local:
                continue
            out.add(local)
            if scope:
                out.add(f"{scope}:{local}")
    return out


def _strip_neighbor(neighbor: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": neighbor.get("type"),
        "direction": neighbor.get("direction"),
        "other_labels": neighbor.get("other_labels") or [],
        "other_properties": _strip_large_props(neighbor.get("other_properties") or {}),
        "properties": _strip_large_props(neighbor.get("properties") or {}),
    }


def _strip_large_props(props: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in props.items()
        if key not in {"embedding"} and _json_reasonable(value)
    }


def _json_reasonable(value: Any) -> bool:
    if isinstance(value, str):
        return len(value) <= 2000
    if isinstance(value, int | float | bool) or value is None:
        return True
    if isinstance(value, list):
        return len(value) <= 20
    return False


def _truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max_chars // 2
    return text[:keep] + "\n...[truncated]...\n" + text[-keep:]
