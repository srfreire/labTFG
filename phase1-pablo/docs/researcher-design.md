# Researcher Agent — Design Spec

## Decisions

| Decision | Value | Reason |
|----------|-------|--------|
| SDK | `anthropic` (Claude API) | Standalone app, TDD, full control |
| Loop | Manual async agentic loop | Parallel tool dispatch via `asyncio.gather` |
| Model | Claude Sonnet (`claude-sonnet-4-6`) | Breadth search doesn't need Opus |
| Web search | DuckDuckGo (`duckduckgo-search`) | Free, no API key |
| Paper search | Semantic Scholar API | Free (100 req/s with key, no key for basic) |
| Architecture | Clean architecture (ports/adapters) | TDD, swappable implementations |
| Tool implementations | Real + mock | Test flow without internet |

## Architecture

```
src/decisionlab/
├── domain/
│   ├── ports.py              # Protocol classes (interfaces)
│   └── models.py             # Dataclasses: SearchResult, PaperResult, Paradigm, ResearchReport
├── adapters/
│   ├── duckduckgo.py         # WebSearchPort → DuckDuckGo
│   ├── semantic_scholar.py   # PaperSearchPort → Semantic Scholar API
│   └── mock.py               # Mock implementations for tests
├── runtime/
│   ├── loop.py               # Generic async agentic loop
│   └── dispatcher.py         # Parallel tool dispatch (asyncio.gather)
├── tools/
│   ├── search.py             # web_search, search_papers, fetch_paper (JSON schemas)
│   └── agents.py             # launch_deep_research
└── agents/
    ├── researcher.py         # Researcher agent (breadth)
    └── deep_researcher.py    # Sub-agent (depth)
```

### Layers

- **domain/ports.py** — `Protocol` classes defining interfaces. Tools and agents depend on ports, never on adapters directly.
- **domain/models.py** — Pure dataclasses (`SearchResult`, `PaperResult`, `Paradigm`, `ResearchReport`). No logic, no dependencies.
- **adapters/** — Concrete implementations of ports. Real (HTTP calls) and mock (canned data).
- **runtime/** — Generic agentic loop + parallel dispatcher. Agent-agnostic, reusable.
- **tools/** — Tool definitions (JSON schemas) + thin async functions that delegate to ports. Shared between agents.
- **agents/** — Agent classes. Receive adapters via constructor injection. Use runtime loop + tools.

### Dependency flow

```
agents → tools → domain/ports ← adapters
agents → runtime
agents → domain/models
```

Adapters are never imported by tools or agents — injected at construction time.

## Tools

### Researcher tools

| Tool | Port | Description |
|------|------|-------------|
| `web_search(query)` | `WebSearchPort` | Broad web search |
| `search_papers(query, limit)` | `PaperSearchPort` | Search academic papers |
| `launch_deep_research(paradigm)` | — (spawns sub-agent) | Launch depth sub-agent |

### Sub-agent tools

| Tool | Port | Description |
|------|------|-------------|
| `web_search(query)` | `WebSearchPort` | Focused web search |
| `search_papers(query, limit)` | `PaperSearchPort` | Search specific papers |
| `fetch_paper(paper_id)` | `PaperSearchPort` | Get abstract + metadata |

`web_search` and `search_papers` are shared (same definitions, same ports).

## Runtime

### Agentic loop (`runtime/loop.py`)

```python
async def run_agent_loop(client, model, system, tools, messages, registry) -> Message:
    while True:
        response = await client.messages.create(
            model=model, system=system, tools=tools, messages=messages, max_tokens=4096
        )
        if response.stop_reason == "end_turn":
            return response

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": response.content})
        results = await dispatch_tools(tool_calls, registry)
        messages.append({"role": "user", "content": results})
```

### Parallel dispatcher (`runtime/dispatcher.py`)

```python
async def dispatch_tools(tool_calls, registry) -> list[dict]:
    async def run_one(call):
        try:
            result = await registry[call.name](call.input)
            return {"type": "tool_result", "tool_use_id": call.id, "content": result}
        except Exception as e:
            return {"type": "tool_result", "tool_use_id": call.id, "content": str(e), "is_error": True}

    return await asyncio.gather(*(run_one(call) for call in tool_calls))
```

All tool calls from the same turn run in parallel. Errors are isolated — one failure doesn't kill the others.

## Agent wiring

```python
class Researcher:
    def __init__(self, client: AsyncAnthropic, search: WebSearchPort, papers: PaperSearchPort):
        self.client = client
        self.tools = [WEB_SEARCH_SCHEMA, SEARCH_PAPERS_SCHEMA, LAUNCH_DEEP_RESEARCH_SCHEMA]
        self.registry = {
            "web_search": lambda input: search.search(input["query"]),
            "search_papers": lambda input: papers.search(input["query"], input.get("limit", 10)),
            "launch_deep_research": self._launch_deep,
        }

    async def run(self, problem: str) -> ResearchReport: ...
    async def _launch_deep(self, input) -> str:
        sub = DeepResearcher(self.client, ...)  # same adapters
        return await sub.run(input["paradigm"])
```

### Production

```python
researcher = Researcher(AsyncAnthropic(), DuckDuckGoAdapter(), SemanticScholarAdapter())
report = await researcher.run("food intake behavior")
```

### Tests

```python
researcher = Researcher(mock_client, MockSearchAdapter(), MockPaperAdapter())
report = await researcher.run("food intake behavior")
```

## System prompts

### Researcher

```
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
```

### Deep Researcher (sub-agent)

```
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
```

## Output

The Researcher produces a `ResearchReport`:

```
ResearchReport
├── paradigms: list[Paradigm]         # Identified paradigms with metadata
├── summary: str                      # paradigms.md content
└── deep_reports: dict[str, str]      # paradigm_id → deep research markdown
```

The Router/CLI persists this to disk:

```
outputs/<run_id>/01_researcher/
├── paradigms.md
├── homeostatic.md
├── hedonic.md
└── prospect_theory.md
```

The Researcher does NOT write files — it returns data. Persistence is the caller's responsibility.
