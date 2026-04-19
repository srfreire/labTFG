"""Persist NDJSON event batches to S3 with read-then-put append semantics.

The S3 backend has no native append. We keep the full object body in memory
(cached after first load) and PUT the concatenated bytes on every append.
Acceptable at pipeline-event volumes (hundreds to low thousands per run).
"""

from __future__ import annotations

import asyncio
from typing import Protocol


class _StorageLike(Protocol):
    async def get_text(self, key: str) -> str: ...
    async def put_text(
        self, key: str, text: str, content_type: str = "text/plain"
    ) -> str: ...
    async def exists(self, key: str) -> bool: ...


class S3EventStore:
    CONTENT_TYPE = "application/x-ndjson"

    def __init__(self, storage: _StorageLike, run_id: str) -> None:
        self._storage = storage
        self._key = f"research/{run_id}/events.jsonl"
        self._tail: str | None = None  # cached full body
        self._lock = asyncio.Lock()

    async def append(self, ndjson_chunk: str) -> None:
        async with self._lock:
            if self._tail is None:
                if await self._storage.exists(self._key):
                    self._tail = await self._storage.get_text(self._key)
                else:
                    self._tail = ""
            self._tail = self._tail + ndjson_chunk
            await self._storage.put_text(self._key, self._tail, self.CONTENT_TYPE)

    @property
    def key(self) -> str:
        return self._key
