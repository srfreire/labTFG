"""Idempotent seeding of canonical Paradigm umbrellas into the KG + vector index.

Phase C's enum-constrained Researcher emission only collapses variant slugs
(``q-learning``, ``td-rl-foraging``) into their canonical umbrella
(``reinforcement-learning``) when the umbrella is already a Paradigm node
in Neo4j AND retrievable from the vector store under namespace=paradigm.
``seed_canonical_paradigms`` reads the JSON fixture and merges both, so a
fresh ``kg reset`` run starts pre-seeded rather than discovering umbrellas
one variant at a time.

Idempotent: re-running on a populated KG is a no-op for nodes whose slug
already exists (Cypher ``MERGE`` semantics) and a re-upsert for vector
points (deterministic UUID5 IDs).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.embedding import EmbeddingService
    from shared.knowledge_graph import KnowledgeGraph
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "evals"
    / "fixtures"
    / "canonical-paradigms.json"
)

_SEED_RUN_ID = "canonical-paradigms-seed"


def _load_fixture(path: Path | None = None) -> list[dict]:
    fixture = path or _FIXTURE_PATH
    with open(fixture) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{fixture}: expected a list, got {type(data).__name__}")
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError(f"{fixture}: every entry must be an object, got {entry!r}")
        for required in ("slug", "name", "definition"):
            if required not in entry or not isinstance(entry[required], str):
                raise ValueError(
                    f"{fixture}: entry missing required string field {required!r}: {entry!r}"
                )
    return data


def _seed_point_id(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{_SEED_RUN_ID}:paradigm:{slug}"))


async def seed_canonical_paradigms(
    kg: KnowledgeGraph,
    embedding_service: EmbeddingService | None = None,
    vector_store: VectorStore | None = None,
    *,
    fixture_path: Path | None = None,
) -> dict:
    """MERGE canonical Paradigm umbrellas and (optionally) index their definitions.

    Returns a counter dict with ``nodes_created``, ``nodes_merged`` and
    ``vectors_indexed``. Vector indexing is skipped when either
    ``embedding_service`` or ``vector_store`` is None — the KG side is
    still seeded so the classifier sees the umbrellas even on a degraded
    deployment.
    """
    paradigms = _load_fixture(fixture_path)
    now = datetime.now(UTC).isoformat()

    nodes_created = 0
    nodes_merged = 0

    async def _seed_one(tx, slug, name, definition):
        cypher = (
            "MERGE (p:Paradigm {slug: $slug}) "
            "ON CREATE SET p.name = $name, p.description = $description, "
            "  p.created_at = $now, p.run_ids = [$run_id], p.canonical = true "
            "ON MATCH SET p.canonical = true "
            "RETURN p.created_at = $now AS was_created"
        )
        result = await tx.run(
            cypher,
            {
                "slug": slug,
                "name": name,
                "description": definition,
                "now": now,
                "run_id": _SEED_RUN_ID,
            },
        )
        return await result.single()

    for entry in paradigms:
        record = await kg.execute_write(
            _seed_one, entry["slug"], entry["name"], entry["definition"]
        )
        if record and record["was_created"]:
            nodes_created += 1
        else:
            nodes_merged += 1

    vectors_indexed = 0
    if embedding_service is not None and vector_store is not None:
        texts = [p["definition"] for p in paradigms]
        vectors = await embedding_service.embed_texts(texts)
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"embed_texts returned {len(vectors)} vectors for {len(texts)} texts"
            )
        for entry, vec in zip(paradigms, vectors, strict=True):
            point_id = _seed_point_id(entry["slug"])
            payload = {
                "entity_id": point_id,
                "namespace": "paradigm",
                "source_stage": "seed",
                "run_id": _SEED_RUN_ID,
                "importance": 9.0,
                "confidence": 1.0,
                "created_at": now,
                "text_preview": entry["definition"][:200],
                "slug": entry["slug"],
                "name": entry["name"],
            }
            await vector_store.upsert_dense(
                collection="artifacts_dense",
                id=point_id,
                vector=vec,
                payload=payload,
            )
            await vector_store.upsert_sparse(
                collection="artifacts_sparse",
                id=point_id,
                text=f"{entry['name']}: {entry['definition']}",
                payload=payload,
            )
            vectors_indexed += 1

    logger.info(
        "Seeded canonical paradigms: created=%d merged=%d vectors=%d",
        nodes_created,
        nodes_merged,
        vectors_indexed,
    )
    return {
        "nodes_created": nodes_created,
        "nodes_merged": nodes_merged,
        "vectors_indexed": vectors_indexed,
    }
