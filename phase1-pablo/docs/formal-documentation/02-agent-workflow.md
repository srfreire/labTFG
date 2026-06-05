# Agent Workflow

## Overview

The workflow is a staged transformation:

```text
Natural-language problem
  -> scientific paradigms
  -> mathematical formulations
  -> environment-adapted JSON specs
  -> Python DecisionModel code and tests
```

Each transition narrows ambiguity. Early stages are exploratory and textual.
Later stages are structured and executable.

## Complete Flow

```text
1. Classifier
   Input: problem
   Output: canonical umbrella candidate

2. Researcher
   Input: problem + known paradigm slugs
   Output: summary report + deep reports

3. Human review
   Input: research artifacts
   Output: approved paradigm slugs

4. Formalizer
   Input: approved deep reports
   Output: mathematical formulations per paradigm

5. Human review
   Input: formulation docs
   Output: selected formulation slugs

6. Environment spec
   Input: JSON file supplied by feedback port
   Output: env_spec.json in run artifacts

7. Reasoner
   Input: selected formulations + env_spec
   Output: one JSON spec per valid formulation

8. Human review
   Input: JSON specs / invalid reports
   Output: approved implementation specs

9. Builder
   Input: approved JSON specs
   Output: Python model files + tests

10. Human review
    Input: generated code/test results
    Output: registered models
```

Memory stages may run after accepted review gates, but the main cognitive chain
is the one above.

## 1. Classifier

The classifier is a small structured-output step before research. It tries to
anchor the problem to a broad canonical paradigm from
`canonical-paradigms.json`.

Why it exists:

- prevents variant slugs such as `q-learning` from fragmenting an existing
  umbrella such as `reinforcement-learning`
- gives the Researcher a canonical option before it starts web search
- degrades safely if the classifier or canonical fixture is unavailable

The result is stored only in memory for the current run. It is not persisted as
a formal run artifact.

## 2. Researcher and DeepResearcher

The Researcher performs broad discovery. It has tools for:

- `retrieve_knowledge`
- `web_search`
- `launch_deep_research`
- `read_report`

Its current behavior has two layers:

```text
programmatic step:
  list_known_slugs(problem) -> candidate canonical slugs

agentic step:
  retrieve_knowledge once
  web_search for gaps
  launch_deep_research per gap paradigm
  read full deep reports
  synthesize final report
```

The structured emission at the end is constrained to known slugs plus the
`__NEW__` sentinel. If the model emits `__NEW__`, canonicalization checks the KG
before minting a new slug.

The DeepResearcher is a focused sub-agent. It receives one paradigm and produces
a deep scientific report:

```text
deep/{paradigm}.md
  Foundations
  Postulates
  Assumptions
  Predictions
  Primary Locus
  Key Concepts
  Identified variables
  References
```

The parent Researcher only receives a concise summary from each DeepResearcher.
The full report is saved as an artifact for later stages.

## 3. Formalizer

The Formalizer is an orchestrator. It launches one `FormalizerSubAgent` per
approved paradigm:

```text
approved paradigms
  -> Formalizer
       -> SubAgent(paradigm A)
       -> SubAgent(paradigm B)
       -> SubAgent(paradigm C)
  -> formulations/{slug}.md
```

Each sub-agent reads `deep/{slug}.md` and writes
`formulations/{slug}.md`. It must produce 2 or 3 meaningfully different
mathematical formulations. Differences should be structural, not cosmetic:

- ODE vs algebraic control
- probabilistic belief model vs utility scoring
- reinforcement learning update vs threshold policy

Each formulation contains:

- variables
- parameters
- equations in plain-text and LaTeX
- executable decision logic
- comparison against the other formulations

The formalizer stage is still textual, but it prepares the system for
implementation by requiring concrete variables, parameters and decision rules.

## 4. Human Selection of Formulations

After formalization, the user selects which formulations continue. The feedback
layer converts selected headings into stable slugs.

This is a key narrowing point:

```text
all generated formulations
  -> human selects useful/valid formulations
  -> Reasoner receives only selected formulation slugs
```

The system deliberately keeps the human in the loop before environmental
adaptation, because not every mathematical variant is worth implementing.

## 5. Environment Specification

The Reasoner cannot produce implementation specs until it knows the simulation
environment. The environment spec is a JSON artifact supplied through the
feedback port and saved as:

```text
research/{run_id}/env_spec.json
```

The Reasoner treats this file as authoritative for:

- grid shape and perception fields
- available actions
- resource types and properties
- reward sources
- environment constraints

## 6. Reasoner

The Reasoner adapts mathematical formulations to the environment. Like the
Formalizer, it fans out one sub-agent per paradigm.

Each `ReasonerSubAgent` reads:

```text
deep/{paradigm}.md
formulations/{paradigm}.md
env_spec.json
```

For each selected formulation it writes:

```text
models/{run_id}/reasoner/{paradigm}/{formulation}.json
```

The JSON spec is the Builder's contract. It contains:

- `formulation_id`
- `paradigm`
- model name and description
- variables and parameters
- update rules
- decision logic
- environment mapping
- expected behaviors
- references

The Reasoner also validates formulations before writing implementation specs.
Invalid formulations are written as validation reports at the same path, with
`status: "invalid"` and concrete problems.

The validation checks are prompt-level but explicit:

- variables used in rules must be defined
- equations must not be incoherently circular
- decision logic must reference existing constructs
- defaults must be reasonable
- actions must exist in `env_spec`
- perception mappings must be observable or computable

## 7. Builder

The Builder receives approved Reasoner specs and launches one sub-agent per
spec:

```text
approved JSON specs
  -> Builder
       -> BuilderSubAgent(spec 1)
       -> BuilderSubAgent(spec 2)
  -> Python model + tests
```

Each BuilderSubAgent reads a JSON spec and writes:

```text
builder/{paradigm}/{formulation}_model.py
builder/{paradigm}/test_{formulation}.py
```

It then calls `run_tests`, which materializes the relevant files and runs tests
with `uv run pytest`.

The Builder validates implementability before code generation. Invalid specs
produce:

```text
builder/{paradigm}/{formulation}_validation.json
```

and do not produce code.

## Code Generation Contract

Generated model files must be self-contained and use only standard library/math
style dependencies. Each file defines:

```python
@dataclass
class Action:
    name: str
    params: dict = field(default_factory=dict)
```

The main class name is deterministic. It is derived from the formulation slug:

```text
drive-reduction-rl -> DriveReductionRlModel
```

This avoids a common mismatch where file name, spec id and class name drift
apart.

## Review and Rerun Paths

Human review can rerun different depths of the pipeline:

```text
Research review:
  add a missing paradigm -> DeepResearcher

Reason review:
  bad formulation -> Formalizer then Reasoner
  bad adaptation -> Reasoner only

Build review:
  bad spec -> Reasoner then Builder
  bad implementation -> Builder only
```

This matters because the Router can correct a problem at the right level. A bad
mathematical formulation should not be fixed by only patching generated code.

## Important Quality Controls

| Control | Location | Purpose |
| --- | --- | --- |
| stage retry cap | Router loop | prevents infinite failed stage loops |
| exact artifact paths | prompts + Router validation | prevents downstream lookup drift |
| deterministic class names | Builder + Router registration | keeps registry aligned |
| `decide`/`update` separation | Builder prompt | avoids simulation side effects |
| `q_values` in state | Builder prompt | supports downstream analysis |
| per-spec tests | BuilderSubAgent | executable validation |
| memory after review | Router memory stages | stores curated knowledge |

## Code Anchors

- Router stage handlers: `src/decisionlab/router.py`
- Researcher: `src/decisionlab/agents/researcher.py`
- DeepResearcher: `src/decisionlab/agents/deep_researcher.py`
- Formalizer: `src/decisionlab/agents/formalizer.py`
- Reasoner: `src/decisionlab/agents/reasoner.py`
- Builder: `src/decisionlab/agents/builder.py`
- Builder prompt and class-name rule: `src/decisionlab/agents/builder_sub.py`
- Test execution tool: `src/decisionlab/tools/tests.py`

