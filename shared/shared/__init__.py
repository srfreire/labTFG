"""Shared infrastructure — init/shutdown lifecycle."""

from __future__ import annotations

import logging

from shared.database import DatabaseService
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.settings import Settings, load_settings
from shared.storage import StorageService
from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

storage: StorageService | None = None
db: DatabaseService | None = None
kg: KnowledgeGraph | None = None
vectors: VectorStore | None = None
embeddings: EmbeddingService | None = None

# Phase 2 simulation memories — populated by `init()` when
# ENABLE_KNOWLEDGE_WRITE is truthy and the infra above is available.
# Typed as `object | None` here to avoid an import cycle with `simlab`.
sim_memory_writer: object | None = None


async def init(settings: Settings | None = None) -> None:
    """Boot all infrastructure services, expose as module-level singletons."""
    global storage, db, kg, vectors, embeddings
    if settings is None:
        settings = load_settings()
    storage = StorageService(settings)
    await storage.connect()
    db = DatabaseService(settings)
    await db.connect()

    # Knowledge infrastructure — each component degrades independently.
    _unavailable: list[str] = []

    try:
        _kg = KnowledgeGraph(
            settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD
        )
        await _kg.init_schema()
        kg = _kg
    except Exception:
        logger.warning("Neo4j unavailable — KnowledgeGraph disabled", exc_info=True)
        _unavailable.append("Neo4j")

    try:
        _vs = VectorStore(settings)
        await _vs.connect()
        await _vs.init_collections()
        vectors = _vs
    except Exception:
        logger.warning("Qdrant unavailable — VectorStore disabled", exc_info=True)
        _unavailable.append("Qdrant")

    if settings.VOYAGE_API_KEY and settings.ZEROENTROPY_API_KEY:
        embeddings = EmbeddingService(
            settings.VOYAGE_API_KEY, settings.ZEROENTROPY_API_KEY
        )
    else:
        missing = [
            k
            for k in ("VOYAGE_API_KEY", "ZEROENTROPY_API_KEY")
            if not getattr(settings, k)
        ]
        _unavailable.append(f"Voyage AI ({', '.join(missing)})")

    if _unavailable:
        logger.warning(
            "Knowledge infrastructure unavailable: %s. Running in degraded mode.",
            ", ".join(_unavailable),
        )

    _init_sim_memory_writer(settings)


def _init_sim_memory_writer(settings: Settings) -> None:
    """Wire the Phase 2 simulation memories writer if the flag is on and infra is up.

    Reuses `db`, `vectors`, `embeddings` already initialised above — does not
    open new connections. Leaves `sim_memory_writer = None` silently when the
    flag is off (the common case).
    """
    global sim_memory_writer
    if not settings.ENABLE_KNOWLEDGE_WRITE:
        return

    if vectors is None or embeddings is None or db is None:
        logger.warning(
            "ENABLE_KNOWLEDGE_WRITE=true but infra missing — "
            "Qdrant/Voyage/Postgres not initialised; knowledge writes disabled",
        )
        return

    try:
        from simlab.knowledge import TrackerMemoryWriter
    except ImportError:
        logger.warning(
            "ENABLE_KNOWLEDGE_WRITE=true but simlab.knowledge import failed — "
            "knowledge writes disabled",
            exc_info=True,
        )
        return

    sim_memory_writer = TrackerMemoryWriter(
        vector_store=vectors,
        embedding_service=embeddings,
        db=db,
    )
    logger.info("Knowledge writes enabled (namespace=simulation)")


async def shutdown() -> None:
    """Tear down all services."""
    global storage, db, kg, vectors, embeddings, sim_memory_writer
    sim_memory_writer = None
    if storage is not None:
        await storage.close()
        storage = None
    if db is not None:
        await db.close()
        db = None
    if kg is not None:
        await kg.close()
        kg = None
    if vectors is not None:
        await vectors.close()
        vectors = None
    embeddings = None
