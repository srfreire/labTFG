"""Tests for the shared agent tool dispatcher."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from simlab.loop import dispatch_tools


async def test_dispatch_tools_preserves_call_order_for_stateful_tools():
    seen: list[str] = []

    async def first(_params):
        await asyncio.sleep(0.01)
        seen.append("first")
        return "ok first"

    async def second(_params):
        seen.append("second")
        return "ok second"

    calls = [
        SimpleNamespace(id="tu1", name="first", input={}),
        SimpleNamespace(id="tu2", name="second", input={}),
    ]

    results = await dispatch_tools(calls, {"first": first, "second": second})

    assert seen == ["first", "second"]
    assert [r["tool_use_id"] for r in results] == ["tu1", "tu2"]
