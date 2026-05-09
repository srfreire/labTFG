"""Knowledge-graph admin: stats, reset, snapshot/restore, raw query.

Operates on the ``services.kg`` (Neo4j) passed in by the caller — entry
points (CLI, suite runner) build a ``Services`` via ``init_services()`` and
thread it through. Every public function raises ``RuntimeError`` when the
KG is not connected so failures surface at the entry point rather than as
cryptic Cypher errors deeper in the call stack.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.knowledge_graph import KnowledgeGraph
    from shared.services import Services

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KGStats:
    """Counts of nodes/relations in the active KG."""

    total_nodes: int
    total_relations: int
    by_label: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_nodes": self.total_nodes,
            "total_relations": self.total_relations,
            "by_label": dict(self.by_label),
            "by_type": dict(self.by_type),
        }


def _require_kg(services: Services) -> KnowledgeGraph:
    if services.kg is None:
        raise RuntimeError(
            "knowledge graph not initialised — call init_services() first "
            "and ensure NEO4J_* env vars point at a reachable instance"
        )
    return services.kg


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


async def stats(services: Services) -> KGStats:
    """Count nodes and active (non-superseded) relations.

    Per P4-004 every Neo4j relation is in principle "current": temporal
    validity now lives in ``pipeline_memories`` (joined via
    ``r.memory_id``).  These counts include every edge — superseded
    versions and the active replacement both contribute. For an "as-of"
    view callers should go through ``KnowledgeGraph.query_at_time``.
    """
    kg = _require_kg(services)

    total_nodes_rows = await kg.query("MATCH (n) RETURN count(n) AS n")
    total_nodes = int(total_nodes_rows[0]["n"]) if total_nodes_rows else 0

    total_rels_rows = await kg.query("MATCH ()-[r]->() RETURN count(r) AS n")
    total_relations = int(total_rels_rows[0]["n"]) if total_rels_rows else 0

    label_rows = await kg.query(
        "MATCH (n) UNWIND labels(n) AS lab "
        "RETURN lab AS label, count(*) AS n ORDER BY n DESC"
    )
    by_label = {row["label"]: int(row["n"]) for row in label_rows}

    type_rows = await kg.query(
        "MATCH ()-[r]->() "
        "RETURN type(r) AS rel_type, count(r) AS n ORDER BY n DESC"
    )
    by_type = {row["rel_type"]: int(row["n"]) for row in type_rows}

    return KGStats(
        total_nodes=total_nodes,
        total_relations=total_relations,
        by_label=by_label,
        by_type=by_type,
    )


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


async def reset(services: Services, *, confirm: bool = False) -> int:
    """Delete every node and relation. Returns the number of nodes deleted.

    The ``confirm=True`` requirement is a safety belt: this is destructive
    and the eval harness explicitly opts in.
    """
    if not confirm:
        raise RuntimeError(
            "kgadmin.reset requires confirm=True to proceed (destructive)"
        )
    kg = _require_kg(services)
    before_rows = await kg.query("MATCH (n) RETURN count(n) AS n")
    before = int(before_rows[0]["n"]) if before_rows else 0
    await kg.query("MATCH (n) DETACH DELETE n")
    logger.info("kgadmin.reset: deleted %d nodes (and all their relations)", before)
    return before


# ---------------------------------------------------------------------------
# snapshot / restore
# ---------------------------------------------------------------------------


async def snapshot(services: Services) -> dict:
    """Return a JSON-serialisable dump of the entire KG.

    Shape::

        {
          "nodes": [{"id": ..., "labels": [...], "props": {...}}, ...],
          "relations": [{"id": ..., "source": ..., "target": ...,
                          "type": ..., "props": {...}}, ...],
        }

    Includes superseded relations so a ``restore`` exactly reproduces the
    temporal history.
    """
    kg = _require_kg(services)
    node_rows = await kg.query(
        "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, "
        "properties(n) AS props"
    )
    rel_rows = await kg.query(
        "MATCH (a)-[r]->(b) RETURN elementId(r) AS id, "
        "elementId(a) AS source, elementId(b) AS target, "
        "type(r) AS type, properties(r) AS props"
    )
    return {
        "nodes": [
            {"id": r["id"], "labels": list(r["labels"]), "props": dict(r["props"])}
            for r in node_rows
        ],
        "relations": [
            {
                "id": r["id"],
                "source": r["source"],
                "target": r["target"],
                "type": r["type"],
                "props": dict(r["props"]),
            }
            for r in rel_rows
        ],
    }


async def snapshot_to_file(path: Path, services: Services) -> None:
    """Convenience: ``snapshot()`` → ``json.dump`` to *path*."""
    snap = await snapshot(services)
    path.write_text(json.dumps(snap, indent=2, default=str))
    logger.info(
        "kgadmin.snapshot: wrote %d nodes / %d relations to %s",
        len(snap["nodes"]),
        len(snap["relations"]),
        path,
    )


async def restore(snap: dict, services: Services, *, reset_first: bool = True) -> None:
    """Restore a snapshot produced by ``snapshot()``.

    By default this wipes the KG first (``reset_first=True``) so the
    target ends up identical to the snapshot — node element-IDs change,
    so we re-MERGE on label+props rather than try to preserve them.
    Pass ``reset_first=False`` to layer the snapshot on top of existing
    data (rarely useful — risks duplicate nodes when natural-key MERGE
    isn't possible).
    """
    kg = _require_kg(services)
    if reset_first:
        await reset(services, confirm=True)

    # Element-ID → newly-created internal id (Neo4j-side)
    id_map: dict[str, int] = {}
    for node in snap["nodes"]:
        labels = node["labels"]
        if not labels:
            continue
        # Build a CREATE per node — we can't MERGE generically because
        # natural keys vary by label. Restore is for round-trips, not
        # for cross-instance dedup.
        label_str = ":".join(labels)
        result = await kg.query(
            f"CREATE (n:{label_str}) SET n = $props RETURN id(n) AS new_id",
            {"props": node["props"]},
        )
        if result:
            id_map[node["id"]] = int(result[0]["new_id"])

    for rel in snap["relations"]:
        src = id_map.get(rel["source"])
        dst = id_map.get(rel["target"])
        if src is None or dst is None:
            logger.warning(
                "restore: skipping relation %s — endpoint missing in id_map",
                rel["id"],
            )
            continue
        rel_type = rel["type"]
        await kg.query(
            "MATCH (a), (b) WHERE id(a) = $src AND id(b) = $dst "
            f"CREATE (a)-[r:{rel_type}]->(b) SET r = $props",
            {"src": src, "dst": dst, "props": rel["props"]},
        )

    logger.info(
        "kgadmin.restore: created %d nodes / %d relations",
        len(snap["nodes"]),
        len(snap["relations"]),
    )


async def restore_from_file(path: Path, services: Services) -> None:
    """Convenience: ``json.load`` *path* → ``restore()`` (with reset_first=True)."""
    snap = json.loads(path.read_text())
    await restore(snap, services, reset_first=True)


# ---------------------------------------------------------------------------
# raw query
# ---------------------------------------------------------------------------


async def query(
    cypher: str, params: dict | None = None, *, services: Services
) -> list[dict]:
    """Run an arbitrary Cypher query. Thin pass-through to ``services.kg.query``."""
    kg = _require_kg(services)
    return await kg.query(cypher, params or {})
