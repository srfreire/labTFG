"""Shared infrastructure — init/shutdown lifecycle for all services."""
from __future__ import annotations

import logging

from shared.database import DatabaseService
from shared.knowledge_graph import KnowledgeGraph
from shared.settings import Settings, load_settings
from shared.storage import StorageService
from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

storage: StorageService | None = None
db: DatabaseService | None = None
knowledge_graph: KnowledgeGraph | None = None
vector_store: VectorStore | None = None


async def init(settings: Settings | None = None) -> None:
    """Boot all services, expose as module-level singletons.

    Neo4j and Qdrant are optional — if unreachable, a warning is logged
    and the corresponding singleton stays None.
    """
    global storage, db, knowledge_graph, vector_store
    if settings is None:
        settings = load_settings()

    storage = StorageService(settings)
    await storage.connect()

    db = DatabaseService(settings)
    await db.connect()

    # Neo4j — optional
    try:
        kg = KnowledgeGraph(settings)
        await kg.connect()
        knowledge_graph = kg
    except Exception:
        logger.warning("Neo4j unavailable — knowledge_graph will be None", exc_info=True)
        knowledge_graph = None

    # Qdrant — optional
    try:
        vs = VectorStore(settings)
        await vs.connect()
        vector_store = vs
    except Exception:
        logger.warning("Qdrant unavailable — vector_store will be None", exc_info=True)
        vector_store = None


async def shutdown() -> None:
    """Tear down all services."""
    global storage, db, knowledge_graph, vector_store
    if storage is not None:
        await storage.close()
        storage = None
    if db is not None:
        await db.close()
        db = None
    if knowledge_graph is not None:
        await knowledge_graph.close()
        knowledge_graph = None
    if vector_store is not None:
        await vector_store.close()
        vector_store = None
