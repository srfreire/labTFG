import json
from itertools import pairwise

import pytest

from decisionlab.server import ConnectionManager


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, str] = {}

    async def get_text(self, key: str) -> str:
        return self.objects[key]

    async def put_text(
        self, key: str, text: str, content_type: str = "text/plain"
    ) -> str:
        self.objects[key] = text
        return key

    async def exists(self, key: str) -> bool:
        return key in self.objects


@pytest.mark.asyncio
async def test_emit_stamps_and_persists_events() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r1"})
    await mgr.emit({"type": "stage_change", "stage": "research", "status": "running"})
    await mgr.emit(
        {
            "type": "node_add",
            "node": {
                "id": "n1",
                "kind": "agent",
                "label": "r",
                "status": "running",
                "meta": {},
            },
        }
    )
    await mgr.emit({"type": "pipeline_done"})

    body = storage.objects["research/r1/events.jsonl"]
    lines = [json.loads(ln) for ln in body.strip().split("\n")]
    assert [e["type"] for e in lines] == [
        "run_start",
        "stage_change",
        "node_add",
        "pipeline_done",
    ]
    assert [e["seq"] for e in lines] == [1, 2, 3, 4]
    assert all(isinstance(e["ts"], (int, float)) for e in lines)
    for a, b in pairwise(lines):
        assert a["ts"] <= b["ts"]


@pytest.mark.asyncio
async def test_cancel_flushes_partial_log() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r2"})
    await mgr.emit(
        {
            "type": "node_add",
            "node": {
                "id": "n1",
                "kind": "agent",
                "label": "r",
                "status": "running",
                "meta": {},
            },
        }
    )
    await mgr.cancel_and_flush()
    body = storage.objects["research/r2/events.jsonl"]
    assert body.count("\n") == 2


@pytest.mark.asyncio
async def test_graph_clear_flushes_previous_run() -> None:
    storage = FakeStorage()
    mgr = ConnectionManager(storage=storage)
    await mgr.emit({"type": "run_start", "run_id": "r1"})
    await mgr.emit(
        {
            "type": "node_add",
            "node": {
                "id": "n1",
                "kind": "agent",
                "label": "a",
                "status": "running",
                "meta": {},
            },
        }
    )
    await mgr.emit({"type": "graph_clear"})
    await mgr.emit({"type": "run_start", "run_id": "r2"})
    await mgr.emit({"type": "pipeline_done"})
    assert storage.objects["research/r1/events.jsonl"].count("\n") == 3
    assert storage.objects["research/r2/events.jsonl"].count("\n") == 2
