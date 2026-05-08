"""Async Neo4j client for the knowledge backbone graph."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict, TypeVar

from neo4j import AsyncGraphDatabase, AsyncManagedTransaction

_T = TypeVar("_T")


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
        """Create a typed relation between two nodes, injecting temporal metadata.

        Raises ValueError if either endpoint node is not found.
        """
        _check_label(from_label)
        _check_label(to_label)
        _check_rel_type(rel_type)
        _check_ident(from_key, "from_key")
        _check_ident(to_key, "to_key")

        props = dict(properties or {})
        now = datetime.now(UTC).isoformat()
        props.setdefault("created_at", now)
        props.setdefault("valid_from", now)

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
        params: dict | None = None,
    ) -> list[dict]:
        """Execute Cypher with a temporal validity filter on relations.

        Injects a ``WHERE`` clause before the ``RETURN`` that keeps only
        relations valid at *as_of*:
            r.valid_from <= $_as_of AND (r.valid_to IS NULL OR r.valid_to > $_as_of)

        The input *cypher* must bind relations as ``r`` and contain a
        ``RETURN`` keyword.  If no ``RETURN`` is found the filter is
        appended as a ``WITH * WHERE`` clause (useful for sub-queries).
        """
        as_of_iso = as_of.isoformat()
        temporal_clause = (
            "WHERE r.valid_from <= $_as_of "
            "AND (r.valid_to IS NULL OR r.valid_to > $_as_of)"
        )

        # Insert temporal filter before the RETURN clause
        upper = cypher.upper()
        ret_idx = upper.rfind("RETURN")
        if ret_idx != -1:
            match_part = cypher[:ret_idx].rstrip()
            return_part = cypher[ret_idx:]
            wrapped = f"{match_part}\n{temporal_clause}\n{return_part}"
        else:
            wrapped = f"{cypher}\nWITH * {temporal_clause}"

        merged = dict(params or {})
        merged["_as_of"] = as_of_iso
        return await self.query(wrapped, merged)

    async def get_node_history(
        self,
        label: str,
        key_property: str,
        key_value: str | int,
    ) -> list[dict]:
        """Return all versions of a node's relations ordered by valid_from.

        Returns a list of dicts with keys: type, props, neighbor — showing
        how the node's relationships evolved over time.
        """
        _check_label(label)
        _check_ident(key_property, "key_property")
        cypher = (
            f"MATCH (n:{label} {{{key_property}: $val}})-[r]-(m) "
            f"RETURN type(r) AS type, properties(r) AS props, "
            f"properties(m) AS neighbor "
            f"ORDER BY r.valid_from ASC"
        )
        return await self.query(cypher, {"val": key_value})

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
