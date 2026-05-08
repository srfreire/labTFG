"""KG population: write ExtractionResult to Neo4j with node dedup and temporal provenance."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from decisionlab.knowledge.models import ExtractionResult, KGWriteResult
from decisionlab.tools.reports import slugify
from shared.knowledge_graph import KnowledgeGraph

if TYPE_CHECKING:
    from shared.embedding import EmbeddingService
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _get_embedding_service() -> EmbeddingService | None:
    """Lazy lookup of shared.embeddings — None if not initialised. Test
    seam: monkeypatch this to inject a fake."""
    import shared

    return shared.embeddings


def _get_vector_store() -> VectorStore | None:
    """Lazy lookup of shared.vectors — None if not initialised. Test
    seam: monkeypatch this to inject a fake."""
    import shared

    return shared.vectors


_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# UUID4 shape: 8-4-4-4-12 hex digits. Used to catch run_id / uuid.uuid4()
# leaks into identifier-style natural keys (Paradigm.slug being the canonical
# offender — see research-memory-rewrite-status.md "Known issues").
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Hard ceiling on natural-key length. Real slugs/names sit well under this;
# anything longer is almost certainly a hash, full statement, or LLM blob
# accidentally promoted to a key.
_MAX_KEY_VALUE_LEN = 80

# Labels whose natural key is a human-readable identifier (slug, name, id).
# A UUID-shaped value on these is a leak, not a legitimate identifier.
# Paper.doi is excluded — DOIs share the dash-pattern surface but are content
# keys, not slugs, and never collide with the UUID4 shape in practice.
_SLUG_LIKE_LABELS = frozenset(
    {"Paradigm", "Variable", "Postulate", "Formulation", "Model", "BrainRegion"}
)

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


def _validate_natural_key(
    *, label: str, key_name: str, key_value: object
) -> tuple[bool, object, str | None]:
    """Validate and (for slug-like labels) renormalize a natural-key value.

    Returns ``(ok, normalized_value, err)``:
      - ``ok=True``: caller may MERGE on ``normalized_value``. For slug-like
        labels the value has been re-slugified; for everything else it is
        returned verbatim.
      - ``ok=False``: ``err`` carries a human-readable reason; the caller
        records it in ``KGWriteResult.errors`` and skips the node.

    Catches three classes of bugs:
      1. ``run_id`` UUIDs leaking into ``Paradigm.slug`` (upstream
         coercion).
      2. LLM-emitted slugs that bypassed producer-side normalization
         ("Reinforcement Learning" → "reinforcement-learning").
      3. Outsized blobs (full statements, hashes) accidentally promoted
         to a key.
    """
    if not isinstance(key_value, str):
        return (True, key_value, None)
    # Length and UUID-shape checks are scoped to slug-like labels. Content keys
    # (Paper.title, Equation.latex) routinely exceed the slug ceiling and must
    # pass through unmolested.
    if label in _SLUG_LIKE_LABELS:
        if len(key_value) > _MAX_KEY_VALUE_LEN:
            return (
                False,
                key_value,
                f"{label}.{key_name}={key_value!r}: natural-key value exceeds "
                f"{_MAX_KEY_VALUE_LEN} characters — refusing to write",
            )
        if _UUID_RE.match(key_value):
            return (
                False,
                key_value,
                f"{label}.{key_name}={key_value!r}: natural-key value is shaped "
                "like a UUID — likely a run_id leak; refusing to write",
            )
        # Only the key actually called "slug" gets renormalized — Variable.name
        # ("energy_level") and Postulate.id ("P1") are slug-like labels but
        # their natural_key is a human-readable name, not a kebab-case slug.
        if key_name == "slug":
            normalized = slugify(key_value)
            if not normalized:
                return (
                    False,
                    key_value,
                    f"{label}.{key_name}={key_value!r}: slug normalized to empty",
                )
            return (True, normalized, None)
    return (True, key_value, None)


def _resolve_natural_key(node, kg=None) -> tuple[str, object] | None:
    """Pick a usable (key_name, key_value) pair for a node.

    Resolution order:
      1. The schema's unique-key property (e.g. ``Paper.doi``) when present
         and non-null in properties — overrides any LLM-declared key so the
         Neo4j uniqueness constraint cannot be violated by accidentally
         MERGEing on a different field (the cumulative-growth t1 failure).
      2. The LLM-declared natural_key, if its value is present in properties.
      3. Any of _FALLBACK_KEY_NAMES present in properties.
      4. A synthetic key derived from a stable hash of (label, properties).

    For (4) the property is injected into ``node.properties`` so MERGE has
    something to bind to. Returning None means the node has neither a label
    nor any property to hash — effectively unrecoverable.

    Variable nodes get a composite ``id = {paradigm_slug}:{slugify(name)}``
    so the same name under two paradigms cannot collide. Bypasses the
    schema/declared/fallback chain entirely: the canonical id is always
    derived here, even if ``id`` was already set on the incoming node.
    """
    if node.label == "Variable":
        name = node.properties.get("name") or ""
        paradigm = node.properties.get("paradigm_slug") or ""
        slug_name = slugify(name) if isinstance(name, str) else ""
        if not slug_name:
            return None
        if paradigm:
            return ("id", f"{slugify(paradigm)}:{slug_name}")
        # Orphan: still scope it under a fixed namespace so it can't collide
        # with a real paradigm-scoped variable.
        return ("id", f"orphan:{slug_name}")

    schema_key: str | None = None
    if kg is not None:
        try:
            schema_key = kg.unique_key_for(node.label)
        except (ValueError, AttributeError):
            schema_key = None

    if schema_key and _SAFE_IDENT.match(schema_key):
        val = node.properties.get(schema_key)
        if val is not None and val != "":
            return schema_key, val

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

    Each node and relation is written in its own managed-write transaction,
    so a single failure (e.g. a ``Paper.doi`` constraint collision) cannot
    void the rest of the batch. Failed writes are logged into ``errors``
    and skipped; downstream assertions detect partial writes via
    ``KGWriteResult.errors``.

    Nodes are MERGEd (ON CREATE / ON MATCH) so re-running on the same
    extraction is idempotent. Relations follow the Zep immutable+
    supersession pattern: if an existing active relation has different
    non-temporal properties, it is superseded (``valid_to`` set) and a
    new one created.
    """
    now = datetime.now(UTC).isoformat()
    run_id = extraction.run_id

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

    # Slug-like nodes successfully written this batch — fed into the
    # kg_entities_dense ANN index after the node loop so retrieval's
    # _link_entities_ann can find them without an O(N) Cypher table scan.
    ann_targets: list[
        tuple[str, str, str, str]
    ] = []  # (label, key_value, name, description)

    # ── Nodes ────────────────────────────────────────────────────────────
    for node in extraction.nodes:
        if not _SAFE_IDENT.match(node.label):
            errors.append(f"Node: invalid label '{node.label}'")
            continue

        resolved = _resolve_natural_key(node, kg)
        if resolved is None:
            errors.append(
                f"Node {node.label}: no usable natural_key and no properties to hash"
            )
            continue
        key_name, key_value = resolved

        ok, normalized, err = _validate_natural_key(
            label=node.label, key_name=key_name, key_value=key_value
        )
        if not ok:
            errors.append(err or f"natural-key rejected: {node.label}.{key_name}")
            logger.warning("kg_write_skipped: %s", err)
            continue
        # Re-slugified or content-key passthrough — use the canonical form
        # for both the MERGE binding and the property write so the node is
        # discoverable by the same key on subsequent reads.
        key_value = normalized
        if isinstance(normalized, str) and isinstance(
            node.properties.get(key_name), str
        ):
            node.properties[key_name] = normalized

        # Per-entity transaction: a constraint failure on this node leaves
        # the rest of the batch untouched. The pre-rewrite version wrapped
        # every node + relation in a single tx, so a single Paper.doi
        # collision wiped the whole topic's writes (cumulative-growth t1).
        async def _node_work(tx, node=node, key_name=key_name, key_value=key_value):
            create_props = {
                **{k: v for k, v in node.properties.items() if k != "updated_at"},
                "created_at": now,
                "run_ids": [run_id],
            }
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
            return await result.single()

        try:
            record = await kg.execute_write(_node_work)
        except Exception as exc:
            errors.append(
                f"Node {node.label}.{key_name}={key_value!r} write failed: {exc}"
            )
            logger.warning(
                "kg_write_skipped node=%s key=%s=%r: %s",
                node.label,
                key_name,
                key_value,
                exc,
            )
            continue

        node_key_map[(node.label, str(key_value))] = key_name
        if record and record["was_created"]:
            counters["nodes_created"] += 1
        else:
            counters["nodes_merged"] += 1

        # Queue slug-like nodes for ANN-index sync after the node loop.
        if node.label in _SLUG_LIKE_LABELS:
            display_name = node.properties.get("name") or str(key_value)
            description = node.properties.get("description") or ""
            ann_targets.append((node.label, str(key_value), display_name, description))

    # ── Relations ────────────────────────────────────────────────────────
    for rel in extraction.relations:
        if not _SAFE_IDENT.match(rel.from_label):
            errors.append(f"Relation: invalid from_label '{rel.from_label}'")
            continue
        if not _SAFE_IDENT.match(rel.to_label):
            errors.append(f"Relation: invalid to_label '{rel.to_label}'")
            continue
        if not _SAFE_IDENT.match(rel.rel_type):
            errors.append(f"Relation: invalid rel_type '{rel.rel_type}'")
            continue

        from_key = _resolve_key(rel.from_label, rel.from_key_value, node_key_map, kg)
        to_key = _resolve_key(rel.to_label, rel.to_key_value, node_key_map, kg)
        if from_key is None or to_key is None:
            errors.append(
                f"Relation {rel.rel_type}: cannot resolve key for "
                f"{rel.from_label}={rel.from_key_value!r} or "
                f"{rel.to_label}={rel.to_key_value!r}"
            )
            continue

        new_props = {
            **rel.properties,
            "run_id": run_id,
            "created_at": now,
            "valid_from": now,
        }

        async def _rel_work(
            tx,
            rel=rel,
            from_key=from_key,
            to_key=to_key,
            new_props=new_props,
        ):
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

            superseded = False
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
                    return ("idempotent", False)

                await tx.run(
                    "MATCH ()-[r]->() WHERE elementId(r) = $rid SET r.valid_to = $now",
                    {"rid": existing["rid"], "now": now},
                )
                superseded = True

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
            create_record = await create_result.single()
            if create_record is None:
                return ("missing_endpoint", superseded)
            return ("created", superseded)

        try:
            outcome, superseded = await kg.execute_write(_rel_work)
        except Exception as exc:
            errors.append(f"Relation {rel.rel_type}: write failed: {exc}")
            logger.warning(
                "kg_write_skipped rel=%s %s→%s: %s",
                rel.rel_type,
                rel.from_label,
                rel.to_label,
                exc,
            )
            continue

        if superseded:
            counters["relations_superseded"] += 1
        if outcome == "created":
            counters["relations_created"] += 1
        elif outcome == "missing_endpoint":
            errors.append(
                f"Relation {rel.rel_type}: endpoint not found — "
                f"{rel.from_label}.{from_key}={rel.from_key_value!r} or "
                f"{rel.to_label}.{to_key}={rel.to_key_value!r}"
            )

    # ── ANN sync (best-effort) ───────────────────────────────────────────
    # After all node writes, push the slug-like nodes into kg_entities_dense
    # so retrieval._link_entities_ann can find them without a Cypher table
    # scan. Fire-and-forget at this layer: a Voyage/Qdrant outage logs a
    # warning but does not turn the KG write into a failure.
    if ann_targets:
        try:
            emb = _get_embedding_service()
            vec = _get_vector_store()
            if emb is not None and vec is not None:
                texts = [
                    f"{name}: {desc}" if desc else name
                    for (_label, _key, name, desc) in ann_targets
                ]
                vecs = await emb.embed_texts(texts)
                for (label, key_value, display_name, _desc), vector in zip(
                    ann_targets, vecs, strict=True
                ):
                    point_id = f"{label}:{key_value}"
                    await vec.upsert_dense(
                        "kg_entities_dense",
                        id=point_id,
                        vector=vector,
                        payload={
                            "label": label,
                            "key_value": key_value,
                            "name": display_name,
                        },
                    )
        except Exception as exc:
            logger.warning("kg_writer: ANN sync failed (non-fatal): %s", exc)

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
