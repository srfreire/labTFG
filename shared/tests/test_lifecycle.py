"""Tests for shared.init() / shutdown() lifecycle."""
import uuid

import pytest

import shared
from shared.database import DatabaseService
from shared.storage import StorageService


@pytest.mark.asyncio
async def test_before_init_is_none():
    """Module-level singletons are None before init."""
    # Reset in case another test already ran init
    await shared.shutdown()
    assert shared.storage is None
    assert shared.db is None


@pytest.mark.asyncio
async def test_init_boots_services():
    """init() creates usable StorageService and DatabaseService."""
    await shared.init()
    try:
        assert isinstance(shared.storage, StorageService)
        assert isinstance(shared.db, DatabaseService)
    finally:
        await shared.shutdown()


@pytest.mark.asyncio
async def test_storage_works_after_init():
    """StorageService is functional after init."""
    await shared.init()
    try:
        key = f"test-lifecycle/{uuid.uuid4()}.txt"
        await shared.storage.put_text(key, "lifecycle test")
        result = await shared.storage.get_text(key)
        assert result == "lifecycle test"
        await shared.storage.delete(key)
    finally:
        await shared.shutdown()


@pytest.mark.asyncio
async def test_db_works_after_init():
    """DatabaseService is functional after init."""
    await shared.init()
    try:
        async with shared.db.get_session() as session:
            from sqlalchemy import text
            row = await session.execute(text("SELECT 1 AS ok"))
            assert row.scalar() == 1
    finally:
        await shared.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cleans_up():
    """shutdown() sets singletons to None."""
    await shared.init()
    await shared.shutdown()
    assert shared.storage is None
    assert shared.db is None


@pytest.mark.asyncio
async def test_store_backward_compat():
    """Old store.py functions still work independently."""
    from shared.store import init_db, create_experiment, get_experiment
    init_db()
    exp_id = create_experiment("lifecycle backward compat test")
    exp = get_experiment(exp_id)
    assert exp is not None
    assert exp["description"] == "lifecycle backward compat test"
