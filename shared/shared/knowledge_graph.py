"""Async Neo4j client for the knowledge backbone graph."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict, TypeVar

from neo4j import AsyncGraphDatabase, AsyncManagedTransaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Default namespace for relations bookkept as ``pipeline_memories`` rows under
# the P4-004 PG-as-temporal-source-of-truth pattern.
KG_RELATION_NAMESPACE = "kg_relation"


class _SchemaEntry(TypedDict):
    unique_key: str
    indexes: list[str]


# Node labels → {"unique_key": <prop>, "indexes": [<additional indexed props>]}
_SCHEMA: dict[str, _SchemaEntry] = {
    "Paradigm": {"unique_key": "slug", "indexes": ["name"]},
    "Variable": {"unique_key": "id", "indexes": ["paradigm_slug", "name"]},
    "Equation": {"unique_key": "latex", "indexes": []},
    "BrainRegion": {"unique_key": "name", "indexes": []},
    "Author": {"unique_key": "name", "indexes": []},
    "Paper": {"unique_key": "doi", "indexes": []},
    "Postulate": {"unique_key": "id", "indexes": []},
    "Formulation": {"unique_key": "id", "indexes": []},
    "Parameter": {"unique_key": "name", "indexes": []},
    "Model": {"unique_key": "formulation_id", "indexes": []},
    "Reflection": {"unique_key": "id", "indexes": []},
    "RollupReflection": {"unique_key": "id", "indexes": ["month"]},
}

_ALLOWED_LABELS = frozenset(_SCHEMA)
_ALLOWED_REL_TYPES = frozenset(
    [
        "SUPPORTS",
        "CONTRADICTS",
        "EXTENDS",
        "MEASURES",
        "MODULATES",
        "AUTHORED",
        "DERIVES_FROM",
        "IMPLEMENTS",
        "USES_EQUATION",
        "BELONGS_TO",
        "CITES",
    ]
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Labels that get a native Neo4j vector index on `n.embedding` (P4-002).
# Replaces the dropped Qdrant `kg_entities_dense` collection — entity
# linking now goes via `db.index.vector.queryNodes` on these indexes.
_VECTOR_INDEX_LABELS = ("Paradigm", "Variable", "Postulate", "Formulation", "Model")
_VECTOR_INDEX_DIMENSIONS = 1024


def vector_index_name(label: str) -> str:
    """Return the Neo4j vector index name for a slug-like label."""
    if label not in _VECTOR_INDEX_LABELS:
        raise ValueError(f"No vector index for label: {label!r}")
    return f"{label.lower()}_embedding_idx"


def _check_label(label: str) -> None:
    if label not in _ALLOWED_LABELS:
        raise ValueError(f"Unknown label: {label!r}")


def _check_rel_type(rel_type: str) -> None:
    if rel_type not in _ALLOWED_REL_TYPES:
        raise ValueError(f"Unknown relation type: {rel_type!r}")


def _check_ident(value: str, name: str) -> None:
    if not _IDENT_RE.match(value):
        raise ValueError(f"Invalid {name}: {value!r}")


class KnowledgeGraph:
    """Thin async wrapper around Neo4j for the knowledge backbone schema."""

    SCHEMA = _SCHEMA

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def init_schema(self) -> None:
        """Create uniqueness constraints, indexes, and vector indexes. Idempotent."""
        async with self._driver.session() as session:
            for label, info in _SCHEMA.items():
                key_prop = info["unique_key"]
                extra_indexes = info["indexes"]
                constraint_name = f"uniq_{label}_{key_prop}"
                await session.run(
                    f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{key_prop} IS UNIQUE"
                )
                for prop in extra_indexes:
                    index_name = f"idx_{label}_{prop}"
                    await session.run(
                        f"CREATE INDEX {index_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.{prop})"
                    )
            for label in _VECTOR_INDEX_LABELS:
                index_name = vector_index_name(label)
                await session.run(
                    f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
                    f"FOR (n:{label}) ON (n.embedding) "
                    "OPTIONS { indexConfig: { "
                    "`vector.dimensions`: $dims, "
                    "`vector.similarity_function`: 'cosine' "
                    "}}",
                    {"dims": _VECTOR_INDEX_DIMENSIONS},
                )

            # One-shot cleanup of pre-P0-004 n.run_ids arrays. Idempotent — once
            # all nodes have been processed this becomes a no-op.
            result = await session.run(
                "MATCH (n) WHERE n.run_ids IS NOT NULL "
                "REMOVE n.run_ids "
                "RETURN count(n) AS cleaned"
            )
            record = await result.single()
            if record and record["cleaned"] > 0:
                logger.info(
                    "init_schema: cleared n.run_ids on %d nodes", record["cleaned"]
                )

    async def create_node(self, label: str, properties: dict) -> str:
        """Create a node and return its element ID."""
        _check_label(label)
        async with self._driver.session() as session:
            result = await session.run(
                f"CREATE (n:{label} $props) RETURN elementId(n) AS eid",
                {"props": properties},
            )
            record = await result.single()
            if record is None:
                raise RuntimeError(f"CREATE {label} returned no record")
            return record["eid"]

    async def create_relation(
        self,
        from_label: str,
        from_key: str,
        from_value: str | int,
        to_label: str,
        to_key: str,
        to_value: str | int,
        rel_type: str,
        properties: dict | None = None,
    ) -> None:
        """Create a typed relation between two nodes.

        Per P4-004 the temporal lifecycle of a relation lives in Postgres
        ``pipeline_memories``: callers seed a row first, then pass the new
        memory_id via ``properties`` so this method can write only the
        identity triple + ``memory_id`` link.  No ``created_at`` /
        ``valid_from`` / ``valid_to`` is stamped here anymore.

        Raises ValueError if either endpoint node is not found.
        """
        _check_label(from_label)
        _check_label(to_label)
        _check_rel_type(rel_type)
        _check_ident(from_key, "from_key")
        _check_ident(to_key, "to_key")

        props = dict(properties or {})

        async with self._driver.session() as session:
            result = await session.run(
                f"MATCH (a:{from_label} {{{from_key}: $fv}}), "
                f"(b:{to_label} {{{to_key}: $tv}}) "
                f"CREATE (a)-[r:{rel_type} $props]->(b) "
                f"RETURN elementId(r) AS rid",
                {"fv": from_value, "tv": to_value, "props": props},
            )
            record = await result.single()
            if record is None:
                raise ValueError(
                    f"Cannot create {rel_type}: "
                    f"{from_label}.{from_key}={from_value!r} or "
                    f"{to_label}.{to_key}={to_value!r} not found"
                )

    async def get_node(
        self, label: str, key_property: str, key_value: str | int
    ) -> dict | None:
        """Return a node's properties or None if not found."""
        _check_label(label)
        _check_ident(key_property, "key_property")
        async with self._driver.session() as session:
            result = await session.run(
                f"MATCH (n:{label} {{{key_property}: $val}}) RETURN properties(n) AS props",
                {"val": key_value},
            )
            record = await result.single()
            return record["props"] if record else None

    async def get_neighbors(
        self,
        label: str,
        key_property: str,
        key_value: str | int,
        rel_type: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        """Return properties of neighboring nodes, optionally filtered by relation type."""
        _check_label(label)
        _check_ident(key_property, "key_property")
        if rel_type is not None:
            _check_rel_type(rel_type)
        if direction not in ("out", "in", "both"):
            raise ValueError(f"Invalid direction: {direction!r}")

        rel = f":{rel_type}" if rel_type else ""

        if direction == "out":
            match = f"MATCH (n:{label} {{{key_property}: $val}})-[r{rel}]->(m)"
        elif direction == "in":
            match = f"MATCH (n:{label} {{{key_property}: $val}})<-[r{rel}]-(m)"
        else:
            match = f"MATCH (n:{label} {{{key_property}: $val}})-[r{rel}]-(m)"

        async with self._driver.session() as session:
            result = await session.run(
                f"{match} RETURN properties(m) AS props",
                {"val": key_value},
            )
            records = [r async for r in result]
            return [r["props"] for r in records]

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Execute arbitrary Cypher and return deserialized results."""
        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            records = [r async for r in result]
            return [dict(r) for r in records]

    async def query_at_time(
        self,
        cypher: str,
        as_of: datetime,
        *,
        session: AsyncSession,
        namespace: str = KG_RELATION_NAMESPACE,
        params: dict | None = None,
    ) -> list[dict]:
        """Execute Cypher against the set of relations valid at *as_of*.

        Per P4-004, Postgres ``pipeline_memories`` is the source of truth
        for relation temporal validity.  This is a two-step helper:

          1. PG SELECT — fetch ``pipeline_memories.id`` rows whose namespace
             matches *namespace* and whose
             ``valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)``.
          2. Neo4j MATCH — inject ``WHERE r.memory_id IS NULL OR
             r.memory_id IN $_valid_ids`` before the ``RETURN`` so only
             relations referencing a still-valid PG row (or pre-P4-004
             seed relations with no ``memory_id`` at all) survive.

        The input *cypher* must bind relations as ``r`` and contain a
        ``RETURN`` keyword.  If no ``RETURN`` is found the filter is
        appended as a ``WITH * WHERE`` clause (useful for sub-queries).
        """
        valid_ids = await select_valid_memory_ids(session, as_of, namespace=namespace)

        temporal_clause = "WHERE r.memory_id IS NULL OR r.memory_id IN $_valid_ids"

        upper = cypher.upper()
        ret_idx = upper.rfind("RETURN")
        if ret_idx != -1:
            match_part = cypher[:ret_idx].rstrip()
            return_part = cypher[ret_idx:]
            wrapped = f"{match_part}\n{temporal_clause}\n{return_part}"
        else:
            wrapped = f"{cypher}\nWITH * {temporal_clause}"

        merged = dict(params or {})
        merged["_valid_ids"] = valid_ids
        merged["_as_of"] = as_of.isoformat()
        return await self.query(wrapped, merged)

    async def get_node_history(
        self,
        label: str,
        key_property: str,
        key_value: str | int,
        *,
        session: AsyncSession,
        namespace: str = KG_RELATION_NAMESPACE,
    ) -> list[dict]:
        """Return every version of a node's relations, oldest first.

        Each row carries ``type``/``props``/``neighbor`` as before, plus
        ``memory_id``, ``valid_from``, ``valid_to``, and ``confidence``
        joined from the corresponding ``pipeline_memories`` row.  Pre-P4-004
        seed relations (no ``memory_id``) are returned with the temporal
        fields set to ``None`` and sort first.
        """
        _check_label(label)
        _check_ident(key_property, "key_property")
        cypher = (
            f"MATCH (n:{label} {{{key_property}: $val}})-[r]-(m) "
            f"RETURN type(r) AS type, properties(r) AS props, "
            f"properties(m) AS neighbor, r.memory_id AS memory_id"
        )
        rows = await self.query(cypher, {"val": key_value})
        if not rows:
            return rows

        memory_ids = [row["memory_id"] for row in rows if row.get("memory_id")]
        meta = await fetch_memory_temporal_meta(
            session, memory_ids, namespace=namespace
        )
        for row in rows:
            mid = row.get("memory_id")
            entry = meta.get(mid) if mid else None
            row["valid_from"] = entry["valid_from"] if entry else None
            row["valid_to"] = entry["valid_to"] if entry else None
            row["confidence"] = entry["confidence"] if entry else None

        rows.sort(
            key=lambda r: (
                r.get("valid_from") is None,
                r.get("valid_from") or "",
            )
        )
        return rows

    @staticmethod
    def unique_key_for(label: str) -> str:
        """Return the unique-key property name for a node label."""
        _check_label(label)
        return _SCHEMA[label]["unique_key"]

    async def execute_write(
        self,
        work: Callable[[AsyncManagedTransaction], Awaitable[_T]],
    ) -> _T:
        """Run *work* inside a managed write transaction (auto-retry on transient errors)."""
        async with self._driver.session() as session:
            return await session.execute_write(work)  # type: ignore[return-value]

    async def close(self) -> None:
        """Close the driver."""
        await self._driver.close()


async def select_valid_memory_ids(
    session: AsyncSession,
    as_of: datetime,
    *,
    namespace: str = KG_RELATION_NAMESPACE,
) -> list[str]:
    """Return the ``pipeline_memories`` ids valid at *as_of*, as strings.

    Returns string-encoded UUIDs (Neo4j has no native UUID type, so the
    relation property ``r.memory_id`` is stored as a string).  An empty
    list is a perfectly valid answer — it means no relation in the given
    namespace was live at *as_of*.
    """
    from sqlalchemy import select

    from shared.models import PipelineMemory

    naive_as_of = as_of.replace(tzinfo=None) if as_of.tzinfo is not None else as_of

    stmt = select(PipelineMemory.id).where(
        PipelineMemory.namespace == namespace,
        PipelineMemory.valid_from <= naive_as_of,
        (PipelineMemory.valid_to.is_(None)) | (PipelineMemory.valid_to > naive_as_of),
    )
    result = await session.execute(stmt)
    return [str(row[0]) for row in result.all()]


async def fetch_memory_temporal_meta(
    session: AsyncSession,
    memory_ids: list[str],
    *,
    namespace: str = KG_RELATION_NAMESPACE,
) -> dict[str, dict]:
    """Hydrate temporal + confidence metadata for a batch of memory_ids.

    Returns ``{str(memory_id): {"valid_from", "valid_to", "confidence"}}``.
    Ids that don't resolve (deleted PG row, foreign namespace) are absent
    from the map — callers fall back to None on miss.
    """
    if not memory_ids:
        return {}

    import uuid as _uuid

    from sqlalchemy import select

    from shared.models import PipelineMemory

    parsed: list[_uuid.UUID] = []
    for mid in memory_ids:
        try:
            parsed.append(_uuid.UUID(str(mid)))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return {}

    stmt = select(
        PipelineMemory.id,
        PipelineMemory.valid_from,
        PipelineMemory.valid_to,
        PipelineMemory.confidence,
    ).where(
        PipelineMemory.id.in_(parsed),
        PipelineMemory.namespace == namespace,
    )
    result = await session.execute(stmt)
    out: dict[str, dict] = {}
    for row in result.all():
        out[str(row.id)] = {
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "confidence": row.confidence,
        }
    return out
