# System Architecture

## Purpose

Phase 1 transforms a natural-language decision-making problem into executable
Python agents. The system researches scientific paradigms, formalizes them
mathematically, adapts selected formulations to a concrete environment, and
generates tested `DecisionModel` implementations.

The implementation is the `decisionlab` Python package in `phase1-pablo`. It
uses the shared repository package only for infrastructure: database, object
storage, knowledge graph, vector store and embeddings.

## Architectural View

```text
                         +----------------------+
User / CLI / Web / Eval ->| Router               |
                         | - stage machine      |
                         | - human review gates |
                         | - trace events       |
                         | - memory hooks       |
                         +----------+-----------+
                                    |
         +--------------------------+--------------------------+
         |                          |                          |
         v                          v                          v
  Agent pipeline              Artifact layer             Memory layer
  decisionlab/agents          MinIO + artifacts          KG + vectors + PG
         |                          |                          |
         v                          v                          v
 Research reports       research/{run_id}/...        retrieve_knowledge
 Formulations           models/{run_id}/...          cross-run reuse
 Reasoner specs
 Builder code/tests
```

The Router is the central coordinator. Agents do not know the whole pipeline.
They receive narrow inputs, read and write artifacts through tools, and return
stage-level reports. The Router decides when to continue, when to ask for human
review, when to rerun a stage, and when to invoke memory.

## Main Runtime Components

| Component | Responsibility | Main file |
| --- | --- | --- |
| `Router` | Orchestrates stages, review gates, traces, persistence and reruns. | `src/decisionlab/router.py` |
| `PipelineState` | Stores current stage and approved artifacts for resume. | `src/decisionlab/router.py` |
| `run_agent_loop` | Generic Anthropic tool loop for all agentic stages. | `src/decisionlab/runtime/loop.py` |
| `dispatch_tools` | Executes tool calls concurrently and records tool diagnostics. | `src/decisionlab/runtime/dispatcher.py` |
| `FeedbackPort` | Abstracts CLI, web and eval feedback. | `src/decisionlab/feedback_port.py` |
| `Services` | Shared dependency container for infra. | `../shared/shared/services.py` |

## Stage Machine

The current Router is more than the original four-stage design. It includes a
canonical umbrella classifier and optional memory stages:

```text
CLASSIFY_UMBRELLA
  -> RESEARCH -> REVIEW_RESEARCH -> MEMORY_RESEARCH?
  -> FORMALIZE -> REVIEW_FORMALIZE -> MEMORY_FORMALIZE?
  -> GET_ENV_SPEC
  -> REASON -> REVIEW_REASON -> MEMORY_REASON?
  -> BUILD -> REVIEW_BUILD -> MEMORY_BUILD?
  -> DONE
```

The `MEMORY_*` stages only run when the memory infrastructure is available. They
are placed after human review, which is an important design decision: the system
stores accepted output, not every draft produced by an LLM.

## Data and Artifact Flow

```text
research/{run_id}/
  report.md
  deep/{paradigm}.md
  formulations/{paradigm}.md
  env_spec.json
  pipeline_state.json
  trace.jsonl

models/{run_id}/
  reasoner/{paradigm}/{formulation}.json
  builder/{paradigm}/{formulation}_model.py
  builder/{paradigm}/test_{formulation}.py
  builder/{paradigm}/{formulation}_validation.json
```

MinIO stores the real artifact bytes. Postgres stores metadata about runs,
artifacts and registered models. The `PipelineState` is also saved to MinIO so a
run can resume without depending on local disk.

## Agent Boundary

Every agent is intentionally narrow:

- Researcher discovers and summarizes paradigms.
- DeepResearcher creates one deep report per paradigm.
- FormalizerSubAgent writes mathematical formulations for one paradigm.
- ReasonerSubAgent converts selected formulations into JSON implementation specs.
- BuilderSubAgent writes Python model code and tests for one spec.

The fan-out stages use `asyncio.gather`, so multiple paradigms or formulations
can be processed in parallel. Failures are collected per sub-agent instead of
aborting the whole orchestrator immediately.

## Generated Model Contract

The output of Phase 1 is not tied to Phase 2 classes. It follows duck typing:

```python
def decide(self, perception: dict) -> Action
def update(self, action, reward, new_perception) -> None
def get_state(self) -> dict
```

The generated model file defines its own lightweight `Action` dataclass. The
important runtime rule is:

```text
decide(perception) -> read-only action choice
update(action, reward, new_perception) -> all state mutation
get_state() -> inspect internal variables, including q_values
```

The Builder prompt enforces this boundary because Phase 2 calls the model in
this order:

```text
pre_state = model.get_state()
perception = env.build_perception(agent)
action = model.decide(perception)
reward, result = env.apply(action)
new_perception = env.build_perception(agent)
model.update(action, reward, new_perception)
```

## Shared Infrastructure Boundary

Phase 1 owns:

- agents and prompts
- Anthropic/OpenRouter calls
- tool schemas and tool handlers
- pipeline orchestration
- memory semantics
- generated model requirements

The shared package owns:

- Postgres connectivity and ORM models
- MinIO object storage
- Neo4j client and schema
- Qdrant vector collections
- Voyage/ZeroEntropy embedding and reranking client
- memory lifecycle helpers

The dependency boundary is the immutable `Services` dataclass. This avoids
module-level global state and keeps Phase 1 from importing Juan's Phase 2
application.

## Reliability Shape

The infrastructure has two levels:

```text
Required for Phase 1 run:
  Postgres
  MinIO

Optional, degraded independently:
  Neo4j
  Qdrant
  Voyage embeddings
  ZeroEntropy reranker
```

If knowledge infrastructure is missing, the pipeline still runs. The agents lose
retrieval and memory benefits, but the core generation path remains available.

## Code Anchors

- Stage enum and state: `src/decisionlab/router.py`
- Agent runtime loop: `src/decisionlab/runtime/loop.py`
- Tool dispatch: `src/decisionlab/runtime/dispatcher.py`
- Agent model settings: `src/decisionlab/config.py`
- Generated contract prompt: `src/decisionlab/agents/builder_sub.py`
- Shared services: `../shared/shared/services.py`
- Shared ORM models: `../shared/shared/models.py`

