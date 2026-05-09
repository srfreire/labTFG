"""One-shot backfill of ``n.embedding`` on slug-like KG nodes (P4-002).

Walks every Paradigm/Variable/Postulate/Formulation/Model node, embeds
``"<name>: <description>"``, and writes the vector to ``n.embedding``
via Cypher. Populates the native Neo4j vector index that replaced the
dropped ``kg_entities_dense`` Qdrant collection.

Idempotent — re-running with no schema changes is cheap. Existing
``n.embedding`` values are overwritten with a fresh embedding (Voyage
caches make this near-free).

Usage:

    uv run scripts/backfill_kg_entities.py
"""

from __future__ import annotations

import asyncio
import logging

from shared.knowledge_graph import _VECTOR_INDEX_LABELS
from shared.services import init_services, shutdown_services

logger = logging.getLogger(__name__)


async def _backfill(services) -> None:
    if services.kg is None or services.embeddings is None:
        raise RuntimeError("init_services() did not bring up KG / EmbeddingService")

    for label in _VECTOR_INDEX_LABELS:
        unique_key = services.kg.unique_key_for(label)
        rows = await services.kg.query(
            f"MATCH (n:{label}) "
            f"RETURN n.{unique_key} AS key_value, "
            "COALESCE(n.name, n.slug, n.id) AS name, "
            "COALESCE(n.description, '') AS description"
        )
        if not rows:
            logger.info("backfill: no %s nodes", label)
            continue

        texts = [
            f"{r['name']}: {r['description']}" if r["description"] else r["name"]
            for r in rows
        ]
        vecs = await services.embeddings.embed_texts(texts)

        for r, v in zip(rows, vecs, strict=True):
            await services.kg.query(
                f"MATCH (n:{label} {{{unique_key}: $key_value}}) "
                "SET n.embedding = $vector",
                {"key_value": r["key_value"], "vector": v},
            )
        logger.info("backfill: wrote n.embedding on %d %s nodes", len(rows), label)


async def main() -> None:
    services = await init_services()
    try:
        await _backfill(services)
    finally:
        await shutdown_services(services)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
