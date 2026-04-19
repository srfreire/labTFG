"""Batch-buffering helper for pipeline event persistence.

Decouples batching policy from the storage backend. The caller supplies an
async ``on_flush`` callback that receives an NDJSON payload to persist.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

FlushFn = Callable[[str], Awaitable[None]]


class EventLogger:
    def __init__(
        self,
        on_flush: FlushFn,
        max_batch: int = 50,
        max_age_s: float = 2.0,
    ) -> None:
        self._on_flush = on_flush
        self._max_batch = max_batch
        self._max_age_s = max_age_s
        self._buf: list[dict] = []
        self._buf_started_at: float | None = None
        self._lock = asyncio.Lock()

    async def add(self, event: dict) -> None:
        async with self._lock:
            if not self._buf:
                self._buf_started_at = time.monotonic()
            self._buf.append(event)
            if len(self._buf) >= self._max_batch:
                await self._flush_locked()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    def is_due(self) -> bool:
        if not self._buf or self._buf_started_at is None:
            return False
        return (time.monotonic() - self._buf_started_at) >= self._max_age_s

    async def _flush_locked(self) -> None:
        if not self._buf:
            return
        payload = "".join(
            json.dumps(e, separators=(",", ":")) + "\n" for e in self._buf
        )
        self._buf.clear()
        self._buf_started_at = None
        await self._on_flush(payload)
