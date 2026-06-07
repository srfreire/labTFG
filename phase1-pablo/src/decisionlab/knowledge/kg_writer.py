"""KG population: write ExtractionResult to Neo4j with node dedup and temporal provenance."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from decisionlab.knowledge.ids import (
    normalize_extraction_ids,
    scoped_formulation_id,
    scoped_parameter_id,
    scoped_variable_id,
    split_scoped_id,
)
from decisionlab.knowledge.models import ExtractionResult, KGWriteResult
from decisionlab.tools.reports import slugify
from shared.knowledge_graph import KG_RELATION_NAMESPACE, KnowledgeGraph
from shared.pipeline_memories import memory_content_hash

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
    semantic_props: dict | None = None,
) -> str:
    """Stable text encoding of a relation identity triple.

    Used as ``pipeline_memories.content`` so the row is human-readable in
    SQL inspection and survives the JSONB round-trip without ambiguity.
    """
    base = f"{from_label}.{from_key_value} -[{rel_type}]-> {to_label}.{to_key_value}"
    if not semantic_props:
        return base
    props = json.dumps(semantic_props, sort_keys=True, ensure_ascii=False, default=str)
    return f"{base} {props}"


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
    content_hash = memory_content_hash(content)
    naive_valid_from = (
        valid_from.replace(tzinfo=None) if valid_from.tzinfo is not None else valid_from
    )

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO pipeline_memories "
                    "(id, content, content_hash, namespace, memory_type, source_stage, "
                    "run_id, importance, confidence, valid_from, metadata) "
                    "VALUES (:id, :content, :content_hash, :namespace, "
                    ":memory_type, :stage, "
                    ":run_id, :importance, :confidence, :valid_from, "
                    "CAST(:metadata AS JSONB))"
                ),
                {
                    "id": new_id,
                    "content": content,
                    "content_hash": content_hash,
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
        reused = await _fetch_existing_relation_memory_id(
            run_id=run_id,
            stage=stage,
            content_hash=content_hash,
            db=db,
        )
        if reused is not None:
            return reused
        logger.warning(
            "kg_writer: pipeline_memories insert failed (non-fatal) "
            "content=%r run_id=%s: %s",
            content,
            run_id,
            exc,
        )
        return None


async def _fetch_existing_relation_memory_id(
    *,
    run_id: uuid.UUID,
    stage: str,
    content_hash: str,
    db: DatabaseService | None,
) -> uuid.UUID | None:
    """Return an existing live relation-memory id for an idempotent insert."""
    if db is None:
        return None

    try:
        from sqlalchemy import text as sql_text

        async with db.get_session() as session:
            row = (
                await session.execute(
                    sql_text(
                        "SELECT id FROM pipeline_memories "
                        "WHERE run_id = :run_id "
                        "  AND source_stage = :stage "
                        "  AND namespace = :namespace "
                        "  AND memory_type = :memory_type "
                        "  AND content_hash = :content_hash "
                        "  AND valid_to IS NULL "
                        "ORDER BY created_at ASC "
                        "LIMIT 1"
                    ),
                    {
                        "run_id": run_id,
                        "stage": stage[:100] if stage else "kg_writer",
                        "namespace": KG_RELATION_NAMESPACE,
                        "memory_type": "semantic",
                        "content_hash": content_hash,
                    },
                )
            ).first()
            if row is None:
                return None
            return uuid.UUID(str(row.id))
    except Exception:
        logger.debug(
            "kg_writer: existing relation-memory lookup failed",
            exc_info=True,
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
_MAX_KEY_VALUE_LEN = 160

# Labels whose natural key is a human-readable identifier (slug, name, id).
_SLUG_LIKE_LABELS = frozenset(
    {
        "Paradigm",
        "Variable",
        "Postulate",
        "Formulation",
        "Model",
        "Parameter",
        "BrainRegion",
    }
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
_RELATION_PROVENANCE_KEYS = frozenset(
    {
        "source",
        "source_stage",
        "reason",
        "evidence",
        "identity_hash",
    }
)
_RELATION_IDENTITY_IGNORED_KEYS = _TEMPORAL_KEYS | _RELATION_PROVENANCE_KEYS
_MISSING = object()
_NODE_LIFECYCLE_KEYS = frozenset(
    {"created_at", "updated_at", "last_run_at", "run_count", "embedding"}
)

# Property names tried, in priority order, when the LLM-declared natural_key is
# missing from `properties`. Covers the common identifier vocabulary.
_FALLBACK_KEY_NAMES = ("slug", "id", "doi", "url", "name", "title")
_ENDPOINT_ALIAS_PROPS = (
    "slug",
    "id",
    "doi",
    "url",
    "name",
    "title",
    "formulation_id",
    "latex",
    "plaintext",
    "symbol",
    "display_name",
)
_ENDPOINT_LOOKUP_PROPS: dict[str, tuple[tuple[str, str], ...]] = {
    "Paper": (("title", "doi"), ("title", "title"), ("doi", "doi")),
    "Variable": (("name", "id"), ("id", "id")),
    "Equation": (
        ("plaintext", "latex"),
        ("plaintext", "plaintext"),
        ("latex", "latex"),
    ),
    "Parameter": (
        ("id", "id"),
        ("display_name", "id"),
        ("symbol", "id"),
        ("name", "id"),
        ("display_name", "name"),
        ("symbol", "name"),
        ("name", "name"),
    ),
    "Formulation": (("id", "id"), ("local_id", "id"), ("name", "id")),
    "Model": (("formulation_id", "formulation_id"),),
}
_EndpointMap = dict[tuple[str, str], tuple[str, object] | None]


def _node_create_props(properties: dict, *, now: str) -> dict:
    """Properties for a newly-created node.

    Incoming lifecycle-ish values are ignored so a stale extraction cannot set
    timestamps/counts. Neo4j's MERGE pattern still writes the natural key.
    """
    semantic_props = _sanitize_neo4j_props(
        {k: v for k, v in properties.items() if k not in _NODE_LIFECYCLE_KEYS}
    )
    return {
        **semantic_props,
        "created_at": now,
        "run_count": 1,
        "last_run_at": now,
    }


def _sanitize_neo4j_props(properties: dict) -> dict:
    """Return properties Neo4j can store without dropping the whole entity."""
    sanitized: dict = {}
    for key, value in properties.items():
        clean = _sanitize_neo4j_value(value)
        if clean is _DROP_PROPERTY:
            continue
        sanitized[key] = clean
    return sanitized


def _relation_semantic_props(properties: dict) -> dict:
    """Properties that change the meaning/version of a relation."""
    return _sanitize_neo4j_props(
        {
            k: v
            for k, v in properties.items()
            if k not in _RELATION_IDENTITY_IGNORED_KEYS
        }
    )


def _relation_identity_hash(
    *,
    from_label: str,
    from_value: object,
    rel_type: str,
    to_label: str,
    to_value: object,
    semantic_props: dict,
) -> str:
    payload = {
        "from_label": from_label,
        "from_value": str(from_value),
        "rel_type": rel_type,
        "to_label": to_label,
        "to_value": str(to_value),
        "semantic_props": semantic_props,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


_DROP_PROPERTY = object()


def _sanitize_neo4j_value(value: object) -> object:
    if value is None:
        return _DROP_PROPERTY
    if isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list | tuple | set):
        cleaned = [
            item
            for raw_item in value
            if (item := _sanitize_neo4j_scalar(raw_item)) is not _DROP_PROPERTY
        ]
        return cleaned
    return _DROP_PROPERTY


def _sanitize_neo4j_scalar(value: object) -> object:
    if value is None:
        return _DROP_PROPERTY
    if isinstance(value, str | bool | int | float):
        return value
    return _DROP_PROPERTY


def _node_match_semantic_props(properties: dict) -> dict:
    """Safe semantic props that may be filled if absent on an existing node.

    Existing semantic properties are deliberately not overwritten. The Cypher
    generated from this dict uses ``coalesce(n.key, value)``.
    """
    return _sanitize_neo4j_props(
        {
            k: v
            for k, v in properties.items()
            if isinstance(k, str)
            and k not in _NODE_LIFECYCLE_KEYS
            and _SAFE_IDENT.match(k)
            and v is not None
        }
    )


def _node_match_set_clause(properties: dict) -> tuple[str, dict]:
    """Return additional ON MATCH SET clauses + params for missing props."""
    clauses: list[str] = []
    params: dict = {}
    for idx, key in enumerate(sorted(properties)):
        param_name = f"match_prop_{idx}"
        clauses.append(f"n.`{key}` = coalesce(n.`{key}`, ${param_name})")
        params[param_name] = properties[key]
    return ", ".join(clauses), params


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

    Scoped labels bypass the schema/declared/fallback chain. Their canonical
    IDs are always derived here, even if an incoming extraction carried a stale
    local key.
    """
    if node.label == "Variable":
        name = node.properties.get("name")
        if not isinstance(name, str):
            return None
        variable_id = scoped_variable_id(
            name,
            paradigm_slug=node.properties.get("paradigm_slug"),
            formulation_id=node.properties.get("formulation_id"),
        )
        if not variable_id:
            return None
        _scope, local_id = split_scoped_id(variable_id)
        if local_id.startswith("h-"):
            return None
        formulation_id = node.properties.get("formulation_id")
        if formulation_id:
            scoped_form_id, local_formulation_id = scoped_formulation_id(
                formulation_id,
                paradigm_slug=node.properties.get("paradigm_slug"),
            )
            if scoped_form_id:
                node.properties["formulation_id"] = scoped_form_id
                node.properties.setdefault("local_formulation_id", local_formulation_id)
        node.properties["id"] = variable_id
        node.properties.setdefault("local_id", local_id)
        return ("id", variable_id)

    if node.label == "Formulation":
        scoped_id, local_id = scoped_formulation_id(
            node.properties.get("id") or node.properties.get("formulation_id"),
            paradigm_slug=node.properties.get("paradigm_slug"),
            name=node.properties.get("name"),
        )
        if not scoped_id:
            return None
        node.properties["id"] = scoped_id
        node.properties.setdefault("local_id", local_id)
        return ("id", scoped_id)

    if node.label == "Model":
        formulation_id = node.properties.get("formulation_id")
        if formulation_id:
            scoped_id, local_id = scoped_formulation_id(
                formulation_id,
                paradigm_slug=node.properties.get("paradigm_slug"),
            )
            if not scoped_id:
                return None
            node.properties["formulation_id"] = scoped_id
            node.properties.setdefault("local_formulation_id", local_id)
            node.properties.setdefault("id", scoped_id)
            return ("formulation_id", scoped_id)

    if node.label == "Parameter":
        formulation_id = node.properties.get("formulation_id")
        if formulation_id:
            scoped_id, local_id = scoped_formulation_id(
                formulation_id,
                paradigm_slug=node.properties.get("paradigm_slug"),
            )
            if not scoped_id:
                return None
            node.properties["formulation_id"] = scoped_id
            node.properties.setdefault("local_formulation_id", local_id)
        param_id = scoped_parameter_id(
            node.properties.get("name")
            or node.properties.get("symbol")
            or node.properties.get("display_name"),
            formulation_id=node.properties.get("formulation_id"),
            paradigm_slug=node.properties.get("paradigm_slug"),
        )
        if not param_id:
            return None
        node.properties["id"] = param_id
        return ("id", param_id)

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


def _add_endpoint_alias(
    endpoint_key_map: _EndpointMap,
    *,
    label: str,
    alias_value: object,
    key_name: str,
    key_value: object,
) -> None:
    """Register one relation-endpoint alias for a node.

    LLM extractors often emit relations against a display key (Paper.title,
    Variable.name, Equation.plaintext) while the writer canonicalizes the node
    to a schema key (Paper.doi, Variable.id, Equation.latex).  The map lets the
    relation loop translate those display keys back to the actual MERGE key.
    If the same alias points to multiple canonical nodes, mark it ambiguous and
    force the relation to fail instead of silently connecting to the wrong node.
    """
    if alias_value is None or alias_value == "":
        return

    alias_key = (label, str(alias_value))
    canonical = (key_name, key_value)
    existing = endpoint_key_map.get(alias_key, _MISSING)
    if existing is _MISSING:
        endpoint_key_map[alias_key] = canonical
    elif existing != canonical:
        endpoint_key_map[alias_key] = None


def _register_endpoint_aliases(
    endpoint_key_map: _EndpointMap,
    *,
    label: str,
    properties: dict,
    key_name: str,
    key_value: object,
) -> None:
    """Register canonical and display aliases for one written node."""
    _add_endpoint_alias(
        endpoint_key_map,
        label=label,
        alias_value=key_value,
        key_name=key_name,
        key_value=key_value,
    )
    for prop in _ENDPOINT_ALIAS_PROPS:
        if prop in properties:
            _add_endpoint_alias(
                endpoint_key_map,
                label=label,
                alias_value=properties.get(prop),
                key_name=key_name,
                key_value=key_value,
            )

    if label == "Variable":
        name = properties.get("name")
        if isinstance(name, str):
            _add_endpoint_alias(
                endpoint_key_map,
                label=label,
                alias_value=slugify(name),
                key_name=key_name,
                key_value=key_value,
            )

    if label == "Postulate":
        postulate_id = properties.get("id")
        if isinstance(postulate_id, str) and ":" in postulate_id:
            _add_endpoint_alias(
                endpoint_key_map,
                label=label,
                alias_value=postulate_id.rsplit(":", 1)[1],
                key_name=key_name,
                key_value=key_value,
            )


async def _resolve_orphan_formulation_ids(
    extraction: ExtractionResult,
    kg: KnowledgeGraph,
) -> None:
    """Attach local builder/formulation IDs to existing scoped KG IDs.

    Artifact IDs are intentionally local because they double as filenames.
    Neo4j IDs are label-wide, so the KG representation scopes Formulations as
    ``<paradigm>:<local>``. If an incoming batch lacks the paradigm and exactly
    one existing Formulation has that local id, use the existing global id.
    Ambiguous or missing matches stay under ``orphan:`` and fail visibly later.
    """
    orphan_ids = sorted(_collect_orphan_formulation_ids(extraction))
    if not orphan_ids:
        return

    aliases: dict[str, str] = {}
    for orphan_id in orphan_ids:
        _scope, local_id = split_scoped_id(orphan_id)
        if not local_id:
            continue
        resolved = await _lookup_unique_formulation_id_by_local_id(kg, local_id)
        if resolved is None or resolved == orphan_id:
            continue
        aliases[orphan_id] = resolved
        aliases[local_id] = resolved

    if not aliases:
        return

    for node in extraction.nodes:
        props = node.properties
        if node.label == "Formulation":
            raw_id = props.get("id")
            if isinstance(raw_id, str) and raw_id in aliases:
                props["id"] = aliases[raw_id]
                scope, local_id = split_scoped_id(aliases[raw_id])
                if scope:
                    props["paradigm_slug"] = scope
                props.setdefault("local_id", local_id)

        raw_fid = props.get("formulation_id")
        if isinstance(raw_fid, str) and raw_fid in aliases:
            props["formulation_id"] = aliases[raw_fid]
            scope, local_id = split_scoped_id(aliases[raw_fid])
            if scope:
                props["paradigm_slug"] = scope
            props.setdefault("local_formulation_id", local_id)
            if node.label == "Model" and props.get("id") == raw_fid:
                props["id"] = aliases[raw_fid]

    for rel in extraction.relations:
        if rel.from_key_value in aliases:
            rel.from_key_value = aliases[rel.from_key_value]
        if rel.to_key_value in aliases:
            rel.to_key_value = aliases[rel.to_key_value]

    normalize_extraction_ids(extraction)


def _collect_orphan_formulation_ids(extraction: ExtractionResult) -> set[str]:
    values: set[str] = set()

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        scope, local_id = split_scoped_id(value)
        if scope == "orphan" and local_id:
            values.add(value)

    for node in extraction.nodes:
        if node.label == "Formulation":
            add(node.properties.get("id"))
        if node.label in {"Equation", "Variable", "Parameter", "Model"}:
            add(node.properties.get("formulation_id"))

    for rel in extraction.relations:
        if rel.from_label in {"Formulation", "Model"}:
            add(rel.from_key_value)
        if rel.to_label == "Formulation":
            add(rel.to_key_value)

    return values


async def _lookup_unique_formulation_id_by_local_id(
    kg: KnowledgeGraph,
    local_id: str,
) -> str | None:
    rows = await kg.query(
        "MATCH (f:Formulation) "
        "WHERE f.local_id = $local_id "
        "   OR f.id = $local_id "
        "   OR f.id ENDS WITH $scoped_suffix "
        "RETURN f.id AS id "
        "LIMIT 2",
        {"local_id": local_id, "scoped_suffix": f":{local_id}"},
    )
    ids = {
        row.get("id")
        for row in rows
        if isinstance(row.get("id"), str) and row.get("id")
    }
    if len(ids) == 1:
        return next(iter(ids))
    return None


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
    normalize_extraction_ids(extraction)
    await _resolve_orphan_formulation_ids(extraction, kg)

    now = datetime.now(UTC).isoformat()
    run_id = extraction.run_id

    counters = {
        "nodes_created": 0,
        "nodes_merged": 0,
        "relations_created": 0,
        "relations_superseded": 0,
    }
    errors: list[str] = []

    # Map (label, relation_key_value) → (canonical_key_property, canonical_value)
    # built during node processing, so relation lookups can use display keys
    # emitted by extraction while still matching the actual MERGE identity.
    node_key_map: dict[tuple[str, str], str] = {}
    endpoint_key_map: _EndpointMap = {}

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
            create_props = _node_create_props(node.properties, now=now)
            match_props = _node_match_semantic_props(node.properties)
            semantic_set_clause, semantic_set_params = _node_match_set_clause(
                match_props
            )
            match_set_clause = (
                "n.updated_at = $now, "
                "n.last_run_at = $now, "
                "n.run_count = coalesce(n.run_count, 0) + 1"
            )
            if semantic_set_clause:
                match_set_clause = f"{match_set_clause}, {semantic_set_clause}"

            cypher = (
                f"MERGE (n:{node.label} {{{key_name}: $key_value}}) "
                f"ON CREATE SET n += $create_props "
                f"ON MATCH SET {match_set_clause} "
                f"RETURN n.updated_at IS NULL AS was_created"
            )
            result = await tx.run(
                cypher,
                {
                    "key_value": key_value,
                    "create_props": create_props,
                    "match_props": match_props,
                    "now": now,
                    **semantic_set_params,
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
        _register_endpoint_aliases(
            endpoint_key_map,
            label=node.label,
            properties=node.properties,
            key_name=key_name,
            key_value=key_value,
        )
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

        from_endpoint = await _resolve_endpoint(
            rel.from_label,
            rel.from_key_value,
            endpoint_key_map,
            kg,
            key_name=rel.from_key,
        )
        to_endpoint = await _resolve_endpoint(
            rel.to_label,
            rel.to_key_value,
            endpoint_key_map,
            kg,
            key_name=rel.to_key,
        )
        if from_endpoint is None or to_endpoint is None:
            errors.append(
                f"Relation {rel.rel_type}: cannot resolve key for "
                f"{rel.from_label}={rel.from_key_value!r} or "
                f"{rel.to_label}={rel.to_key_value!r}"
            )
            continue
        from_key, from_value = from_endpoint
        to_key, to_value = to_endpoint

        # Step 1: enumerate existing relations matching this identity.
        existing_rels = await _list_existing_relations(
            kg=kg,
            from_label=rel.from_label,
            from_key=from_key,
            from_value=from_value,
            to_label=rel.to_label,
            to_key=to_key,
            to_value=to_value,
            rel_type=rel.rel_type,
        )

        stored_relation_props = _sanitize_neo4j_props(
            {k: v for k, v in rel.properties.items() if k not in _TEMPORAL_KEYS}
        )
        new_semantic_props = _relation_semantic_props(stored_relation_props)

        # Idempotency: if any existing relation has the same content (modulo
        # temporal/provenance metadata), skip without writing. Works in both
        # PG-available and PG-unavailable modes.
        if any(
            _relation_semantic_props(er["props"]) == new_semantic_props
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
                    from_key_value=from_value,
                    rel_type=rel.rel_type,
                    to_label=rel.to_label,
                    to_key_value=to_value,
                    semantic_props=new_semantic_props,
                ),
                confidence=relation_confidence,
                importance=stage_importance,
                properties=stored_relation_props,
                valid_from=valid_from_dt,
                db=db,
            )

        # Step 3: create the Neo4j relation. Identity props + memory_id
        # (when present); no temporal metadata.
        identity_hash = _relation_identity_hash(
            from_label=rel.from_label,
            from_value=from_value,
            rel_type=rel.rel_type,
            to_label=rel.to_label,
            to_value=to_value,
            semantic_props=new_semantic_props,
        )
        kg_props: dict = dict(stored_relation_props)
        kg_props["identity_hash"] = identity_hash
        if new_memory_id is not None:
            kg_props["memory_id"] = str(new_memory_id)

        async def _rel_work(
            tx,
            rel=rel,
            from_key=from_key,
            from_value=from_value,
            to_key=to_key,
            to_value=to_value,
            kg_props=kg_props,
            identity_hash=identity_hash,
        ):
            marker = str(uuid.uuid4())
            memory_id = kg_props.get("memory_id")
            merge_cypher = (
                f"MATCH (a:{rel.from_label} {{{from_key}: $from_val}}), "
                f"(b:{rel.to_label} {{{to_key}: $to_val}}) "
                f"MERGE (a)-[r:{rel.rel_type} {{identity_hash: $identity_hash}}]->(b) "
                "ON CREATE SET r += $props, r._merge_marker = $marker "
                "WITH r, coalesce(r._merge_marker, '') = $marker AS created "
                "REMOVE r._merge_marker "
                "RETURN elementId(r) AS rid, created"
            )
            merge_result = await tx.run(
                merge_cypher,
                {
                    "from_val": from_value,
                    "to_val": to_value,
                    "props": kg_props,
                    "identity_hash": identity_hash,
                    "marker": marker,
                    "memory_id": memory_id,
                },
            )
            merge_record = await merge_result.single()
            if merge_record is None:
                return "missing_endpoint"
            return "created" if merge_record["created"] else "merged"

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
                f"{rel.from_label}.{from_key}={from_value!r} "
                f"(from {rel.from_key_value!r}) or "
                f"{rel.to_label}.{to_key}={to_value!r} "
                f"(from {rel.to_key_value!r})"
            )
            if new_memory_id is not None:
                await _close_memory(new_memory_id, valid_to=valid_from_dt, db=db)
            continue
        if outcome == "merged":
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


async def _resolve_endpoint(
    label: str,
    key_value: str,
    endpoint_key_map: _EndpointMap,
    kg: KnowledgeGraph,
    *,
    key_name: str | None = None,
) -> tuple[str, object] | None:
    """Determine which Neo4j property/value to match a relation endpoint on.

    First checks aliases populated during this extraction. This covers display
    keys such as ``Paper.title`` and ``Variable.name`` after the node was
    canonicalized to ``Paper.doi`` or ``Variable.id``. Then it probes existing
    nodes for labels with known display/canonical key pairs. If no alias is
    found, falls back to the schema's unique key for cross-extraction references.
    """
    if key_name:
        if not _SAFE_IDENT.match(key_name):
            return None
        return key_name, key_value

    lookup_key = (label, str(key_value))
    mapped = endpoint_key_map.get(lookup_key, _MISSING)
    if mapped is None:
        return None
    if mapped is not _MISSING:
        return mapped

    looked_up = await _lookup_existing_endpoint(label, key_value, kg)
    if looked_up is not None:
        return looked_up

    try:
        return kg.unique_key_for(label), key_value
    except ValueError:
        return None


async def _lookup_existing_endpoint(
    label: str,
    key_value: str,
    kg: KnowledgeGraph,
) -> tuple[str, object] | None:
    """Resolve cross-extraction endpoint aliases already present in Neo4j.

    This intentionally returns a match only when exactly one node is found. For
    example, a bare ``Variable.name`` that exists under multiple paradigms is
    ambiguous and should fail rather than attach an edge to the wrong concept.
    """
    lookup_props = _ENDPOINT_LOOKUP_PROPS.get(label, ())
    if not lookup_props:
        return None

    for alias_prop, canonical_prop in lookup_props:
        if not _SAFE_IDENT.match(alias_prop) or not _SAFE_IDENT.match(canonical_prop):
            continue
        rows = await kg.query(
            f"MATCH (n:{label} {{{alias_prop}: $value}}) "
            f"RETURN n.{canonical_prop} AS key_value "
            "LIMIT 2",
            {"value": key_value},
        )
        values = [
            row.get("key_value")
            for row in rows
            if row.get("key_value") is not None and row.get("key_value") != ""
        ]
        if len(values) == 1:
            return canonical_prop, values[0]
        if len(values) > 1:
            return None

    return None


def _resolve_key(
    label: str,
    key_value: str,
    node_key_map: dict[tuple[str, str], str],
    kg: KnowledgeGraph,
) -> str | None:
    """Backward-compatible key-name helper for older tests/imports."""
    mapped = node_key_map.get((label, key_value))
    if mapped is not None:
        return mapped
    try:
        return kg.unique_key_for(label)
    except ValueError:
        return None
