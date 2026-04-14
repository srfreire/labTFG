"""Shared infrastructure — init/shutdown lifecycle."""

from __future__ import annotations

from shared.database import DatabaseService
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.settings import Settings, load_settings
from shared.storage import StorageService
from shared.vector_store import VectorStore

storage: StorageService | None = None
db: DatabaseService | None = None
kg: KnowledgeGraph | None = None
vectors: VectorStore | None = None
embeddings: EmbeddingService | None = None


async def init(settings: Settings | None = None) -> None:
    """Boot all infrastructure services, expose as module-level singletons."""
    global storage, db, kg, vectors, embeddings
    if settings is None:
        settings = load_settings()
    storage = StorageService(settings)
    await storage.connect()
    db = DatabaseService(settings)
    await db.connect()
    kg = KnowledgeGraph(
        settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD
    )
    await kg.init_schema()
    vectors = VectorStore(settings)
    await vectors.connect()
    await vectors.init_collections()
    if settings.VOYAGE_API_KEY:
        embeddings = EmbeddingService(settings.VOYAGE_API_KEY)
    else:
        import warnings

        warnings.warn(
            "VOYAGE_API_KEY not set — EmbeddingService unavailable",
            stacklevel=2,
        )


async def shutdown() -> None:
    """Tear down all services."""
    global storage, db, kg, vectors, embeddings
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
