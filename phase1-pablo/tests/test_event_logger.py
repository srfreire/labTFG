import asyncio

import pytest

from decisionlab.runtime.event_logger import EventLogger


@pytest.mark.asyncio
async def test_flushes_when_batch_reaches_size_limit() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=3, max_age_s=60.0)
    await logger.add({"type": "node_add", "node": {"id": "a"}})
    await logger.add({"type": "node_add", "node": {"id": "b"}})
    assert flushed == []
    await logger.add({"type": "node_add", "node": {"id": "c"}})
    assert len(flushed) == 1
    lines = flushed[0].rstrip("\n").split("\n")
    assert len(lines) == 3
    assert '"id":"a"' in lines[0]
    assert '"id":"c"' in lines[2]


@pytest.mark.asyncio
async def test_age_trigger_reports_due_without_new_events() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=100, max_age_s=0.01)
    await logger.add({"type": "node_add"})
    assert logger.is_due() is False
    await asyncio.sleep(0.02)
    assert logger.is_due() is True
    await logger.flush()
    assert len(flushed) == 1
    assert logger.is_due() is False


@pytest.mark.asyncio
async def test_flush_on_empty_buffer_is_noop() -> None:
    calls = 0

    async def on_flush(_payload: str) -> None:
        nonlocal calls
        calls += 1

    logger = EventLogger(on_flush=on_flush)
    await logger.flush()
    assert calls == 0


@pytest.mark.asyncio
async def test_concurrent_adds_respect_batch_size() -> None:
    flushed: list[str] = []

    async def on_flush(payload: str) -> None:
        flushed.append(payload)

    logger = EventLogger(on_flush=on_flush, max_batch=10, max_age_s=60.0)
    await asyncio.gather(*[logger.add({"i": i}) for i in range(30)])
    await logger.flush()
    assert len(flushed) == 3
    for payload in flushed:
        assert payload.count("\n") == 10
