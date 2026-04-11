"""Shared infrastructure — init/shutdown lifecycle for StorageService + DatabaseService."""
from __future__ import annotations

from shared.database import DatabaseService
from shared.settings import Settings, load_settings
from shared.storage import StorageService

storage: StorageService | None = None
db: DatabaseService | None = None


async def init(settings: Settings | None = None) -> None:
    """Boot StorageService and DatabaseService, expose as module-level singletons."""
    global storage, db
    if settings is None:
        settings = load_settings()
    storage = StorageService(settings)
    await storage.connect()
    db = DatabaseService(settings)
    await db.connect()


async def shutdown() -> None:
    """Tear down both services."""
    global storage, db
    if storage is not None:
        await storage.close()
        storage = None
    if db is not None:
        await db.close()
        db = None
