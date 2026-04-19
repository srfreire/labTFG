import pytest

from decisionlab.runtime.event_store import S3EventStore


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, str] = {}
        self.put_calls: int = 0
        self.get_calls: int = 0

    async def get_text(self, key: str) -> str:
        self.get_calls += 1
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]

    async def put_text(
        self, key: str, text: str, content_type: str = "text/plain"
    ) -> str:
        self.put_calls += 1
        self.objects[key] = text
        return key

    async def exists(self, key: str) -> bool:
        return key in self.objects


@pytest.mark.asyncio
async def test_first_append_creates_object() -> None:
    storage = FakeStorage()
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1,"type":"node_add"}\n')
    assert (
        storage.objects["research/abc/events.jsonl"] == '{"seq":1,"type":"node_add"}\n'
    )
    assert storage.put_calls == 1


@pytest.mark.asyncio
async def test_subsequent_appends_concatenate() -> None:
    storage = FakeStorage()
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1}\n')
    await store.append('{"seq":2}\n{"seq":3}\n')
    assert (
        storage.objects["research/abc/events.jsonl"]
        == '{"seq":1}\n{"seq":2}\n{"seq":3}\n'
    )


@pytest.mark.asyncio
async def test_caches_existing_content_after_first_load() -> None:
    storage = FakeStorage()
    storage.objects["research/abc/events.jsonl"] = '{"seq":0}\n'
    store = S3EventStore(storage, run_id="abc")
    await store.append('{"seq":1}\n')
    await store.append('{"seq":2}\n')
    assert storage.get_calls == 1
    assert (
        storage.objects["research/abc/events.jsonl"]
        == '{"seq":0}\n{"seq":1}\n{"seq":2}\n'
    )
