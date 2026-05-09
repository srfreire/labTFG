"""KG population: write ExtractionResult to Neo4j with node dedup and temporal provenance."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from decisionlab.knowledge.models import ExtractionResult, KGWriteResult
from decisionlab.tools.reports import slugify
from shared.knowledge_graph import KG_RELATION_NAMESPACE, KnowledgeGraph

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.embedding import EmbeddingService
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Per-stage defaults for KG-relation memory rows. Mirror the resolver's
# shape (importance / confidence / memory_type) so that PG `pipeline_memories`
# rows seeded by `populate_kg` are queryable alongside fact-style rows.
_STAGE_RELATION_IMPORTANCE: dict[str, float] = {
    "researcher": 5.0,
    "formalizer": 6.0,
    "reasoner": 7.0,
    "builder": 8.0,
}
_STAGE_RELATION_CONFIDENCE: dict[str, float] = {
    "researcher": 0.6,
    "formalizer": 0.7,
    "reasoner": 0.8,
    "builder": 0.9,
}
_DEFAULT_RELATION_IMPORTANCE = 5.0
_DEFAULT_RELATION_CONFIDENCE = 0.7


async def _record_node_run_observation(
    *,
    label: str,
    key_value: str,
    run_id: str,
    db: DatabaseService | None,
) -> None:
    """Best-effort insert of one ``node_run_observations`` row.

    Skipped when ``db`` is unavailable or ``run_id`` isn't a UUID (e.g. the
    ``canonical-paradigms-seed`` constant — those nodes have no backing
    ``runs`` row to point at). Postgres failures are logged but never
    propagate: the KG write must succeed even if Postgres is down.
    """
    try:
        parsed_run_id = uuid.UUID(run_id)
    except (ValueError, AttributeError, TypeError):
        return

    if db is None:
        return

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO node_run_observations "
                    "(id, label, key_value, run_id) "
                    "VALUES (:id, :label, :key_value, :run_id) "
                    "ON CONFLICT (label, key_value, run_id) DO NOTHING"
                ),
                {
                    "id": uuid.uuid4(),
                    "label": label[:40],
                    "key_value": str(key_value)[:120],
                    "run_id": parsed_run_id,
                },
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "node_run_observations insert failed (non-fatal) "
            "label=%s key=%r run_id=%s: %s",
            label,
            key_value,
            run_id,
            exc,
        )


def _relation_content(
    *,
    from_label: str,
    from_key_value: str | int,
    rel_type: str,
    to_label: str,
    to_key_value: str | int,
) -> str:
    """Stable text encoding of a relation identity triple.

    Used as ``pipeline_memories.content`` so the row is human-readable in
    SQL inspection and survives the JSONB round-trip without ambiguity.
    """
    return f"{from_label}.{from_key_value} -[{rel_type}]-> {to_label}.{to_key_value}"


async def _create_relation_memory(
    *,
    run_id: uuid.UUID,
    stage: str,
    content: str,
    confidence: float,
    importance: float,
    properties: dict,
    valid_from: datetime,
    db: DatabaseService | None,
) -> uuid.UUID | None:
    """Insert a fresh ``pipeline_memories`` row for a KG relation.

    Returns the new id on success, or ``None`` if Postgres is unavailable
    or the insert fails (caller falls back to writing the relation with no
    ``memory_id``).  The KG write must keep working even when PG is down.
    """
    if db is None:
        return None

    new_id = uuid.uuid4()
    naive_valid_from = (
        valid_from.replace(tzinfo=None) if valid_from.tzinfo is not None else valid_from
    )

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO pipeline_memories "
                    "(id, content, namespace, memory_type, source_stage, "
                    "run_id, importance, confidence, valid_from, metadata) "
                    "VALUES (:id, :content, :namespace, :memory_type, :stage, "
                    ":run_id, :importance, :confidence, :valid_from, "
                    "CAST(:metadata AS JSONB))"
                ),
                {
                    "id": new_id,
                    "content": content,
                    "namespace": KG_RELATION_NAMESPACE,
                    "memory_type": "semantic",
                    "stage": stage[:100] if stage else "kg_writer",
                    "run_id": run_id,
                    "importance": importance,
                    "confidence": confidence,
                    "valid_from": naive_valid_from,
                    "metadata": json.dumps(properties, default=str),
                },
            )
            await session.commit()
        return new_id
    except Exception as exc:
        logger.warning(
            "kg_writer: pipeline_memories insert failed (non-fatal) "
            "content=%r run_id=%s: %s",
            content,
            run_id,
            exc,
        )
        return None


async def _close_memory(
    memory_id: uuid.UUID,
    *,
    valid_to: datetime,
    db: DatabaseService | None,
) -> bool:
    """Stamp ``valid_to`` on an existing ``pipeline_memories`` row.

    Returns True on success, False on Postgres failure or unavailability.
    Idempotent: a row whose ``valid_to`` is already set is left alone (the
    UPDATE only matches rows where the column is NULL).
    """
    if db is None:
        return False

    naive_valid_to = (
        valid_to.replace(tzinfo=None) if valid_to.tzinfo is not None else valid_to
    )

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            await session.execute(
                sql_text(
                    "UPDATE pipeline_memories SET valid_to = :valid_to "
                    "WHERE id = :id AND valid_to IS NULL"
                ),
                {"id": memory_id, "valid_to": naive_valid_to},
            )
            await session.commit()
        return True
    except Exception as exc:
        logger.warning(
            "kg_writer: pipeline_memories valid_to update failed (non-fatal) id=%s: %s",
            memory_id,
            exc,
        )
        return False


async def _list_existing_relations(
    *,
    kg: KnowledgeGraph,
    from_label: str,
    from_key: str,
    from_value: str | int,
    to_label: str,
    to_key: str,
    to_value: str | int,
    rel_type: str,
) -> list[dict]:
    """Return every Neo4j relation matching the identity triple, with props.

    Each row carries ``{"memory_id": str | None, "props": dict}``.
    Relations without ``memory_id`` are pre-P4-004 seed edges (timeless
    canonical truth) — they participate in content-based idempotency
    checks but are never tombstoned.
    """
    cypher = (
        f"MATCH (a:{from_label} {{{from_key}: $from_val}})"
        f"-[r:{rel_type}]->"
        f"(b:{to_label} {{{to_key}: $to_val}}) "
        f"RETURN r.memory_id AS memory_id, properties(r) AS props"
    )
    rows = await kg.query(
        cypher,
        {"from_val": from_value, "to_val": to_value},
    )
    return [
        {"memory_id": row.get("memory_id"), "props": row.get("props") or {}}
        for row in rows
    ]


async def _fetch_active_memory_meta(
    memory_ids: list[str],
    *,
    db: DatabaseService | None,
) -> dict[str, dict]:
    """Return ``{memory_id: {valid_to, content, properties}}`` for live rows.

    "Live" = ``valid_to IS NULL``. Rows already superseded are excluded so
    only at most one live row per Neo4j triple should ever come back.
    """
    if not memory_ids:
        return {}
    if db is None:
        return {}

    parsed: list[uuid.UUID] = []
    for mid in memory_ids:
        try:
            parsed.append(uuid.UUID(str(mid)))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return {}

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT id, content, metadata FROM pipeline_memories "
                    "WHERE id = ANY(:ids) AND valid_to IS NULL"
                ),
                {"ids": parsed},
            )
            return {
                str(row.id): {
                    "content": row.content,
                    "properties": row.metadata or {},
                }
                for row in result.all()
            }
    except Exception as exc:
        logger.warning(
            "kg_writer: pipeline_memories fetch failed (non-fatal): %s",
            exc,
        )
        return {}


_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Hard ceiling on natural-key length. Real slugs/names sit well under this;
# anything longer is almost certainly a hash, full statement, or LLM blob
# accidentally promoted to a key.
_MAX_KEY_VALUE_LEN = 80

# Labels whose natural key is a human-readable identifier (slug, name, id).
_SLUG_LIKE_LABELS = frozenset(
    {"Paradigm", "Variable", "Postulate", "Formulation", "Model", "BrainRegion"}
)

# Relation properties that are temporal metadata — excluded from content comparison.
# `memory_id` is the PG join key (P4-004), not part of the relation's identity.
_TEMPORAL_KEYS = frozenset(
    {
        "valid_from",
        "valid_to",
        "run_id",
        "created_at",
        "updated_at",
        "superseded_by",
        "memory_id",
        "confidence",
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
      - ``ok=True``: caller may MERGE on ``normalized_value``. For ``slug``
        keys the value has been re-slugified; for everything else it is
        returned verbatim.
      - ``ok=False``: ``err`` carries a human-readable reason; the caller
        records it in ``KGWriteResult.errors`` and skips the node.

    Length cap rejects outsized blobs (full statements, hashes) accidentally
    promoted to a key on slug-like labels. ``slug`` keys also get
    re-slugified to enforce kebab-case identity.
    """
    if not isinstance(key_value, str):
        return (True, key_value, None)
    # Length cap is scoped to slug-like labels. Content keys (Paper.title,
    # Equation.latex) routinely exceed the slug ceiling and must pass
    # through unmolested.
    if label in _SLUG_LIKE_LABELS:
        if len(key_value) > _MAX_KEY_VALUE_LEN:
            return (
                False,
                key_value,
                f"{label}.{key_name}={key_value!r}: natural-key value exceeds "
                f"{_MAX_KEY_VALUE_LEN} characters — refusing to write",
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
    extraction: ExtractionResult,
    kg: KnowledgeGraph,
    *,
    db: DatabaseService | None = None,
    embeddings: EmbeddingService | None = None,
    vectors: VectorStore | None = None,
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

    # Slug-like nodes successfully written this batch — embeddings are
    # written to `n.embedding` after the node loop so the native Neo4j
    # vector index (`<label>_embedding_idx`) can answer entity-linking
    # queries without leaving Neo4j (replaces the prior Qdrant
    # `kg_entities_dense` round-trip — P4-002).
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
            # P0-004: drop unbounded `run_ids` array; track count + recency
            # only. Per-run provenance moves to the Postgres
            # node_run_observations table written after this Cypher returns.
            #
            # `run_count` increment is read-modify-write inside the Cypher
            # tx. Neo4j serialises write-tx on the same node, so two
            # concurrent populate_kg calls on the *same* node will not
            # interleave reads — the loser retries the whole tx work fn.
            # Cross-pipeline concurrent write throughput is single-digit
            # in this project, so the simple `coalesce(...) + 1` is safe.
            create_props = {
                **{k: v for k, v in node.properties.items() if k != "updated_at"},
                "created_at": now,
                "run_count": 1,
                "last_run_at": now,
            }
            update_props = {**node.properties, "updated_at": now, "last_run_at": now}

            cypher = (
                f"MERGE (n:{node.label} {{{key_name}: $key_value}}) "
                f"ON CREATE SET n += $create_props "
                f"ON MATCH SET n += $update_props, "
                f"n.run_count = coalesce(n.run_count, 0) + 1 "
                f"RETURN n.updated_at IS NULL AS was_created"
            )
            result = await tx.run(
                cypher,
                {
                    "key_value": key_value,
                    "create_props": create_props,
                    "update_props": update_props,
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

        # Per-run provenance: best-effort PG insert. Postgres failures or
        # non-UUID run_ids (e.g. the seed run) silently skip — the KG write
        # already succeeded and counts toward the result.
        await _record_node_run_observation(
            label=node.label, key_value=str(key_value), run_id=run_id, db=db
        )

        # Queue slug-like nodes for ANN-index sync after the node loop.
        if node.label in _SLUG_LIKE_LABELS:
            display_name = node.properties.get("name") or str(key_value)
            description = node.properties.get("description") or ""
            ann_targets.append((node.label, str(key_value), display_name, description))

    # ── Relations (P4-004: PG-then-KG with memory_id link) ───────────────
    # Parse run_id once; non-UUID seed runs (e.g. canonical-paradigms-seed)
    # skip the PG insert path entirely and write the relation without a
    # memory_id — those relations are timeless canonical truth.
    parsed_run_id: uuid.UUID | None
    try:
        parsed_run_id = uuid.UUID(run_id)
    except (ValueError, AttributeError, TypeError):
        parsed_run_id = None

    valid_from_dt = datetime.fromisoformat(now)
    stage_confidence = _STAGE_RELATION_CONFIDENCE.get(
        extraction.stage, _DEFAULT_RELATION_CONFIDENCE
    )
    stage_importance = _STAGE_RELATION_IMPORTANCE.get(
        extraction.stage, _DEFAULT_RELATION_IMPORTANCE
    )

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

        # Step 1: enumerate existing relations matching this identity.
        existing_rels = await _list_existing_relations(
            kg=kg,
            from_label=rel.from_label,
            from_key=from_key,
            from_value=rel.from_key_value,
            to_label=rel.to_label,
            to_key=to_key,
            to_value=rel.to_key_value,
            rel_type=rel.rel_type,
        )

        new_content_props = {
            k: v for k, v in rel.properties.items() if k not in _TEMPORAL_KEYS
        }

        # Idempotency: if any existing relation has the same content (modulo
        # temporal/memory_id/confidence), skip without writing. Works in
        # both PG-available and PG-unavailable modes.
        if any(
            {k: v for k, v in er["props"].items() if k not in _TEMPORAL_KEYS}
            == new_content_props
            for er in existing_rels
        ):
            continue

        # Step 2: find the active superseded-by-this-write version via PG
        # (we close out exactly one live PG row per triple). Skipped when
        # PG is unavailable or when no existing relation carries memory_id.
        existing_mids = [
            str(er["memory_id"]) for er in existing_rels if er.get("memory_id")
        ]
        active_meta = await _fetch_active_memory_meta(existing_mids, db=db)
        active_id: uuid.UUID | None = None
        for mid_str in active_meta:
            active_id = uuid.UUID(mid_str)
            break

        # Step 2: insert a fresh `pipeline_memories` row for the new edge
        # (skipped for non-UUID seed runs).
        relation_confidence = float(rel.properties.get("confidence", stage_confidence))
        new_memory_id: uuid.UUID | None = None
        if parsed_run_id is not None:
            new_memory_id = await _create_relation_memory(
                run_id=parsed_run_id,
                stage=extraction.stage,
                content=_relation_content(
                    from_label=rel.from_label,
                    from_key_value=rel.from_key_value,
                    rel_type=rel.rel_type,
                    to_label=rel.to_label,
                    to_key_value=rel.to_key_value,
                ),
                confidence=relation_confidence,
                importance=stage_importance,
                properties=new_content_props,
                valid_from=valid_from_dt,
                db=db,
            )

        # Step 3: create the Neo4j relation. Identity props + memory_id
        # (when present); no temporal metadata.
        kg_props: dict = dict(new_content_props)
        if new_memory_id is not None:
            kg_props["memory_id"] = str(new_memory_id)

        async def _rel_work(
            tx,
            rel=rel,
            from_key=from_key,
            to_key=to_key,
            kg_props=kg_props,
        ):
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
                    "props": kg_props,
                },
            )
            create_record = await create_result.single()
            return "missing_endpoint" if create_record is None else "created"

        try:
            outcome = await kg.execute_write(_rel_work)
        except Exception as exc:
            errors.append(f"Relation {rel.rel_type}: write failed: {exc}")
            logger.warning(
                "kg_write_skipped rel=%s %s→%s: %s",
                rel.rel_type,
                rel.from_label,
                rel.to_label,
                exc,
            )
            # Roll back the PG insert: there's no live Neo4j relation pointing
            # at the new memory_id, so close it out so retrieval doesn't pick
            # up an orphaned PG row.
            if new_memory_id is not None:
                await _close_memory(new_memory_id, valid_to=valid_from_dt, db=db)
            continue

        if outcome == "missing_endpoint":
            errors.append(
                f"Relation {rel.rel_type}: endpoint not found — "
                f"{rel.from_label}.{from_key}={rel.from_key_value!r} or "
                f"{rel.to_label}.{to_key}={rel.to_key_value!r}"
            )
            if new_memory_id is not None:
                await _close_memory(new_memory_id, valid_to=valid_from_dt, db=db)
            continue

        # Step 4: now that the new relation exists, supersede the old PG
        # row (if any). Doing this *after* the new edge is in Neo4j keeps
        # retrieval consistent: a concurrent read at any point sees either
        # both edges live (PG view: old still valid until we stamp valid_to)
        # or only the new edge live (after stamp).
        if active_id is not None:
            await _close_memory(active_id, valid_to=valid_from_dt, db=db)
            counters["relations_superseded"] += 1

        counters["relations_created"] += 1

    # ── ANN sync (best-effort) ───────────────────────────────────────────
    # After all node writes, embed the slug-like nodes and write the
    # vector to `n.embedding` so the native Neo4j vector index
    # (`<label>_embedding_idx`) can answer retrieval._link_entities_ann
    # queries without leaving Neo4j. Fire-and-forget: a Voyage outage or
    # Cypher write failure logs a warning but does not turn the KG write
    # into a failure.
    if ann_targets:
        try:
            if embeddings is not None:
                texts = [
                    f"{name}: {desc}" if desc else name
                    for (_label, _key, name, desc) in ann_targets
                ]
                vecs = await embeddings.embed_texts(texts)
                for (label, key_value, _display_name, _desc), vector in zip(
                    ann_targets, vecs, strict=True
                ):
                    key_name = node_key_map.get((label, key_value))
                    if key_name is None:
                        try:
                            key_name = kg.unique_key_for(label)
                        except (ValueError, AttributeError):
                            continue
                    if not _SAFE_IDENT.match(key_name):
                        continue
                    await kg.query(
                        f"MATCH (n:{label} {{{key_name}: $key_value}}) "
                        f"SET n.embedding = $vector",
                        {"key_value": key_value, "vector": vector},
                    )
        except Exception as exc:
            logger.warning("kg_writer: embedding sync failed (non-fatal): %s", exc)

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
