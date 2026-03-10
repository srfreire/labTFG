import pytest

from decisionlab.runtime.dispatcher import dispatch_tools


class FakeToolCall:
    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input


@pytest.mark.asyncio
async def test_dispatch_single_tool():
    async def greet(params: dict) -> str:
        return f"hello {params['name']}"

    calls = [FakeToolCall(id="t1", name="greet", input={"name": "world"})]
    results = await dispatch_tools(calls, {"greet": greet})

    assert len(results) == 1
    assert results[0]["tool_use_id"] == "t1"
    assert results[0]["content"] == "hello world"
    assert "is_error" not in results[0]


@pytest.mark.asyncio
async def test_dispatch_multiple_tools_in_parallel():
    import asyncio

    order = []

    async def slow_tool(params: dict) -> str:
        order.append(f"start_{params['id']}")
        await asyncio.sleep(0.05)
        order.append(f"end_{params['id']}")
        return f"done_{params['id']}"

    calls = [
        FakeToolCall(id="t1", name="slow", input={"id": "a"}),
        FakeToolCall(id="t2", name="slow", input={"id": "b"}),
    ]
    results = await dispatch_tools(calls, {"slow": slow_tool})

    assert len(results) == 2
    # Both started before either finished = parallel
    assert order[0].startswith("start_")
    assert order[1].startswith("start_")


@pytest.mark.asyncio
async def test_dispatch_handles_error_in_one_tool():
    async def good_tool(params: dict) -> str:
        return "ok"

    async def bad_tool(params: dict) -> str:
        raise ValueError("boom")

    calls = [
        FakeToolCall(id="t1", name="good", input={}),
        FakeToolCall(id="t2", name="bad", input={}),
    ]
    results = await dispatch_tools(calls, {"good": good_tool, "bad": bad_tool})

    assert len(results) == 2
    ok_result = next(r for r in results if r["tool_use_id"] == "t1")
    err_result = next(r for r in results if r["tool_use_id"] == "t2")
    assert ok_result["content"] == "ok"
    assert err_result["is_error"] is True
    assert "boom" in err_result["content"]


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error():
    calls = [FakeToolCall(id="t1", name="nonexistent", input={})]
    results = await dispatch_tools(calls, {"real_tool": lambda p: "x"})

    assert len(results) == 1
    assert results[0]["is_error"] is True
    assert "Unknown tool" in results[0]["content"]
    assert "nonexistent" in results[0]["content"]
