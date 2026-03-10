# Researcher Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Researcher agent that discovers decision-making paradigms via breadth-first search and delegates depth research to parallel sub-agents.

**Architecture:** Clean architecture with ports/adapters. Manual async agentic loop with parallel tool dispatch. Domain models and ports in `domain/`, concrete adapters in `adapters/`, reusable runtime in `runtime/`, shared tool definitions in `tools/`, agent orchestration in `agents/`.

**Tech Stack:** Python 3.12+, `anthropic` SDK (async), `duckduckgo-search`, Semantic Scholar API, `pytest` + `pytest-asyncio`

**Spec:** `phase1-pablo/docs/researcher-design.md`

---

## Chunk 1: Foundation — Dependencies, Domain Models, Ports

### Task 1: Update dependencies

**Files:**
- Modify: `phase1-pablo/pyproject.toml`

- [ ] **Step 1: Replace claude-agent-sdk with anthropic + duckduckgo-search**

In `pyproject.toml`, replace dependencies:

```toml
dependencies = [
    "anthropic>=0.52.0",
    "duckduckgo-search>=7.0.0",
    "numpy>=2.4.3",
    "python-dotenv>=1.2.2",
    "questionary>=2.1.1",
    "rich>=14.3.3",
    "typer>=0.24.1",
]
```

Add `pytest-asyncio` to dev deps:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=0.26.0",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `cd phase1-pablo && uv sync`
Expected: resolves and installs without errors

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/pyproject.toml phase1-pablo/uv.lock
git commit -m "feat[phase1]: replace claude-agent-sdk with anthropic + duckduckgo-search"
```

---

### Task 2: Domain models

**Files:**
- Create: `src/decisionlab/domain/__init__.py`
- Create: `src/decisionlab/domain/models.py`
- Create: `tests/domain/__init__.py`
- Create: `tests/domain/test_models.py`

- [ ] **Step 1: Write tests for domain models**

```python
# tests/domain/test_models.py
from decisionlab.domain.models import SearchResult, PaperResult, Paradigm, ResearchReport


def test_search_result_creation():
    r = SearchResult(title="Homeostatic regulation", url="https://example.com", snippet="A model of...")
    assert r.title == "Homeostatic regulation"
    assert r.url == "https://example.com"


def test_paper_result_creation():
    p = PaperResult(
        paper_id="abc123",
        title="A predictive model",
        abstract="We present...",
        authors=["Jacquier", "Alvarez"],
        year=2014,
    )
    assert p.paper_id == "abc123"
    assert len(p.authors) == 2


def test_paradigm_creation():
    paper = PaperResult(paper_id="1", title="T", abstract="A", authors=["X"], year=2020)
    p = Paradigm(id="homeostatic", name="Homeostatic model", description="Desc", references=[paper])
    assert p.id == "homeostatic"
    assert len(p.references) == 1


def test_research_report_creation():
    paradigm = Paradigm(id="h", name="H", description="D", references=[])
    report = ResearchReport(
        paradigms=[paradigm],
        summary="# Summary",
        deep_reports={"h": "# Deep report"},
    )
    assert len(report.paradigms) == 1
    assert "h" in report.deep_reports
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/domain/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'decisionlab.domain'`

- [ ] **Step 3: Implement domain models**

```python
# src/decisionlab/domain/__init__.py
```

```python
# src/decisionlab/domain/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class PaperResult:
    paper_id: str
    title: str
    abstract: str
    authors: list[str]
    year: int


@dataclass(frozen=True)
class Paradigm:
    id: str
    name: str
    description: str
    references: list[PaperResult] = field(default_factory=list)


@dataclass
class ResearchReport:
    paradigms: list[Paradigm]
    summary: str
    deep_reports: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/domain/test_models.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/domain/ phase1-pablo/tests/domain/
git commit -m "feat[phase1]: add domain models (SearchResult, PaperResult, Paradigm, ResearchReport)"
```

---

### Task 3: Domain ports

**Files:**
- Create: `src/decisionlab/domain/ports.py`
- Create: `tests/domain/test_ports.py`

- [ ] **Step 1: Write tests for ports**

```python
# tests/domain/test_ports.py
from decisionlab.domain.ports import WebSearchPort, PaperSearchPort
from decisionlab.domain.models import SearchResult, PaperResult


class FakeSearch:
    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(title="T", url="http://x", snippet="S")]


class FakePapers:
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        return []

    async def fetch(self, paper_id: str) -> PaperResult:
        return PaperResult(paper_id=paper_id, title="T", abstract="A", authors=[], year=2020)


def test_fake_search_satisfies_web_search_port():
    assert isinstance(FakeSearch(), WebSearchPort)


def test_fake_papers_satisfies_paper_search_port():
    assert isinstance(FakePapers(), PaperSearchPort)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/domain/test_ports.py -v`
Expected: FAIL — cannot import `WebSearchPort`

- [ ] **Step 3: Implement ports**

```python
# src/decisionlab/domain/ports.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from decisionlab.domain.models import PaperResult, SearchResult


@runtime_checkable
class WebSearchPort(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...


@runtime_checkable
class PaperSearchPort(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]: ...
    async def fetch(self, paper_id: str) -> PaperResult: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/domain/test_ports.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/domain/ports.py phase1-pablo/tests/domain/test_ports.py
git commit -m "feat[phase1]: add domain ports (WebSearchPort, PaperSearchPort)"
```

---

### Task 4: Mock adapters

**Files:**
- Create: `src/decisionlab/adapters/__init__.py`
- Create: `src/decisionlab/adapters/mock.py`
- Create: `tests/adapters/__init__.py`
- Create: `tests/adapters/test_mock.py`

- [ ] **Step 1: Write tests for mock adapters**

```python
# tests/adapters/test_mock.py
import pytest

from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.domain.ports import WebSearchPort, PaperSearchPort


def test_mock_web_search_satisfies_port():
    assert isinstance(MockWebSearch(), WebSearchPort)


def test_mock_paper_search_satisfies_port():
    assert isinstance(MockPaperSearch(), PaperSearchPort)


@pytest.mark.asyncio
async def test_mock_web_search_returns_results():
    adapter = MockWebSearch()
    results = await adapter.search("test query")
    assert len(results) > 0
    assert results[0].title


@pytest.mark.asyncio
async def test_mock_paper_search_returns_results():
    adapter = MockPaperSearch()
    results = await adapter.search("test query")
    assert len(results) > 0


@pytest.mark.asyncio
async def test_mock_paper_fetch_returns_paper():
    adapter = MockPaperSearch()
    paper = await adapter.fetch("paper123")
    assert paper.paper_id == "paper123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_mock.py -v`
Expected: FAIL — cannot import `MockWebSearch`

- [ ] **Step 3: Implement mock adapters**

```python
# src/decisionlab/adapters/__init__.py
```

```python
# src/decisionlab/adapters/mock.py
from __future__ import annotations

from decisionlab.domain.models import PaperResult, SearchResult


class MockWebSearch:
    def __init__(self, results: list[SearchResult] | None = None):
        self._results = results or [
            SearchResult(
                title="Homeostatic regulation of food intake",
                url="https://example.com/homeostatic",
                snippet="Homeostatic model based on hormonal signals (ghrelin, leptin).",
            ),
            SearchResult(
                title="Hedonic aspects of feeding",
                url="https://example.com/hedonic",
                snippet="Reward-based model using reinforcement learning.",
            ),
            SearchResult(
                title="Prospect theory and food choice",
                url="https://example.com/prospect",
                snippet="Decision-making under uncertainty applied to food.",
            ),
        ]

    async def search(self, query: str) -> list[SearchResult]:
        return self._results


class MockPaperSearch:
    def __init__(self, results: list[PaperResult] | None = None):
        self._results = results or [
            PaperResult(
                paper_id="jacquier2014",
                title="A predictive model of body weight dynamics",
                abstract="We present a model of food intake regulation...",
                authors=["Jacquier", "Alvarez"],
                year=2014,
            ),
        ]

    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        return self._results[:limit]

    async def fetch(self, paper_id: str) -> PaperResult:
        for p in self._results:
            if p.paper_id == paper_id:
                return p
        return PaperResult(
            paper_id=paper_id,
            title=f"Paper {paper_id}",
            abstract="Mock abstract.",
            authors=["Mock Author"],
            year=2020,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_mock.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/adapters/ phase1-pablo/tests/adapters/
git commit -m "feat[phase1]: add mock adapters for WebSearchPort and PaperSearchPort"
```

---

## Chunk 2: Runtime — Dispatcher and Agentic Loop

### Task 5: Parallel dispatcher

**Files:**
- Create: `src/decisionlab/runtime/__init__.py`
- Create: `src/decisionlab/runtime/dispatcher.py`
- Create: `tests/runtime/__init__.py`
- Create: `tests/runtime/test_dispatcher.py`

- [ ] **Step 1: Write tests for dispatcher**

```python
# tests/runtime/test_dispatcher.py
import pytest

from decisionlab.runtime.dispatcher import dispatch_tools


class FakeToolCall:
    def __init__(self, id: str, name: str, input: dict):
        self.id = id
        self.name = name
        self.input = input


@pytest.mark.asyncio
async def test_dispatch_single_tool():
    async def greet(input: dict) -> str:
        return f"hello {input['name']}"

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

    async def slow_tool(input: dict) -> str:
        order.append(f"start_{input['id']}")
        await asyncio.sleep(0.05)
        order.append(f"end_{input['id']}")
        return f"done_{input['id']}"

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
    async def good_tool(input: dict) -> str:
        return "ok"

    async def bad_tool(input: dict) -> str:
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/runtime/test_dispatcher.py -v`
Expected: FAIL — cannot import `dispatch_tools`

- [ ] **Step 3: Implement dispatcher**

```python
# src/decisionlab/runtime/__init__.py
```

```python
# src/decisionlab/runtime/dispatcher.py
from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable


ToolFunction = Callable[[dict], Awaitable[str]]
Registry = dict[str, ToolFunction]


async def dispatch_tools(tool_calls: list, registry: Registry) -> list[dict[str, Any]]:
    async def run_one(call) -> dict[str, Any]:
        try:
            result = await registry[call.name](call.input)
            return {"type": "tool_result", "tool_use_id": call.id, "content": result}
        except Exception as e:
            return {"type": "tool_result", "tool_use_id": call.id, "content": str(e), "is_error": True}

    return list(await asyncio.gather(*(run_one(call) for call in tool_calls)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/runtime/test_dispatcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/runtime/ phase1-pablo/tests/runtime/
git commit -m "feat[phase1]: add parallel tool dispatcher with error isolation"
```

---

### Task 6: Agentic loop

**Files:**
- Create: `src/decisionlab/runtime/loop.py`
- Create: `tests/runtime/test_loop.py`

- [ ] **Step 1: Write tests for the agentic loop**

We mock the Anthropic async client. The loop should: call `messages.create`, detect tool_use, dispatch, feed results back, and stop on `end_turn`.

```python
# tests/runtime/test_loop.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.runtime.loop import run_agent_loop


def _make_tool_use_block(id: str, name: str, input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input
    return block


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_response(stop_reason: str, content: list):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    return resp


@pytest.mark.asyncio
async def test_loop_returns_immediately_on_end_turn():
    client = AsyncMock()
    client.messages.create.return_value = _make_response(
        "end_turn", [_make_text_block("done")]
    )

    response = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
    )

    assert response.stop_reason == "end_turn"
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_loop_dispatches_tool_and_continues():
    tool_response = _make_response(
        "tool_use", [_make_tool_use_block("t1", "echo", {"msg": "hello"})]
    )
    final_response = _make_response("end_turn", [_make_text_block("result")])

    client = AsyncMock()
    client.messages.create.side_effect = [tool_response, final_response]

    async def echo(input: dict) -> str:
        return input["msg"]

    response = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}],
        registry={"echo": echo},
    )

    assert response.stop_reason == "end_turn"
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_loop_respects_max_iterations():
    tool_response = _make_response(
        "tool_use", [_make_tool_use_block("t1", "echo", {"msg": "x"})]
    )

    client = AsyncMock()
    client.messages.create.return_value = tool_response

    async def echo(input: dict) -> str:
        return "x"

    with pytest.raises(RuntimeError, match="Max iterations"):
        await run_agent_loop(
            client=client, model="claude-sonnet-4-6", system="sys",
            tools=[], messages=[{"role": "user", "content": "hi"}],
            registry={"echo": echo}, max_iterations=3,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/runtime/test_loop.py -v`
Expected: FAIL — cannot import `run_agent_loop`

- [ ] **Step 3: Implement agentic loop**

```python
# src/decisionlab/runtime/loop.py
from __future__ import annotations

from typing import Any

from decisionlab.runtime.dispatcher import Registry, dispatch_tools


async def run_agent_loop(
    *,
    client,
    model: str,
    system: str,
    tools: list[dict],
    messages: list[dict[str, Any]],
    registry: Registry,
    max_tokens: int = 4096,
    max_iterations: int = 20,
):
    messages = list(messages)

    for _ in range(max_iterations):
        response = await client.messages.create(
            model=model,
            system=system,
            tools=tools,
            messages=messages,
            max_tokens=max_tokens,
        )

        if response.stop_reason == "end_turn":
            return response

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})

        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Max iterations ({max_iterations}) reached")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/runtime/test_loop.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/runtime/loop.py phase1-pablo/tests/runtime/test_loop.py
git commit -m "feat[phase1]: add generic async agentic loop with max iteration guard"
```

---

## Chunk 3: Tools — Search and Agent Spawning

### Task 7: Search tool definitions

**Files:**
- Create: `src/decisionlab/tools/search.py`
- Create: `tests/tools/test_search.py`

- [ ] **Step 1: Write tests for search tools**

```python
# tests/tools/test_search.py
import pytest

from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.tools.search import (
    WEB_SEARCH_SCHEMA,
    SEARCH_PAPERS_SCHEMA,
    FETCH_PAPER_SCHEMA,
    create_web_search,
    create_search_papers,
    create_fetch_paper,
)


def test_web_search_schema_has_required_fields():
    assert WEB_SEARCH_SCHEMA["name"] == "web_search"
    assert "query" in WEB_SEARCH_SCHEMA["input_schema"]["properties"]


def test_search_papers_schema_has_required_fields():
    assert SEARCH_PAPERS_SCHEMA["name"] == "search_papers"
    assert "query" in SEARCH_PAPERS_SCHEMA["input_schema"]["properties"]
    assert "limit" in SEARCH_PAPERS_SCHEMA["input_schema"]["properties"]


def test_fetch_paper_schema_has_required_fields():
    assert FETCH_PAPER_SCHEMA["name"] == "fetch_paper"
    assert "paper_id" in FETCH_PAPER_SCHEMA["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_web_search_function_delegates_to_port():
    adapter = MockWebSearch()
    fn = create_web_search(adapter)
    result = await fn({"query": "homeostatic regulation"})
    assert "Homeostatic" in result


@pytest.mark.asyncio
async def test_search_papers_function_delegates_to_port():
    adapter = MockPaperSearch()
    fn = create_search_papers(adapter)
    result = await fn({"query": "food intake", "limit": 5})
    assert "predictive model" in result.lower()


@pytest.mark.asyncio
async def test_fetch_paper_function_delegates_to_port():
    adapter = MockPaperSearch()
    fn = create_fetch_paper(adapter)
    result = await fn({"paper_id": "jacquier2014"})
    assert "jacquier2014" in result.lower() or "Jacquier" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/tools/test_search.py -v`
Expected: FAIL — cannot import from `decisionlab.tools.search`

- [ ] **Step 3: Implement search tools**

```python
# src/decisionlab/tools/search.py
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from decisionlab.domain.ports import PaperSearchPort, WebSearchPort

WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "web_search",
    "description": "Search the web for information about decision-making paradigms. Returns a list of results with title, URL, and snippet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
}

SEARCH_PAPERS_SCHEMA: dict[str, Any] = {
    "name": "search_papers",
    "description": "Search for academic papers on a topic. Returns papers with title, abstract, authors, and year.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for academic papers"},
            "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
        },
        "required": ["query"],
    },
}

FETCH_PAPER_SCHEMA: dict[str, Any] = {
    "name": "fetch_paper",
    "description": "Fetch full details of a specific paper by its ID. Returns title, abstract, authors, and year.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Paper ID from search_papers results"},
        },
        "required": ["paper_id"],
    },
}


def create_web_search(adapter: WebSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def web_search(input: dict) -> str:
        results = await adapter.search(input["query"])
        return json.dumps(
            [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
            indent=2,
        )
    return web_search


def create_search_papers(adapter: PaperSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def search_papers(input: dict) -> str:
        results = await adapter.search(input["query"], input.get("limit", 10))
        return json.dumps(
            [{"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract,
              "authors": p.authors, "year": p.year} for p in results],
            indent=2,
        )
    return search_papers


def create_fetch_paper(adapter: PaperSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def fetch_paper(input: dict) -> str:
        paper = await adapter.fetch(input["paper_id"])
        return json.dumps(
            {"paper_id": paper.paper_id, "title": paper.title, "abstract": paper.abstract,
             "authors": paper.authors, "year": paper.year},
            indent=2,
        )
    return fetch_paper
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/tools/test_search.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/tools/search.py phase1-pablo/tests/tools/test_search.py
git commit -m "feat[phase1]: add search tool definitions (web_search, search_papers, fetch_paper)"
```

---

### Task 8: Agent tool (launch_deep_research)

**Files:**
- Create: `src/decisionlab/tools/agents.py`
- Create: `tests/tools/test_agents.py`

- [ ] **Step 1: Write tests for the agent tool**

```python
# tests/tools/test_agents.py
import pytest
from unittest.mock import AsyncMock

from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research


def test_schema_has_required_fields():
    assert LAUNCH_DEEP_RESEARCH_SCHEMA["name"] == "launch_deep_research"
    assert "paradigm" in LAUNCH_DEEP_RESEARCH_SCHEMA["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_launch_deep_research_calls_sub_agent():
    sub_agent_factory = AsyncMock(return_value="# Homeostatic — Deep research\n\nContent here.")
    fn = create_launch_deep_research(sub_agent_factory)
    result = await fn({"paradigm": "Homeostatic regulation of food intake"})
    assert "Homeostatic" in result
    sub_agent_factory.assert_called_once_with("Homeostatic regulation of food intake")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/tools/test_agents.py -v`
Expected: FAIL — cannot import from `decisionlab.tools.agents`

- [ ] **Step 3: Implement agent tool**

```python
# src/decisionlab/tools/agents.py
from __future__ import annotations

from typing import Any, Awaitable, Callable

LAUNCH_DEEP_RESEARCH_SCHEMA: dict[str, Any] = {
    "name": "launch_deep_research",
    "description": "Launch a sub-agent to deeply research a specific decision-making paradigm. The sub-agent will search for papers, read abstracts, and produce a detailed markdown report. Use this for each paradigm you identify.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paradigm": {
                "type": "string",
                "description": "Name and brief description of the paradigm to research in depth",
            },
        },
        "required": ["paradigm"],
    },
}


SubAgentFactory = Callable[[str], Awaitable[str]]


def create_launch_deep_research(factory: SubAgentFactory) -> Callable[[dict], Awaitable[str]]:
    async def launch_deep_research(input: dict) -> str:
        return await factory(input["paradigm"])
    return launch_deep_research
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/tools/test_agents.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/tools/agents.py phase1-pablo/tests/tools/test_agents.py
git commit -m "feat[phase1]: add launch_deep_research tool definition"
```

---

## Chunk 4: Agents — Deep Researcher and Researcher

### Task 9: Deep Researcher agent

**Files:**
- Create: `src/decisionlab/agents/deep_researcher.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_deep_researcher.py`

- [ ] **Step 1: Write tests for Deep Researcher**

```python
# tests/agents/test_deep_researcher.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.agents.deep_researcher import DeepResearcher, DEEP_RESEARCHER_SYSTEM_PROMPT
from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch


def test_system_prompt_exists():
    assert "deep research specialist" in DEEP_RESEARCHER_SYSTEM_PROMPT.lower()


def test_deep_researcher_has_correct_tools():
    client = AsyncMock()
    dr = DeepResearcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    tool_names = [t["name"] for t in dr.tools]
    assert "web_search" in tool_names
    assert "search_papers" in tool_names
    assert "fetch_paper" in tool_names
    assert "launch_deep_research" not in tool_names


@pytest.mark.asyncio
async def test_deep_researcher_run_returns_markdown():
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Homeostatic — Deep research\n\n## Foundations\nContent."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = AsyncMock()
    client.messages.create.return_value = response

    dr = DeepResearcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    result = await dr.run("Homeostatic regulation")

    assert "Homeostatic" in result
    assert client.messages.create.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/agents/test_deep_researcher.py -v`
Expected: FAIL — cannot import `DeepResearcher`

- [ ] **Step 3: Implement Deep Researcher**

```python
# src/decisionlab/agents/deep_researcher.py
from __future__ import annotations

from decisionlab.domain.ports import PaperSearchPort, WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.search import (
    FETCH_PAPER_SCHEMA,
    SEARCH_PAPERS_SCHEMA,
    WEB_SEARCH_SCHEMA,
    create_fetch_paper,
    create_search_papers,
    create_web_search,
)

DEEP_RESEARCHER_SYSTEM_PROMPT = """\
You are a deep research specialist. Your job: given a single decision-making paradigm, produce a thorough scientific report by searching for papers, reading abstracts, and synthesizing findings.

## Process

1. SEARCH for papers and content specific to this paradigm. Use multiple queries: the paradigm name, key authors, key mechanisms, mathematical formulations.

2. FETCH key papers to read their abstracts and metadata. Prioritize foundational papers and recent reviews.

3. SYNTHESIZE findings into a structured report.

## Rules

- DEPTH over breadth. Exhaust this paradigm before finishing.
- Every claim must trace to a specific paper or source from your searches.
- Never fabricate references — only cite papers you found via search tools.
- If you cannot find enough information, say so explicitly rather than inventing content.

## Output format

# {Paradigm name} — Deep research

## Foundations
{What is this paradigm? Origin, key researchers, theoretical basis.}

## Postulates
P1. {Specific, falsifiable statement} ({Author, Year})
P2. ...

## Assumptions
- {Each assumption the model makes}

## Predictions
- {Observable behaviors the model predicts}

## Identified variables
| Variable | Role | Behavior |
|----------|------|----------|
| ... | ... | ... |

## Mathematical formulation (if applicable)
{Equations, ODEs, update rules — as described in the literature}

## References
- {Author (Year)} - {Title} - DOI: {if found}
"""


class DeepResearcher:
    def __init__(self, *, client, search: WebSearchPort, papers: PaperSearchPort):
        self.client = client
        self.tools = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA, FETCH_PAPER_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "search_papers": create_search_papers(papers),
            "fetch_paper": create_fetch_paper(papers),
        }

    async def run(self, paradigm: str) -> str:
        messages = [{"role": "user", "content": f"Research this paradigm in depth: {paradigm}"}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=DEEP_RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        return "\n".join(text_blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/agents/test_deep_researcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/agents/deep_researcher.py phase1-pablo/tests/agents/
git commit -m "feat[phase1]: add DeepResearcher agent with system prompt and tool wiring"
```

---

### Task 10: Researcher agent

**Files:**
- Modify: `src/decisionlab/agents/researcher.py`
- Create: `tests/agents/test_researcher.py`

- [ ] **Step 1: Write tests for Researcher**

```python
# tests/agents/test_researcher.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.agents.researcher import Researcher, RESEARCHER_SYSTEM_PROMPT
from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.domain.models import ResearchReport


def test_system_prompt_exists():
    assert "breadth-first" in RESEARCHER_SYSTEM_PROMPT.lower()


def test_researcher_has_correct_tools():
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    tool_names = [t["name"] for t in r.tools]
    assert "web_search" in tool_names
    assert "search_papers" in tool_names
    assert "launch_deep_research" in tool_names
    assert "fetch_paper" not in tool_names


@pytest.mark.asyncio
async def test_researcher_run_returns_research_report():
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Decision-making paradigms: food\n\n## 1. Homeostatic\nDesc\n**Key authors**: X\n**Key concepts**: Y"

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = AsyncMock()
    client.messages.create.return_value = response

    r = Researcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    report = await r.run("food intake behavior")

    assert isinstance(report, ResearchReport)
    assert "food" in report.summary.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/agents/test_researcher.py -v`
Expected: FAIL — cannot import `Researcher` with the new signature

- [ ] **Step 3: Implement Researcher**

```python
# src/decisionlab/agents/researcher.py
"""Researcher agent — discovers and investigates decision-making paradigms."""

from __future__ import annotations

from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.domain.models import ResearchReport
from decisionlab.domain.ports import PaperSearchPort, WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.tools.agents import LAUNCH_DEEP_RESEARCH_SCHEMA, create_launch_deep_research
from decisionlab.tools.search import (
    SEARCH_PAPERS_SCHEMA,
    WEB_SEARCH_SCHEMA,
    create_search_papers,
    create_web_search,
)

RESEARCHER_SYSTEM_PROMPT = """\
You are a decision-making paradigm researcher. Your job: given a decision-making problem, discover ALL relevant scientific paradigms through breadth-first search.

## Process

1. SEARCH BROADLY — Use web_search and search_papers with varied queries to discover paradigms. Cast a wide net: try synonyms, related fields, different theoretical frameworks.

2. IDENTIFY PARADIGMS — From search results, identify distinct decision-making paradigms. A paradigm is a coherent theoretical framework with its own assumptions, variables, and mechanisms (e.g., "homeostatic regulation", "Q-learning", "prospect theory").

3. LAUNCH DEEP RESEARCH — For each identified paradigm, call launch_deep_research with a clear description. Do NOT research paradigms yourself in depth — delegate.

4. EVALUATE COVERAGE — After receiving sub-agent results, assess:
   - Are there paradigm families not yet covered?
   - Did search results hint at paradigms not yet investigated?
   - Are the found paradigms sufficiently diverse?
   If coverage is insufficient, search more and launch additional sub-agents.

5. PRODUCE SUMMARY — When satisfied with coverage, produce a final summary listing all discovered paradigms with: name, one-line description, key authors, and key concepts.

## Rules

- BREADTH over depth. You identify, sub-agents investigate.
- Minimum 3 varied search queries before concluding no more paradigms exist.
- Always cite real authors and papers from search results. Never fabricate references.
- If search results are poor, reformulate queries — do not give up after one attempt.

## Output format

Return your final summary as structured text:

# Decision-making paradigms: {problem}

## 1. {Paradigm name}
{One-line description}
**Key authors**: {from search results}
**Key concepts**: {list}

## 2. {Paradigm name}
...
"""


class Researcher:
    def __init__(self, *, client, search: WebSearchPort, papers: PaperSearchPort):
        self.client = client
        self.search = search
        self.papers = papers

        self._deep_reports: dict[str, str] = {}

        async def _run_deep_research(paradigm: str) -> str:
            dr = DeepResearcher(client=client, search=search, papers=papers)
            report = await dr.run(paradigm)
            self._deep_reports[paradigm] = report
            return report

        self.tools = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA, LAUNCH_DEEP_RESEARCH_SCHEMA]
        self.registry = {
            "web_search": create_web_search(search),
            "search_papers": create_search_papers(papers),
            "launch_deep_research": create_launch_deep_research(_run_deep_research),
        }

    async def run(self, problem: str) -> ResearchReport:
        self._deep_reports.clear()

        messages = [{"role": "user", "content": problem}]

        response = await run_agent_loop(
            client=self.client,
            model="claude-sonnet-4-6",
            system=RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
        )

        summary = "\n".join(b.text for b in response.content if b.type == "text")

        return ResearchReport(
            paradigms=[],
            summary=summary,
            deep_reports=dict(self._deep_reports),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/agents/test_researcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/agents/researcher.py phase1-pablo/tests/agents/test_researcher.py
git commit -m "feat[phase1]: add Researcher agent with breadth-first search and sub-agent delegation"
```

---

## Chunk 5: Real Adapters and Cleanup

### Task 11: DuckDuckGo adapter

**Files:**
- Create: `src/decisionlab/adapters/duckduckgo.py`
- Create: `tests/adapters/test_duckduckgo.py`

- [ ] **Step 1: Write tests**

```python
# tests/adapters/test_duckduckgo.py
import pytest

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.domain.ports import WebSearchPort


def test_satisfies_port():
    assert isinstance(DuckDuckGoAdapter(), WebSearchPort)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_search_returns_results():
    adapter = DuckDuckGoAdapter()
    results = await adapter.search("homeostatic regulation food intake")
    assert len(results) > 0
    assert results[0].title
    assert results[0].url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_duckduckgo.py -v -k "not integration"`
Expected: FAIL — cannot import `DuckDuckGoAdapter`

- [ ] **Step 3: Implement DuckDuckGo adapter**

```python
# src/decisionlab/adapters/duckduckgo.py
from __future__ import annotations

import asyncio
from functools import partial

from duckduckgo_search import DDGS

from decisionlab.domain.models import SearchResult


class DuckDuckGoAdapter:
    def __init__(self, max_results: int = 10):
        self._max_results = max_results

    async def search(self, query: str) -> list[SearchResult]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, partial(self._sync_search, query))
        return results

    def _sync_search(self, query: str) -> list[SearchResult]:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=self._max_results))
        return [
            SearchResult(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", ""))
            for r in raw
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_duckduckgo.py -v -k "not integration"`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/adapters/duckduckgo.py phase1-pablo/tests/adapters/test_duckduckgo.py
git commit -m "feat[phase1]: add DuckDuckGo adapter for WebSearchPort"
```

---

### Task 12: Semantic Scholar adapter

**Files:**
- Create: `src/decisionlab/adapters/semantic_scholar.py`
- Create: `tests/adapters/test_semantic_scholar.py`

- [ ] **Step 1: Write tests**

```python
# tests/adapters/test_semantic_scholar.py
import pytest

from decisionlab.adapters.semantic_scholar import SemanticScholarAdapter
from decisionlab.domain.ports import PaperSearchPort


def test_satisfies_port():
    assert isinstance(SemanticScholarAdapter(), PaperSearchPort)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_search_returns_papers():
    adapter = SemanticScholarAdapter()
    results = await adapter.search("homeostatic food intake model", limit=3)
    assert len(results) > 0
    assert results[0].title


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_fetch_returns_paper():
    adapter = SemanticScholarAdapter()
    results = await adapter.search("Jacquier predictive model body weight", limit=1)
    if results:
        paper = await adapter.fetch(results[0].paper_id)
        assert paper.title
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_semantic_scholar.py -v -k "not integration"`
Expected: FAIL — cannot import `SemanticScholarAdapter`

- [ ] **Step 3: Implement Semantic Scholar adapter**

```python
# src/decisionlab/adapters/semantic_scholar.py
from __future__ import annotations

import asyncio
from functools import partial
from urllib.request import urlopen, Request
from urllib.parse import quote
import json

from decisionlab.domain.models import PaperResult

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year"


class SemanticScholarAdapter:
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._sync_search, query, limit))

    async def fetch(self, paper_id: str) -> PaperResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._sync_fetch, paper_id))

    def _sync_search(self, query: str, limit: int) -> list[PaperResult]:
        url = f"{_BASE_URL}/paper/search?query={quote(query)}&limit={limit}&fields={_FIELDS}"
        data = self._get_json(url)
        return [self._to_paper(p) for p in data.get("data", []) if p.get("title")]

    def _sync_fetch(self, paper_id: str) -> PaperResult:
        url = f"{_BASE_URL}/paper/{quote(paper_id)}?fields={_FIELDS}"
        data = self._get_json(url)
        return self._to_paper(data)

    def _get_json(self, url: str) -> dict:
        req = Request(url, headers={"User-Agent": "decisionlab/0.1"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _to_paper(self, raw: dict) -> PaperResult:
        return PaperResult(
            paper_id=raw.get("paperId", ""),
            title=raw.get("title", ""),
            abstract=raw.get("abstract", "") or "",
            authors=[a.get("name", "") for a in raw.get("authors", [])],
            year=raw.get("year", 0) or 0,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase1-pablo && uv run pytest tests/adapters/test_semantic_scholar.py -v -k "not integration"`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add phase1-pablo/src/decisionlab/adapters/semantic_scholar.py phase1-pablo/tests/adapters/test_semantic_scholar.py
git commit -m "feat[phase1]: add Semantic Scholar adapter for PaperSearchPort"
```

---

### Task 13: Cleanup and update smoke test

**Files:**
- Remove: `src/decisionlab/tools/web_search.py`
- Remove: `src/decisionlab/tools/semantic_scholar.py`
- Remove: `src/decisionlab/tools/file_io.py`
- Remove: `src/decisionlab/tools/code_runner.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Remove old empty tool files**

```bash
cd phase1-pablo
rm src/decisionlab/tools/web_search.py
rm src/decisionlab/tools/semantic_scholar.py
rm src/decisionlab/tools/file_io.py
rm src/decisionlab/tools/code_runner.py
```

- [ ] **Step 2: Update smoke test**

```python
# tests/test_smoke.py
def test_package_imports():
    import decisionlab
    from decisionlab import cli
    from decisionlab.agents import researcher
    from decisionlab.agents import deep_researcher
    from decisionlab.domain import models, ports
    from decisionlab.adapters import mock
    from decisionlab.runtime import dispatcher, loop
    from decisionlab.tools import search, agents


def test_cli_app_exists():
    from decisionlab.cli import app
    assert app is not None


def test_model_protocol_imports():
    from decisionlab.models.protocol import DecisionModel, Action, Perception


def test_denis_example_imports():
    from denis.homeostatic import HomeostaticModel
    from denis.hedonic import HedonicModel
    from denis.integrated import IntegratedModel, IntegrationMode
```

- [ ] **Step 3: Run all tests**

Run: `cd phase1-pablo && uv run pytest -v -k "not integration"`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add -A phase1-pablo/src/decisionlab/tools/ phase1-pablo/tests/test_smoke.py
git commit -m "fix[phase1]: remove old tool stubs, update smoke test for new structure"
```

---

### Task 14: Add pytest config for integration marker

**Files:**
- Modify: `phase1-pablo/pyproject.toml`

- [ ] **Step 1: Add marker config**

Add to `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "examples", "../phase2-juan"]
asyncio_mode = "auto"
markers = [
    "integration: tests that require internet access (deselect with -k 'not integration')",
]
```

- [ ] **Step 2: Run full suite**

Run: `cd phase1-pablo && uv run pytest -v -k "not integration"`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add phase1-pablo/pyproject.toml
git commit -m "fix[phase1]: add pytest asyncio_mode and integration marker"
```
