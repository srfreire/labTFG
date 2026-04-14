"""Shared infrastructure — init/shutdown lifecycle."""

from __future__ import annotations

from shared.database import DatabaseService
from shared.knowledge_graph import KnowledgeGraph
from shared.settings import Settings, load_settings
from shared.storage import StorageService

storage: StorageService | None = None
db: DatabaseService | None = None
kg: KnowledgeGraph | None = None


async def init(settings: Settings | None = None) -> None:
    """Boot all infrastructure services, expose as module-level singletons."""
    global storage, db, kg
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


async def shutdown() -> None:
    """Tear down all services."""
    global storage, db, kg
    if storage is not None:
        await storage.close()
        storage = None
    if db is not None:
        await db.close()
        db = None
    if kg is not None:
        await kg.close()
        kg = None
