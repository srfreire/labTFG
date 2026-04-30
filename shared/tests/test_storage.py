"""Integration tests for StorageService (requires MinIO on localhost:9000)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from shared.settings import Settings
from shared.storage import StorageService

pytestmark = pytest.mark.integration


PREFIX = f"_test/{uuid.uuid4().hex}/"


@pytest_asyncio.fixture
async def storage():
    """Yield a connected StorageService and clean up test objects afterwards."""
    svc = StorageService(Settings())
    await svc.connect()
    yield svc
    # cleanup: delete everything under our unique prefix
    keys = await svc.list(PREFIX)
    for key in keys:
        await svc.delete(key)
    await svc.close()


def _key(name: str) -> str:
    return f"{PREFIX}{name}"


@pytest.mark.asyncio
async def test_put_get_roundtrip(storage: StorageService):
    key = _key("bytes.bin")
    data = b"\x00\x01\x02hello\xff"
    await storage.put(key, data)
    result = await storage.get(key)
    assert result == data


@pytest.mark.asyncio
async def test_put_text_get_text_roundtrip(storage: StorageService):
    key = _key("text.txt")
    text = "Hola, mundo! \u00e9\u00e0\u00fc \U0001f680"
    await storage.put_text(key, text)
    result = await storage.get_text(key)
    assert result == text


@pytest.mark.asyncio
async def test_list_keys(storage: StorageService):
    keys_to_create = [_key("a.txt"), _key("b.txt"), _key("c.txt")]
    for k in keys_to_create:
        await storage.put_text(k, "x")
    listed = await storage.list(PREFIX)
    assert sorted(listed) == sorted(keys_to_create)


@pytest.mark.asyncio
async def test_delete_and_exists(storage: StorageService):
    key = _key("deleteme.txt")
    await storage.put_text(key, "gone soon")
    assert await storage.exists(key) is True
    await storage.delete(key)
    assert await storage.exists(key) is False


@pytest.mark.asyncio
async def test_exists_false_for_missing(storage: StorageService):
    assert await storage.exists(_key("no-such-key")) is False
