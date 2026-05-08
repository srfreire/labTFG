"""One-shot backfill: walk every Paradigm/Variable/Postulate node in
Neo4j, embed (label, name, description), upsert into kg_entities_dense.

Idempotent — re-running with no changes is cheap (Voyage caches
embeddings; Qdrant upserts overwrite on point id collision).
"""

from __future__ import annotations

import asyncio
import logging

import shared

logger = logging.getLogger(__name__)


LABELS = ("Paradigm", "Variable", "Postulate")


async def _backfill() -> None:
    if shared.kg is None or shared.vectors is None or shared.embeddings is None:
        raise RuntimeError(
            "shared.init() did not bring up KG / VectorStore / EmbeddingService"
        )

    for label in LABELS:
        rows = await shared.kg.query(
            f"MATCH (n:{label}) "
            "RETURN elementId(n) AS id, "
            "COALESCE(n.slug, n.name, n.id) AS key_value, "
            "COALESCE(n.name, n.slug) AS name, "
            "COALESCE(n.description, '') AS description"
        )
        if not rows:
            logger.info("backfill: no %s nodes", label)
            continue

        texts = [
            f"{r['name']}: {r['description']}" if r["description"] else r["name"]
            for r in rows
        ]
        vecs = await shared.embeddings.embed_texts(texts)

        for r, v in zip(rows, vecs):
            point_id = f"{label}:{r['key_value']}"
            await shared.vectors.upsert_dense(
                "kg_entities_dense",
                id=point_id,
                vector=v,
                payload={
                    "label": label,
                    "key_value": r["key_value"],
                    "name": r["name"],
                },
            )
        logger.info("backfill: upserted %d %s entities", len(rows), label)


async def main() -> None:
    await shared.init()
    try:
        await _backfill()
    finally:
        await shared.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
