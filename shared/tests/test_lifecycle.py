"""Tests for ``init_services()`` / ``shutdown_services()`` lifecycle."""

import uuid

import pytest

from shared.database import DatabaseService
from shared.services import init_services, shutdown_services
from shared.storage import StorageService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_init_services_returns_usable_services():
    """``init_services()`` returns a Services with connected Storage + DB."""
    services = await init_services()
    try:
        assert isinstance(services.storage, StorageService)
        assert isinstance(services.db, DatabaseService)
    finally:
        await shutdown_services(services)


@pytest.mark.asyncio
async def test_storage_works_after_init():
    """StorageService is functional after init_services."""
    services = await init_services()
    try:
        key = f"test-lifecycle/{uuid.uuid4()}.txt"
        await services.storage.put_text(key, "lifecycle test")
        result = await services.storage.get_text(key)
        assert result == "lifecycle test"
        await services.storage.delete(key)
    finally:
        await shutdown_services(services)


@pytest.mark.asyncio
async def test_db_works_after_init():
    """DatabaseService is functional after init_services."""
    services = await init_services()
    try:
        async with services.db.get_session() as session:
            from sqlalchemy import text

            row = await session.execute(text("SELECT 1 AS ok"))
            assert row.scalar() == 1
    finally:
        await shutdown_services(services)


@pytest.mark.asyncio
async def test_double_shutdown_is_safe():
    """Calling shutdown twice on the same Services should not raise."""
    services = await init_services()
    await shutdown_services(services)
    # Second shutdown is a no-op (each service.close() handles re-entry).
    await shutdown_services(services)
