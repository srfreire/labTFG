"""KG population: write ExtractionResult to Neo4j with node dedup and temporal provenance."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime

from decisionlab.knowledge.models import ExtractionResult, KGWriteResult
from shared.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Relation properties that are temporal metadata — excluded from content comparison.
_TEMPORAL_KEYS = frozenset(
    {
        "valid_from",
        "valid_to",
        "run_id",
        "created_at",
        "updated_at",
        "superseded_by",
    }
)

# Property names tried, in priority order, when the LLM-declared natural_key is
# missing from `properties`. Covers the common identifier vocabulary.
_FALLBACK_KEY_NAMES = ("slug", "id", "doi", "url", "name", "title")


def _resolve_natural_key(node) -> tuple[str, object] | None:
    """Pick a usable (key_name, key_value) pair for a node.

    Tries in order:
      1. The LLM-declared natural_key, if its value is present in properties.
      2. Any of _FALLBACK_KEY_NAMES present in properties.
      3. A synthetic key derived from a stable hash of (label, properties).

    For (3) the property is injected into ``node.properties`` so MERGE has
    something to bind to. Returning None means the node has neither a label
    nor any property to hash — effectively unrecoverable.
    """
    declared = node.natural_key
    if declared and _SAFE_IDENT.match(declared):
        val = node.properties.get(declared)
        if val is not None:
            return declared, val

    for candidate in _FALLBACK_KEY_NAMES:
        val = node.properties.get(candidate)
        if val is not None and _SAFE_IDENT.match(candidate):
            logger.info(
                "Node %s: natural_key %r missing — falling back to %r",
                node.label,
                declared,
                candidate,
            )
            return candidate, val

    if not node.properties:
        return None

    blob = json.dumps(
        {"label": node.label, "props": node.properties},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    synthetic_value = "h_" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]
    node.properties["_synthetic_id"] = synthetic_value
    logger.warning(
        "Node %s: natural_key %r missing and no fallback property — "
        "synthesized _synthetic_id=%s",
        node.label,
        declared,
        synthetic_value,
    )
    return "_synthetic_id", synthetic_value


async def populate_kg(
    extraction: ExtractionResult, kg: KnowledgeGraph
) -> KGWriteResult:
    """Write extraction nodes and relations to Neo4j with dedup and provenance.

    Nodes are MERGEd (ON CREATE / ON MATCH) so duplicates are impossible.
    Relations follow the Zep immutable+supersession pattern: if an existing
    active relation has different non-temporal properties, it is superseded
    (valid_to set) and a new one created.

    Everything runs in a single write transaction.  If the transaction fails,
    a KGWriteResult with zero counts and the error message is returned.
    """
    now = datetime.now(UTC).isoformat()
    run_id = extraction.run_id

    # Mutable accumulators shared with the transaction closure.
    counters = {
        "nodes_created": 0,
        "nodes_merged": 0,
        "relations_created": 0,
        "relations_superseded": 0,
    }
    errors: list[str] = []

    # Map (label, key_value) → key_property_name built during node processing,
    # so relation lookups use the extraction's natural key, not the schema default.
    node_key_map: dict[tuple[str, str], str] = {}

    async def _work(tx):
        # ── Nodes ────────────────────────────────────────────────────────
        for node in extraction.nodes:
            if not _SAFE_IDENT.match(node.label):
                errors.append(f"Node: invalid label '{node.label}'")
                continue

            resolved = _resolve_natural_key(node)
            if resolved is None:
                errors.append(
                    f"Node {node.label}: no usable natural_key and no properties to hash"
                )
                continue
            key_name, key_value = resolved

            # Record for relation endpoint resolution.
            node_key_map[(node.label, str(key_value))] = key_name

            # Properties for ON CREATE (includes created_at, run_ids).
            # Strip updated_at to keep the was_created heuristic reliable.
            create_props = {
                **{k: v for k, v in node.properties.items() if k != "updated_at"},
                "created_at": now,
                "run_ids": [run_id],
            }
            # Properties for ON MATCH (overrides values, preserves created_at).
            update_props = {**node.properties, "updated_at": now}

            cypher = (
                f"MERGE (n:{node.label} {{{key_name}: $key_value}}) "
                f"ON CREATE SET n += $create_props "
                f"ON MATCH SET n += $update_props, "
                f"n.run_ids = coalesce(n.run_ids, []) + $run_id "
                f"RETURN n.updated_at IS NULL AS was_created"
            )
            result = await tx.run(
                cypher,
                {
                    "key_value": key_value,
                    "create_props": create_props,
                    "update_props": update_props,
                    "run_id": run_id,
                },
            )
            record = await result.single()
            if record and record["was_created"]:
                counters["nodes_created"] += 1
            else:
                counters["nodes_merged"] += 1

        # ── Relations ────────────────────────────────────────────────────
        for rel in extraction.relations:
            # Validate all identifiers interpolated into Cypher.
            if not _SAFE_IDENT.match(rel.from_label):
                errors.append(f"Relation: invalid from_label '{rel.from_label}'")
                continue
            if not _SAFE_IDENT.match(rel.to_label):
                errors.append(f"Relation: invalid to_label '{rel.to_label}'")
                continue
            if not _SAFE_IDENT.match(rel.rel_type):
                errors.append(f"Relation: invalid rel_type '{rel.rel_type}'")
                continue

            # Resolve which property to match each endpoint on.
            from_key = _resolve_key(
                rel.from_label, rel.from_key_value, node_key_map, kg
            )
            to_key = _resolve_key(rel.to_label, rel.to_key_value, node_key_map, kg)
            if from_key is None or to_key is None:
                errors.append(
                    f"Relation {rel.rel_type}: cannot resolve key for "
                    f"{rel.from_label}={rel.from_key_value!r} or "
                    f"{rel.to_label}={rel.to_key_value!r}"
                )
                continue

            # Check for existing active relation of the same type.
            check_cypher = (
                f"MATCH (a:{rel.from_label} {{{from_key}: $from_val}})"
                f"-[r:{rel.rel_type}]->"
                f"(b:{rel.to_label} {{{to_key}: $to_val}}) "
                f"WHERE r.valid_to IS NULL "
                f"RETURN properties(r) AS props, elementId(r) AS rid"
            )
            check_result = await tx.run(
                check_cypher,
                {
                    "from_val": rel.from_key_value,
                    "to_val": rel.to_key_value,
                },
            )
            existing = await check_result.single()

            new_props = {
                **rel.properties,
                "run_id": run_id,
                "created_at": now,
                "valid_from": now,
            }

            if existing:
                old_content = {
                    k: v
                    for k, v in existing["props"].items()
                    if k not in _TEMPORAL_KEYS
                }
                new_content = {
                    k: v for k, v in rel.properties.items() if k not in _TEMPORAL_KEYS
                }
                if old_content == new_content:
                    continue  # idempotent — skip

                # Supersede: mark old relation with valid_to.
                await tx.run(
                    "MATCH ()-[r]->() WHERE elementId(r) = $rid SET r.valid_to = $now",
                    {"rid": existing["rid"], "now": now},
                )
                counters["relations_superseded"] += 1

            # Create the new relation.
            create_cypher = (
                f"MATCH (a:{rel.from_label} {{{from_key}: $from_val}}), "
                f"(b:{rel.to_label} {{{to_key}: $to_val}}) "
                f"CREATE (a)-[r:{rel.rel_type} $props]->(b) "
                f"RETURN elementId(r) AS rid"
            )
            create_result = await tx.run(
                create_cypher,
                {
                    "from_val": rel.from_key_value,
                    "to_val": rel.to_key_value,
                    "props": new_props,
                },
            )
            record = await create_result.single()
            if record is None:
                errors.append(
                    f"Relation {rel.rel_type}: endpoint not found — "
                    f"{rel.from_label}.{from_key}={rel.from_key_value!r} or "
                    f"{rel.to_label}.{to_key}={rel.to_key_value!r}"
                )
                continue
            counters["relations_created"] += 1

    try:
        await kg.execute_write(_work)
    except Exception as exc:
        logger.error("populate_kg transaction failed: %s", exc)
        errors.append(f"Transaction failed: {exc}")
        # Transaction rolled back — zero out counts.
        for key in counters:
            counters[key] = 0

    return KGWriteResult(**counters, errors=errors)


def _resolve_key(
    label: str,
    key_value: str,
    node_key_map: dict[tuple[str, str], str],
    kg: KnowledgeGraph,
) -> str | None:
    """Determine which Neo4j property to match a relation endpoint on.

    First checks the node_key_map (populated during node processing for this
    extraction). Falls back to the schema's unique key for cross-extraction
    references.
    """
    mapped = node_key_map.get((label, key_value))
    if mapped is not None:
        return mapped
    try:
        return kg.unique_key_for(label)
    except ValueError:
        return None
