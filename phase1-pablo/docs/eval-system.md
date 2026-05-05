# Eval system

A non-interactive harness for driving the decisionlab pipeline as part of
tests, evals, and bulk knowledge-graph population. The interactive flow
(`decisionlab run`) is built for humans curating one paradigm at a time;
this is built for repeatable, scriptable runs across many topics.

## Why this exists

Three needs that the interactive pipeline can't serve cleanly:

1. **Bulk KG population.** Fire ten topics through the Researcher to
   watch the knowledge graph grow, dedup, and cross-link. Each topic
   needs to commit its memory writes without waiting for a human to
   click "approve".
2. **Regression evals.** "Did paradigm `prospect-theory` still surface
   for the risk-decision topic?" "Did the generated `q-learning_model.py`
   still import and return an action?" These are checks we want to run
   on a schedule, in CI, with stable exit codes.
3. **Configuration sweeps.** Swap the Researcher prompt or the embedding
   provider, run the same topic suite, diff the reports.

The eval system gives all three a single CLI surface
(`decisionlab eval ...`) backed by a small importable library
(`decisionlab.eval`).

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ CLI layer                                                        │
│ decisionlab eval run | topics | pipeline                         │
│ decisionlab kg stats | reset | snapshot | restore | query        │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│ Library layer (decisionlab.eval)                                 │
│ ┌────────────┐  ┌─────────────┐  ┌─────────┐  ┌──────────┐       │
│ │ runner.py  │  │ suite.py    │  │ cost.py │  │ report.py│       │
│ │ (1 topic)  │  │ (N topics)  │  │ (USD)   │  │ md+json  │       │
│ └─────┬──────┘  └──────┬──────┘  └─────────┘  └──────────┘       │
│       │                │                                         │
│       │      ┌─────────▼────────┐  ┌────────────────────┐        │
│       │      │ assertions.py    │  │ kgadmin.py         │        │
│       │      │ (predicate reg.) │  │ (stats/reset/snap) │        │
│       │      └──────────────────┘  └─────────┬──────────┘        │
│       │                                      │                   │
└───────┼──────────────────────────────────────┼───────────────────┘
        │                                      │
┌───────▼─────────────────┐         ┌──────────▼──────────────────┐
│ FeedbackPort            │         │ shared.kg                   │
│  └ AutoApproveFeedback  │         │  └ Neo4j async driver       │
└─────────────────────────┘         └─────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────┐
│ Existing pipeline                                               │
│ Router → Researcher → MemoryAgent → Formalizer → … → Builder    │
└─────────────────────────────────────────────────────────────────┘
```

Three insights underpin the design:

- **`MemoryAgent` runs before the human review** (`MEMORY_RESEARCH`
  comes between `RESEARCH` and `REVIEW_RESEARCH`), so KG writes happen
  even if the review never runs. The eval harness exploits this by
  short-circuiting the review with an auto-approve adapter.
- **`Router` is reusable.** Rather than reimplement stage transitions,
  the eval harness constructs a real `Router` with a different
  `FeedbackPort`. Every stage dependency, S3 path, and persistence
  detail comes for free.
- **Assertions split into two families** — those that read the
  `PipelineRunResult` (what the pipeline produced) and those that read
  the live KG (what the memory pipeline wrote). Both go through one
  registry so suite YAML treats them uniformly.

## Component reference

### `decisionlab.feedback_port` — the abstraction layer

Three adapters behind a single `FeedbackPort` protocol with five
methods (`review_research`, `review_formalize`, `get_env_spec`,
`review_reason`, `review_build`):

| Adapter | When used | What it does |
|---|---|---|
| `CLIFeedback` | `decisionlab run` | Wraps the existing `decisionlab.feedback` questionary functions. |
| `WebFeedback(emit)` | server WS pipeline | Wraps `decisionlab.web_feedback`, captures the `emit` callback. |
| `AutoApproveFeedback(env_spec_path=…)` | eval runs | Approves every discovered slug, no rejections, no reruns. Returns the configured env_spec when asked. |

`Router.__init__` now takes `feedback: FeedbackPort` (defaults to
`CLIFeedback()`). The previous `_web_mode` branching is gone — the
router has zero knowledge of who's answering its prompts.

### `decisionlab.eval.runner` — one topic

```python
async def run_pipeline(
    topic: str,
    *,
    stages: Iterable[Stage] = (Stage.RESEARCH,),
    env_spec_path: Path | None = None,
    project_root: Path,
    client: AsyncAnthropic,
    search: WebSearchPort,
    reports_root: Path = Path("evals/runs"),
    run_id: str | None = None,
    reset_usage: bool = True,
) -> PipelineRunResult
```

What it does:

1. Validates `stages` is a contiguous prefix of
   `[RESEARCH, FORMALIZE, REASON, BUILD]`. Asking for `[RESEARCH,
   REASON]` silently fills in `FORMALIZE` (logged) — explicit holes
   are nonsensical because every stage needs its predecessor's
   artifacts.
2. Inserts the `Run` row in Postgres so the Router's mid-pipeline
   updates aren't no-ops.
3. Builds a `Router` with `AutoApproveFeedback(env_spec_path=...)` and
   `stop_after=stages[-1]`, then awaits `router.run()`.
4. Captures per-stage `MemoryAgent` payloads from the in-memory mirror
   (`router.memory_results`), the global usage snapshot, and any failure.

Caller is responsible for `shared.init()` / `shared.shutdown()`. The
runner is cheap to call repeatedly inside one process.

### `decisionlab.eval.suite` — N topics

```python
spec = SuiteSpec.from_yaml(Path("evals/suites/smoke.yaml"))
result: SuiteResult = await run_suite(spec, client=..., search=...)
```

`SuiteSpec.from_yaml` parses the DSL (see "Suite YAML schema" below).
`run_suite`:

1. (optional) Wipes the KG via `kgadmin.reset(confirm=True)`.
2. Snapshots `kgadmin.stats()` for the "before" baseline.
3. Iterates topics. For each:
   - Calls `run_pipeline` (with budget watchdog if `max_usd_total` is
     set — see below).
   - Evaluates each assertion against the result.
   - If the watchdog fires, marks the suite `budget_exhausted=True`
     and skips the remaining topics.
4. Snapshots `kgadmin.stats()` for the "after" baseline.

#### Budget watchdog

When `budget.max_usd_total` is set, the runner spawns each topic as an
`asyncio.Task` and starts a sampling loop that calls
`cost.estimate_usd(usage_module.snapshot())` every 2 s. When the
estimate exceeds the cap, the task is cancelled mid-stage — the topic
appears in the report with `failed_at=<stage at cancel>` and the suite
ends. This gives "hard kill on cost ceiling" semantics without making
every agent budget-aware.

`cost.MODEL_RATES` is a public dict — mutate it at process start if
you're routing through OpenRouter or another markup provider.

### `decisionlab.eval.kgadmin` — graph operations

| Function | What it does |
|---|---|
| `await stats()` | `KGStats(total_nodes, total_relations, by_label, by_type)` — counts come from `MATCH (n) RETURN count(n)` etc. Active relations only (`valid_to IS NULL`). |
| `await reset(confirm=True)` | `MATCH (n) DETACH DELETE n`. Returns the deleted node count. `confirm=False` raises — destructive operations need explicit opt-in. |
| `await snapshot()` | Full JSON dump (nodes + every relation, including superseded). Use `snapshot_to_file(path)` to write straight to disk. |
| `await restore(snap)` | Wipes (`reset_first=True` default) then re-CREATEs nodes and relations. Element IDs change; for round-trip identity rather than cross-instance dedup. |
| `await query(cypher, params)` | Thin pass-through to `shared.kg.query`. |

Every function raises `RuntimeError` if `shared.kg is None`, so
infrastructure failures surface at the entry point rather than as
opaque Cypher errors deep in the call stack.

### `decisionlab.eval.assertions` — predicate registry

Each YAML expectation entry is a one-key dict like `{paradigm: rl}`. A
registry maps the key to an async predicate function. Adding one is
two lines:

```python
@register("my_check")
async def _my_check(ctx, args):
    return AssertionOutcome(name="my_check", passed=..., detail="...")
```

Built-in predicates:

| Name | Args | Family | Pass when |
|---|---|---|---|
| `succeeded` | `null` | result | `result.failed_at is None` |
| `paradigm` | slug | result | slug in `result.paradigms` |
| `has_formulation` | slug | result | slug in `result.formulations` |
| `min_paradigms` | int | result | `len(result.paradigms) ≥ n` |
| `min_nodes` | `{label, n}` | KG | Cypher count for `(:label)` ≥ n |
| `relation_exists` | `{from, type, to}` | KG | ≥ 1 active relation matches |
| `module_imports` | spec_id | result+disk | Generated `*_model.py` imports cleanly |
| `decide_returns_action` | `{spec_id, perception}` | result+disk | Loaded class's `decide(perception)` returns a string or `{kind|name: ...}` dict |

KG predicates are skipped (with a "skipped" outcome) when the suite
runs with `skip_kg_ops=True` — used by tests that don't have a live
Neo4j.

### `decisionlab.eval.report` — output

`render_markdown(result)` produces a human-readable summary with KG
growth deltas, per-topic memory writes, and an assertion table.
`render_json(result)` produces a machine-comparable dump suitable for
diffing across runs. `write_report(result, dir)` writes both.

## Suite YAML schema

```yaml
name: my-suite                                 # required
stages: [research, formalize, reason, build]   # default [research];
                                               # contiguous prefix
env_spec: evals/fixtures/env_spec_grid_10x10.json
                                               # required iff reason or build
                                               # is in stages
reset_kg_before: true                          # default false; wipe KG
                                               # before topic 1
project_root: evals/runs                       # default; per-suite isolation
reports_root: evals/runs                       # default; reports_dir parent

topics:
  - text: "free-form topic description"
    expect:                                    # optional
      research:                                # stage-keyed
        - paradigm: reinforcement-learning
        - min_paradigms: 3
      build:
        - module_imports: q-learning

budget:
  max_usd_total: 10.00                         # optional cap
```

A topic can also be a bare string when no expectations are needed:

```yaml
topics:
  - "first topic"
  - "second topic"
```

## CLI reference

### `decisionlab eval`

```text
decisionlab eval run <suite.yaml>
    --stages X,Y          override the suite's stages
    --no-reset            suppress reset_kg_before even if the suite enables it
    --report PATH         write report.md/json here
                          (default: evals/reports/<date>-<name>)
    --verbose / -v

decisionlab eval topics <file.txt>
    --stages X,Y          default research
    --env-spec PATH       required iff stages include reason or build
    --reset-kg            wipe KG before topic 1
    --verbose / -v

decisionlab eval pipeline <topic>
    --stages X,Y
    --env-spec PATH
    --verbose / -v
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Success — every assertion passed |
| 1 | At least one assertion failed |
| 2 | Infrastructure failure (auth, missing API key, malformed flags) |

### `decisionlab kg`

```text
decisionlab kg stats [--json]
decisionlab kg reset --confirm                 # destructive; --confirm required
decisionlab kg snapshot <out.json>
decisionlab kg restore <in.json> [--no-reset]
decisionlab kg query "<cypher>" [-p k=v ...]
```

## Programmatic API

The CLI is a thin shell — every command is reachable from Python:

```python
from pathlib import Path
import anthropic
import shared

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.eval import kgadmin
from decisionlab.eval.runner import run_pipeline
from decisionlab.eval.suite import SuiteSpec, run_suite
from decisionlab.router import Stage

await shared.init()
client = anthropic.AsyncAnthropic()
search = DuckDuckGoAdapter()

# Single topic, full pipeline
result = await run_pipeline(
    "Q-learning agent foraging on a grid",
    stages=(Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON, Stage.BUILD),
    env_spec_path=Path("evals/fixtures/env_spec_grid_10x10.json"),
    project_root=Path("evals/runs"),
    client=client, search=search,
)
assert result.succeeded
print("paradigms:", result.paradigms)
print("KG nodes from this run:", result.total_nodes_created())

# Whole suite
spec = SuiteSpec.from_yaml(Path("evals/suites/smoke.yaml"))
suite_result = await run_suite(spec, client=client, search=search)

# KG inspection
stats = await kgadmin.stats()
print(stats.by_label)

await shared.shutdown()
```

For tests that don't have Neo4j wired up, pass `skip_kg_ops=True` to
`run_suite` — KG predicates record as "skipped" rather than crashing.

## Layout on disk

```
phase1-pablo/
├── src/decisionlab/
│   ├── feedback_port.py       FeedbackPort + 3 impls
│   ├── eval/                  Library
│   │   ├── runner.py
│   │   ├── suite.py
│   │   ├── assertions.py
│   │   ├── kgadmin.py
│   │   ├── cost.py
│   │   ├── report.py
│   │   └── models.py
│   └── cli_eval.py            CLI sub-apps
├── evals/
│   ├── suites/                checked-in YAML
│   ├── fixtures/              checked-in env_specs
│   ├── reports/               gitignored — written by `eval run`
│   └── runs/                  gitignored — pipeline scratch
└── tests/eval/                pytest coverage
```

## Performance & cost notes

A research-only run is roughly `1 × Researcher (Sonnet, 10 iters,
4k out) + N × DeepResearcher (Sonnet, 7 iters, 16k out)`. With current
defaults that's ~$0.50–$1.50 per topic. Full-pipeline runs add Opus
formalize + Opus reason + Sonnet build (25 iters), which is closer to
$3–$5 per topic.

For 10-topic populate runs use `decisionlab eval topics` —
research-only is the right default. Reserve `full-pipeline.yaml` for
regression eval suites you'd run weekly, not nightly.

## Roadmap

What's deferred (not in this version):

- **LLM record/replay.** A `RecordingClient` wrapper around
  `AsyncAnthropic` that hashes `(model, messages, tools)` to a fixture
  file, plus a `ReplayClient` that reads them back. Enables
  zero-cost CI evals against a recorded baseline.
- **Parallel topics.** Run N topics concurrently. Needs investigation
  into Neo4j MERGE contention under concurrent writes; sequential is
  the safe default.
- **Multi-paradigm spec_id matching.** `module_imports` and
  `decide_returns_action` currently match the spec_id as a substring of
  the artifact filename. Cleaner would be reading the Builder's
  `state.approved_specs` directly.
- **Cost ceiling per stage.** Cap REASON or BUILD individually rather
  than the whole topic.

## Migration notes

The `FeedbackPort` refactor changes one Router constructor parameter
list:

```python
# Before
Router(client, state, search, project_root, emit=emit)

# After (CLI)
Router(client, state, search, project_root, feedback=CLIFeedback())

# After (web)
Router(client, state, search, project_root, emit=emit, feedback=WebFeedback(emit))
```

The `feedback=` kwarg is optional and defaults to `CLIFeedback()`, so
test sites that don't pass it keep working. `_web_mode` is gone.

Existing tests that did `patch("decisionlab.feedback.review_research", …)`
keep working because `CLIFeedback.review_research` re-imports the
module on each call.
