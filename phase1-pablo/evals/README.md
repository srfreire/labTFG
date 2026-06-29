# Evals

Layout:

```
evals/
├── suites/      # checked-in YAML suites
├── fixtures/    # checked-in env_specs and other input fixtures
├── reports/     # gitignored — written by `decisionlab eval run`
└── runs/        # gitignored — pipeline scratch (reports_dir, *_model.py)
```

## Quick start

```bash
# Stats — prove the KG is reachable
decisionlab kg stats

# Smoke: 1 topic, research-only, ~1-3 min, <$2
decisionlab eval run evals/suites/smoke.yaml

# Bulk-populate: 10 topics from a list, no assertions
decisionlab eval topics evals/topics-bulk.txt --reset-kg

# One-shot ad-hoc topic
decisionlab eval pipeline "How do humans choose between speed and accuracy?"

# Full pipeline (expensive — research → formalize → reason → build)
decisionlab eval run evals/suites/full-pipeline.yaml

# PDF-only corpus eval: web_search and search_papers see only zip PDFs
LABTFG_EVAL_KG=1 decisionlab eval run evals/suites/caso1-pdf-corpus.yaml
LABTFG_EVAL_KG=1 decisionlab eval run evals/suites/caso2-pdf-corpus.yaml
```

After any suite the report lands in `evals/reports/<date>-<suite>/`
(both `report.md` and `report.json`). Pass `--report PATH` to override.

## Suites

| Suite | Stages | Budget | What it checks |
|---|---|---|---|
| `smoke.yaml` | research | $2 | Pipeline boots, finds ≥2 paradigms |
| `cumulative-growth.yaml` | research | $10 | KG grows monotonically over 5 related topics |
| `full-pipeline.yaml` | research → build | $8 | Full chain produces an importable DecisionModel |

See `decisionlab/eval/assertions.py` for the full predicate set.

## Add a new suite

```yaml
# evals/suites/my-suite.yaml
name: my-suite
stages: [research]              # contiguous prefix; default research-only
reset_kg_before: false          # true wipes the KG before topic 1
topics:
  - text: "your topic here"
    expect:
      research:
        - paradigm: reinforcement-learning
        - min_nodes: { label: Paradigm, n: 3 }
budget:
  max_usd_total: 5.00           # hard-kills mid-topic when exceeded
```

If you set `stages` to include `reason` or `build`, also set
`env_spec: evals/fixtures/env_spec_grid_10x10.json` (or any valid
env_spec JSON for your environment).

### PDF-only corpus mode

Suites may declare `eval_corpus:` as a zip path or list of zip paths. Each
zip must contain PDFs. In that mode the eval CLI replaces production
web search with a local corpus provider:

- `web_search` returns only web-like snippets from those PDFs.
- `search_papers` returns corpus paper metadata plus extracted document text.
- The report directory includes `artifact-bundle/` with copied corpus files,
  generated storage artifacts, DB memory rows, and a KG snapshot when available.

You can also pass corpus zips from the CLI:

```bash
decisionlab eval run evals/suites/my-suite.yaml \
  --eval-corpus ~/Downloads/my-case.zip
```

When `reset_kg_before: true`, the usual eval KG safety guard applies: set
`LABTFG_EVAL_KG=1` or point Neo4j at an eval-marked database.

## Programmatic use

The CLI is a thin shell over the library — everything is reachable from
Python:

```python
from decisionlab.eval.runner import run_pipeline
from decisionlab.eval.suite import SuiteSpec, run_suite
from decisionlab.eval import kgadmin
import shared, anthropic
from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter

await shared.init()
client = anthropic.AsyncAnthropic()
search = DuckDuckGoAdapter()

# One topic
result = await run_pipeline(
    "How do animals exploit vs. explore?",
    project_root=Path("evals/runs"),
    client=client, search=search,
)
print(result.paradigms, result.total_nodes_created())

# A whole suite
spec = SuiteSpec.from_yaml(Path("evals/suites/smoke.yaml"))
suite_result = await run_suite(spec, client=client, search=search)

# KG inspection
print(await kgadmin.stats())
await shared.shutdown()
```

## Running in CI

`decisionlab eval run` exits 0 when every assertion passes, 1 when at
least one fails, 2 on infra errors (auth, missing API key). Wire that
into a workflow file alongside the existing `ruff + pytest` job.

For cheap CI without burning Anthropic tokens, use the existing
`decisionlab.mock_server` for UI replay; an LLM record/replay layer for
evals is on the roadmap (see `docs/eval-system.md`).
