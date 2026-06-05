"""Post-write health checks and deterministic readability repair for the KG."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from decisionlab.knowledge.kg_writer import (
    _SAFE_IDENT,
    _resolve_natural_key,
    _validate_natural_key,
)
from decisionlab.knowledge.models import ExtractionResult, KGHealthResult, NodeSpec
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from shared.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_READABILITY_SOURCE = "kg_health"


@dataclass(frozen=True)
class _NodeIdentity:
    label: str
    key: str
    value: Any
    props: dict


@dataclass(frozen=True)
class _InferredRelation:
    from_node: _NodeIdentity
    rel_type: str
    to_node: _NodeIdentity
    reason: str


async def repair_kg_health(
    extraction: ExtractionResult,
    kg: KnowledgeGraph,
) -> KGHealthResult:
    """Repair obvious post-memory graph readability issues.

    The pass is deliberately deterministic. It never asks an LLM and never
    invents strong scientific claims. When an extraction gives enough scope, it
    adds conservative structure such as ``BELONGS_TO`` paradigm edges, plus
    exact edges like ``Model IMPLEMENTS Formulation`` and single-formulation
    ``USES_*`` / ``HAS_PARAMETER`` edges.
    """
    identities = _node_identities(extraction, kg)
    isolated_before = await _count_isolated(kg, identities)
    inferred_relations = _candidate_inferred_relations(identities)

    created = 0
    warnings: list[str] = []
    for relation in inferred_relations:
        try:
            if await _create_inferred_relation(kg, extraction, relation):
                created += 1
        except Exception as exc:
            warnings.append(
                f"{relation.from_node.label} -[{relation.rel_type}]-> "
                f"{relation.to_node.label}: {exc}"
            )
            logger.warning("KG health inferred relation failed: %s", exc)

    isolated_after = await _count_isolated(kg, identities)
    global_isolated_after = await _global_isolated_count(kg)
    if isolated_after:
        warnings.append(
            f"{isolated_after} node(s) from this extraction remain isolated"
        )
    if global_isolated_after:
        warnings.append(f"{global_isolated_after} total KG node(s) remain isolated")

    return KGHealthResult(
        checked_nodes=len(identities),
        isolated_before=isolated_before,
        isolated_after=isolated_after,
        global_isolated_after=global_isolated_after,
        inferred_relations_created=created,
        warnings=warnings,
    )


def _node_identities(
    extraction: ExtractionResult,
    kg: KnowledgeGraph,
) -> list[_NodeIdentity]:
    identities: list[_NodeIdentity] = []
    seen: set[tuple[str, str, str]] = set()

    for node in extraction.nodes:
        node_copy = NodeSpec(
            label=node.label,
            properties=dict(node.properties),
            natural_key=node.natural_key,
        )
        resolved = _resolve_natural_key(node_copy, kg)
        if resolved is None:
            continue
        key, value = resolved
        ok, normalized, _err = _validate_natural_key(
            label=node_copy.label,
            key_name=key,
            key_value=value,
        )
        if not ok:
            continue
        identity_key = (node_copy.label, key, str(normalized))
        if identity_key in seen:
            continue
        seen.add(identity_key)
        identities.append(
            _NodeIdentity(
                label=node_copy.label,
                key=key,
                value=normalized,
                props=node_copy.properties,
            )
        )

    return identities


def _candidate_inferred_relations(
    identities: list[_NodeIdentity],
) -> list[_InferredRelation]:
    by_label: dict[str, list[_NodeIdentity]] = {}
    for identity in identities:
        by_label.setdefault(identity.label, []).append(identity)

    paradigm_nodes = {
        str(node.value): node
        for node in by_label.get("Paradigm", [])
        if node.key == "slug"
    }
    for slug in _paradigm_slugs(identities):
        paradigm_nodes.setdefault(
            slug,
            _NodeIdentity("Paradigm", "slug", slug, {"slug": slug}),
        )

    fallback_scope = next(iter(paradigm_nodes)) if len(paradigm_nodes) == 1 else None
    formulation_by_id = {
        str(node.value): node for node in by_label.get("Formulation", [])
    }
    single_formulation = (
        by_label["Formulation"][0]
        if len(by_label.get("Formulation", [])) == 1
        else None
    )

    relations: list[_InferredRelation] = []
    seen: set[tuple[str, str, str, str, str, str, str]] = set()

    def add(
        from_node: _NodeIdentity,
        rel_type: str,
        to_node: _NodeIdentity,
        reason: str,
    ) -> None:
        key = (
            from_node.label,
            from_node.key,
            str(from_node.value),
            rel_type,
            to_node.label,
            to_node.key,
            str(to_node.value),
        )
        if key in seen:
            return
        seen.add(key)
        relations.append(_InferredRelation(from_node, rel_type, to_node, reason))

    for node in identities:
        if node.label == "Paradigm":
            continue

        if node.label == "Model":
            formulation = formulation_by_id.get(str(node.value))
            if formulation is not None:
                add(node, "IMPLEMENTS", formulation, "same formulation_id")
                continue

        scope = _node_paradigm_slug(node) or fallback_scope
        if scope and (paradigm := paradigm_nodes.get(scope)):
            add(node, "BELONGS_TO", paradigm, "paradigm scope")

    if single_formulation is not None:
        for equation in by_label.get("Equation", []):
            add(
                single_formulation,
                "USES_EQUATION",
                equation,
                "single formulation extraction",
            )
        for parameter in by_label.get("Parameter", []):
            add(
                single_formulation,
                "HAS_PARAMETER",
                parameter,
                "single formulation extraction",
            )
        for variable in by_label.get("Variable", []):
            add(
                single_formulation,
                "USES_VARIABLE",
                variable,
                "single formulation extraction",
            )

    for node in identities:
        formulation_id = _node_formulation_id(node)
        if not formulation_id:
            continue
        formulation = formulation_by_id.get(formulation_id)
        if formulation is None:
            continue
        if node.label == "Equation":
            add(formulation, "USES_EQUATION", node, "formulation_id scope")
        elif node.label == "Parameter":
            add(formulation, "HAS_PARAMETER", node, "formulation_id scope")
        elif node.label == "Variable":
            add(formulation, "USES_VARIABLE", node, "formulation_id scope")

    return relations


def _paradigm_slugs(identities: list[_NodeIdentity]) -> set[str]:
    slugs: set[str] = set()
    for node in identities:
        slug = _node_paradigm_slug(node)
        if slug:
            slugs.add(slug)
        if node.label == "Paradigm" and node.key == "slug":
            slugs.add(str(node.value))
    return slugs


def _node_paradigm_slug(node: _NodeIdentity) -> str | None:
    raw = node.props.get("paradigm_slug")
    if isinstance(raw, str) and raw.strip():
        return slugify(raw)
    if node.label in {"Variable", "Postulate"} and isinstance(node.value, str):
        prefix, sep, _suffix = node.value.partition(":")
        if sep and prefix and prefix != "orphan":
            return prefix
    return None


def _node_formulation_id(node: _NodeIdentity) -> str | None:
    raw = node.props.get("formulation_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


async def _count_isolated(
    kg: KnowledgeGraph,
    identities: list[_NodeIdentity],
) -> int:
    count = 0
    for node in identities:
        if not _safe_node_match(node):
            continue
        rows = await kg.query(
            f"MATCH (n:{node.label} {{{node.key}: $value}}) "
            "RETURN COUNT { (n)--() } AS degree",
            {"value": node.value},
        )
        degree = int(rows[0].get("degree", 0)) if rows else 0
        if degree == 0:
            count += 1
    return count


async def _global_isolated_count(kg: KnowledgeGraph) -> int:
    rows = await kg.query("MATCH (n) WHERE NOT (n)--() RETURN count(n) AS isolated")
    return int(rows[0].get("isolated", 0)) if rows else 0


async def _create_inferred_relation(
    kg: KnowledgeGraph,
    extraction: ExtractionResult,
    relation: _InferredRelation,
) -> bool:
    from_node = relation.from_node
    to_node = relation.to_node
    if not _safe_node_match(from_node) or not _safe_node_match(to_node):
        return False
    if not _SAFE_IDENT.match(relation.rel_type):
        return False
    if await _belongs_to_conflicts_with_stored_scope(kg, relation):
        return False

    rows = await kg.query(
        f"MATCH (a:{from_node.label} {{{from_node.key}: $from_value}}), "
        f"(b:{to_node.label} {{{to_node.key}: $to_value}}) "
        f"WHERE NOT (a)-[:{relation.rel_type}]->(b) "
        f"CREATE (a)-[r:{relation.rel_type} $props]->(b) "
        "RETURN count(r) AS created",
        {
            "from_value": from_node.value,
            "to_value": to_node.value,
            "props": {
                "source": _READABILITY_SOURCE,
                "source_stage": extraction.stage,
                "reason": relation.reason,
            },
        },
    )
    return bool(rows and rows[0].get("created"))


async def _belongs_to_conflicts_with_stored_scope(
    kg: KnowledgeGraph,
    relation: _InferredRelation,
) -> bool:
    if (
        relation.rel_type != "BELONGS_TO"
        or relation.to_node.label != "Paradigm"
        or relation.to_node.key != "slug"
    ):
        return False

    from_node = relation.from_node
    rows = await kg.query(
        f"MATCH (a:{from_node.label} {{{from_node.key}: $value}}) "
        "RETURN a.paradigm_slug AS paradigm_slug",
        {"value": from_node.value},
    )
    if not rows:
        return False
    stored_scope = rows[0].get("paradigm_slug")
    if not isinstance(stored_scope, str) or not stored_scope.strip():
        return False
    return slugify(stored_scope) != str(relation.to_node.value)


def _safe_node_match(node: _NodeIdentity) -> bool:
    return (
        _SAFE_IDENT.match(node.label) is not None
        and _SAFE_IDENT.match(node.key) is not None
    )
