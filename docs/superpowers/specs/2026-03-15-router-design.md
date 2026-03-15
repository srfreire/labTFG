# Router — Pipeline Orchestration & Human Feedback

## Overview

State-machine-based Router that orchestrates the full 4-agent pipeline (Researcher → Formalizer → Reasoner → Builder) with interactive human feedback between each stage, per-paradigm re-runs, and LLM-based routing for ambiguous feedback.

## Decisions

| Decision | Value | Reason |
|----------|-------|--------|
| Architecture | Explicit state machine | Natural fit: discrete stages, persistable, testable, resume-friendly |
| Routing LLM | Claude Haiku | Classification task only — cheap, fast, sufficient |
| env_spec input | Interactive (questionary path prompt) | Asked when needed, not upfront |
| UI framework | questionary | Already a dependency; checkboxes, confirms, text prompts |
| Re-run scope | Per paradigm | Agent APIs work per-paradigm; per-formulation not supported without agent changes |
| Resume support | `pipeline_state.json` + `--from` override | Filesystem alone can't capture user selections |

---

## 1. Pipeline State

Persisted as `reports_dir/pipeline_state.json`. Serialized/deserialized with `json`.

```python
class Stage(str, Enum):
    RESEARCH = "research"
    REVIEW_RESEARCH = "review_research"
    FORMALIZE = "formalize"
    REVIEW_FORMALIZE = "review_formalize"
    GET_ENV_SPEC = "get_env_spec"
    REASON = "reason"
    REVIEW_REASON = "review_reason"
    BUILD = "build"
    REVIEW_BUILD = "review_build"
    DONE = "done"

@dataclass
class PipelineState:
    stage: Stage
    problem: str
    reports_dir: Path

    # Filled progressively
    approved_paradigms: list[str]                   # slugs approved post-research
    selected_formulations: dict[str, list[int]]     # {paradigm_slug: [1-based formulation numbers]} post-formalize
    env_spec_path: Path | None
    approved_specs: list[str]                       # formulation_ids approved post-reason
    pending_reruns: list[RerunRequest]               # for re-routing

    def save(self) -> None: ...      # atomic write to reports_dir/pipeline_state.json (write tmp + rename)
    @classmethod
    def load(cls, reports_dir: Path) -> "PipelineState": ...  # raises clear error on corrupt JSON

@dataclass
class RerunRequest:
    target: str          # "researcher" | "formalizer" | "reasoner" | "builder"
    paradigm: str        # paradigm slug
    feedback: str        # user's feedback text
```

---

## 2. Router — stage handlers and transitions

```python
class Router:
    def __init__(self, client: AsyncAnthropic, state: PipelineState,
                 search: WebSearchPort, project_root: Path):
        self.client = client
        self.state = state
        self.search = search          # injected for Researcher/DeepResearcher
        self.project_root = project_root  # needed by Builder for run_tests cwd
        self.console = Console()

    async def run(self):
        handlers = {
            Stage.RESEARCH: self._do_research,
            Stage.REVIEW_RESEARCH: self._review_research,
            Stage.FORMALIZE: self._do_formalize,
            Stage.REVIEW_FORMALIZE: self._review_formalize,
            Stage.GET_ENV_SPEC: self._get_env_spec,
            Stage.REASON: self._do_reason,
            Stage.REVIEW_REASON: self._review_reason,
            Stage.BUILD: self._do_build,
            Stage.REVIEW_BUILD: self._review_build,
        }
        while self.state.stage != Stage.DONE:
            handler = handlers[self.state.stage]
            await handler()
            self.state.save()
```

Each handler:
1. Executes its task (run agent or collect feedback).
2. Mutates `self.state.stage` to the next state.
3. State is saved after handler returns.

Review handlers that request additional work (e.g., "investigate another paradigm") loop internally — the state machine only moves forward except for post-Builder re-routing.

### Stage transition diagram

```
RESEARCH → REVIEW_RESEARCH → FORMALIZE → REVIEW_FORMALIZE → GET_ENV_SPEC
    → REASON → REVIEW_REASON → BUILD → REVIEW_BUILD → DONE
                                              ↓ (re-routing)
                                    re-run target agent(s)
                                    then back to REVIEW_BUILD
```

---

## 3. Human Feedback — interactions per stage

All interactions use `questionary` (async-compatible via `asyncio.to_thread`).

### REVIEW_RESEARCH

1. Discover paradigm slugs from `deep/*.md`.
2. `questionary.checkbox`: select which paradigms to approve.
3. `questionary.confirm`: "Investigate additional paradigms?"
4. If yes → `questionary.text` for paradigm name → launch `DeepResearcher` for that paradigm only → loop back to checkbox.
5. When confirmed → store `approved_paradigms`, advance to `FORMALIZE`.

### REVIEW_FORMALIZE (double-level selection)

1. **Level 1**: `questionary.checkbox` — select paradigms from those formalized.
2. **Level 2**: per selected paradigm, parse formulation headers from the `.md` (`## Formulation N: name`), present `questionary.checkbox`.
3. Store `selected_formulations = {"paradigm_slug": [1, 3]}` (1-based formulation numbers).
4. **Filter formulation files**: rewrite each selected paradigm's `formulations/{slug}.md` keeping only the selected formulations. This ensures the Reasoner (which reads the full file from disk) only processes the user's selection.
5. Advance to `GET_ENV_SPEC`.

Note: formulation IDs (e.g., `homeostatic-regulation_pi_negative_feedback`) do not exist at this stage — they are generated by the Reasoner. Selection is by ordinal position within the markdown file.

### GET_ENV_SPEC

1. `questionary.path`: "Path to env_spec.json from Phase 2".
2. Validate file exists and is valid JSON.
3. Copy to `reports_dir/env_spec.json`.
4. Advance to `REASON`.

### REVIEW_REASON

1. List generated specs from `reasoner/*.json`.
2. Per spec: display summary, `questionary.confirm` — "Approve?"
3. If rejected: `questionary.text` — "What needs fixing?" → re-run Reasoner for the paradigm that contains that spec → loop.
4. When all approved → store `approved_specs`, advance to `BUILD`.

### REVIEW_BUILD

1. Display build results per formulation (tests passed/failed).
2. If all pass: `questionary.confirm` → `DONE`.
3. If issues: `questionary.text` — free-form feedback → pass to **routing LLM**.

---

## 4. Routing LLM — Haiku classifier

Only invoked in `REVIEW_BUILD` for free-form feedback classification.

### System prompt

```
You are a feedback classifier for a decision-making modeling pipeline.
Given user feedback about a generated model, decide which agent must re-execute.

Respond ONLY with JSON:
{
  "target": "researcher" | "formalizer" | "reasoner" | "builder",
  "paradigm": "affected paradigm slug",
  "reason": "brief explanation"
}

Criteria:
- "builder": implementation problem (code bug, test failure, import error)
- "reasoner": specification problem (wrong rule, incorrect pseudocode, bad env mapping)
- "formalizer": formalization problem (wrong equations, missing variables, bad mathematical model)
- "researcher": paradigm poorly researched (missing theory, incorrect postulates)
```

### Context provided to Haiku

- List of paradigms and formulations in this run.
- The Reasoner JSON spec for the relevant formulation.
- Builder test output / error messages (if any).
- User's free-form feedback.

### Re-run cascade

After Haiku classifies the target, the Router confirms with the user before executing (cascades can be expensive):

| Target | Cascade |
|--------|---------|
| `builder` | Re-run Builder for that paradigm |
| `reasoner` | Re-run Reasoner for that paradigm → then Builder for it |
| `formalizer` | Re-run Formalizer for that paradigm → Reasoner → Builder |
| `researcher` | Re-run DeepResearcher for that paradigm → Formalizer → Reasoner → Builder (full cascade) |

All re-runs are **per paradigm** (the granularity supported by existing agent APIs). After cascade completes → return to `REVIEW_BUILD`.

---

## 5. CLI commands

### Modified: `run`

```python
@app.command()
def run(
    problem: str = typer.Argument(help="Decision-making problem"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run the full pipeline with interactive human feedback."""
    reports_dir = _reports_dir(problem)
    state = PipelineState(stage=Stage.RESEARCH, problem=problem, reports_dir=reports_dir)
    state.save()
    router = Router(client=_client(), state=state,
                    search=DuckDuckGoAdapter(), project_root=Path.cwd())
    _run_async(router.run())
```

### New: `resume`

```python
@app.command()
def resume(
    reports_dir: Path = typer.Option(..., "--reports-dir"),
    from_stage: str = typer.Option(None, "--from", help="Jump to stage"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Resume a pipeline from saved state or from a specific stage."""
    state = PipelineState.load(reports_dir)
    if from_stage:
        state.stage = Stage[from_stage.upper()]
        state.save()
    router = Router(client=_client(), state=state,
                    search=DuckDuckGoAdapter(), project_root=Path.cwd())
    _run_async(router.run())
```

Individual commands (`research`, `formalize`, `reason`, `build`) remain unchanged — useful for manual execution outside the pipeline.

---

## 6. File structure — changes

| File | Action | Description |
|------|--------|-------------|
| `src/decisionlab/router.py` | Rewrite (stub → full) | `Router` class, `PipelineState`, `Stage` enum |
| `src/decisionlab/feedback.py` | Create | questionary interaction functions, one per review stage |
| `src/decisionlab/routing_llm.py` | Create | `classify_feedback()` — Haiku call for re-routing |
| `src/decisionlab/cli.py` | Modify | Replace `run()`, add `resume()` |
| `src/decisionlab/domain/models.py` | Modify | Add `RerunRequest` dataclass |

No agent files are modified. The Router instantiates and calls them as-is.

---

## 7. Error handling

- **Agent failures**: if an agent raises an exception (API timeout, rate limit), the Router catches it, prints the error, and stays at the current stage. The user can `resume` to retry.
- **Ctrl-C**: `KeyboardInterrupt` during a questionary prompt loses in-progress selections but state was saved after the previous handler completed. Resume picks up at the current review stage.
- **Corrupt `pipeline_state.json`**: `PipelineState.load()` catches `json.JSONDecodeError` and raises a clear error message. Atomic writes (tmp + rename) prevent partial writes.
- **`--from` validation**: when resuming with `--from`, the Router validates that required state fields are populated for that stage (e.g., `BUILD` requires `approved_specs` and `env_spec_path`). Raises an error with guidance if prerequisites are missing.
- **Haiku model**: use `claude-haiku-4-5` (matching existing codebase convention in `deep_researcher.py`).

---

## 8. Dependencies

No new dependencies. Uses existing: `anthropic`, `questionary`, `rich`, `typer`.
