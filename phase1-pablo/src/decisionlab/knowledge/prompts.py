"""Stage-specific extraction prompts for the knowledge extraction module.

Each stage gets a system prompt and a user prompt template.
The user prompt template accepts the stage output text via str.format().
"""

import json
from importlib.resources import files

# ---------------------------------------------------------------------------
# Canonical paradigm vocabulary (loaded once at module import)
# ---------------------------------------------------------------------------
#
# The canonical list is rendered into the Researcher / Formalizer / Reasoner
# system prompts as a constrained vocabulary. List order is preserved
# verbatim from ``canonical-paradigms.json`` so prompt strings are
# deterministic across processes (prompt caching needs byte-identical
# system prompts to hit).

_CANONICAL: list[dict[str, str]] = json.loads(
    (files("decisionlab.data") / "canonical-paradigms.json").read_text()
)

_CANONICAL_LIST = "\n".join(
    f"{i}. {p['slug']}: {p['definition']}" for i, p in enumerate(_CANONICAL, start=1)
)

_CANONICAL_DIRECTIVE = f"""\
Canonical paradigms (reuse verbatim or emit `__NEW__`):
The following paradigms already exist in the knowledge graph. When emitting \
a Paradigm node, or a `paradigm_slug` field on a Variable or Postulate, \
reuse one of these `slug` values exactly. Only emit `slug: "__NEW__"` if \
the topic genuinely does not fit any of them — do NOT invent new variants \
of an existing slug (e.g. `q-learning` when `reinforcement-learning` \
already covers it).

{_CANONICAL_LIST}\
"""

# ---------------------------------------------------------------------------
# Shared JSON schema description (injected into all system prompts)
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """\
{
  "nodes": [
    {
      "label": "<Neo4j label>",
      "properties": { "<key>": "<value>", ... },
      "natural_key": "<property name used for dedup>"
    }
  ],
  "relations": [
    {
      "from_label": "<source node label>",
      "from_key_value": "<natural key value of source>",
      "to_label": "<target node label>",
      "to_key_value": "<natural key value of target>",
      "rel_type": "<RELATION_TYPE>",
      "properties": { ... }
    }
  ],
  "facts": [
    "<atomic plain-text fact — one statement, no compound sentences>"
  ]
}\
"""

# ---------------------------------------------------------------------------
# Researcher extraction
# ---------------------------------------------------------------------------

RESEARCHER_SYSTEM = f"""\
You are a knowledge extraction agent. You receive a deep research report about a \
scientific paradigm and extract structured entities, relations, and atomic facts.

Output ONLY valid JSON matching this schema (no markdown fences, no commentary):
{_JSON_SCHEMA}

{_CANONICAL_DIRECTIVE}

Node types to extract:
- Paradigm: properties={{name, slug, description}}. natural_key="slug". A \
Paradigm is a NAMED THEORY OF DECISION-MAKING with quantifiable mechanisms \
and identifiable authors (e.g. "reinforcement learning", "prospect theory", \
"drift-diffusion model", "bounded rationality", "free-energy principle"). \

DO NOT extract as Paradigm: \
  - aspects of a paradigm ("speed-accuracy tradeoff", "two-alternative forced-choice") \
  - adjectives or qualifiers ("risk-averse", "high-probability", "long-run") \
  - generic terms ("decision-making", "trade-off", "open-ended") \
  - web-page chrome ("faculty publications", "full text", section headings) \
  - truncated identifiers, hashes, or UUID fragments \

If the prose mentions a concept that doesn't have an established name plus \
quantifiable mechanism, OMIT it from Paradigm extraction. Slug is the \
kebab-case version of the paradigm name.
- Author: properties={{name, affiliation}}. natural_key="name".
- Paper: properties={{title, year, doi, citation_count}}. natural_key="title". \
Parse from the References section and inline citations. Set doi/citation_count to \
null if not available.
- BrainRegion: properties={{name, description, system}}. natural_key="name". \
System is one of: homeostatic, hedonic, cognitive, or null. \
description is a 1-sentence summary of the region's primary function (e.g. \
"Hypothalamus: regulates homeostasis, hormonal control of hunger/thirst/temperature"); \
disambiguates aliases (e.g. "VTA" vs "ventral tegmental area") and enriches retrieval.
- Variable: properties={{name, description, type, range, unit, paradigm_slug}}. natural_key="name". \
Extract from the "Identified Variables" table. Type is the Role column value. \
description is a 1-sentence semantic explanation of the variable in the context of \
its paradigm (e.g. "reward: scalar feedback signal received after each action") — \
this disambiguates same-named variables across paradigms ("reward" in RL vs \
prospect-theory) and improves retrieval embeddings beyond the bare name. \
paradigm_slug must be the slug of the Paradigm this report describes — it scopes \
the variable name within its paradigm so "reward" in reinforcement-learning is \
distinct from "reward" in prospect-theory.
- Postulate: properties={{id, statement, falsifiable, paradigm_slug}}. natural_key="id". \
Id MUST be scoped to the postulate's paradigm to prevent cross-paradigm collisions: \
emit it as "{{paradigm-slug}}:P1", "{{paradigm-slug}}:P2", etc. — for example \
"reinforcement-learning:P1", "prospect-theory:P1". Use the slug of the Paradigm \
this postulate BELONGS_TO. paradigm_slug duplicates the prefix as a separate \
property for downstream queries. Falsifiable is true if the statement can be \
empirically tested.

Relation types to extract:
- BELONGS_TO: Postulate → Paradigm (the paradigm the postulate belongs to)
- AUTHORED: Author → Paper (authorship)
- SUPPORTS: Paper → Postulate (with properties: confidence 0-1, quote)
- MEASURES: Variable → BrainRegion (the brain region/system the variable measures)

Facts: produce one atomic fact per postulate (what it claims), one per variable \
(its role in the paradigm). Each fact must be a single, self-contained statement.\
"""

RESEARCHER_USER = (
    "Extract entities, relations, and facts from this deep research report:\n\n{text}"
)

# ---------------------------------------------------------------------------
# Formalizer extraction
# ---------------------------------------------------------------------------

FORMALIZER_SYSTEM = f"""\
You are a knowledge extraction agent. You receive a mathematical formalization \
document containing formulations with equations, variables, and parameters. \
Extract structured entities, relations, and atomic facts.

Output ONLY valid JSON matching this schema (no markdown fences, no commentary):
{_JSON_SCHEMA}

{_CANONICAL_DIRECTIVE}

Node types to extract:
- Equation: properties={{latex, plaintext, type}}. natural_key="plaintext". \
Type is one of: ODE, algebraic, probabilistic. Extract from ### Equations sections.
- Variable: properties={{name, description, type, range, unit, paradigm_slug}}. natural_key="name". \
Extract from ### Variables tables. Type is the Type column value. \
description is a 1-sentence semantic explanation of the variable's role in this \
formulation (e.g. "Q(s,a): action-value function — expected discounted return for \
taking action a in state s"). Carry it through from the Researcher's extraction \
when present; otherwise derive from the variable's row commentary or the \
formulation's narrative. \
paradigm_slug must be the slug of the Paradigm whose formalization this document \
describes (the Researcher upstream sets it; if absent, derive from the document's \
paradigm name).
- Parameter: properties={{name, default_value, source, range}}. natural_key="name". \
Extract from ### Parameters tables. default_value should be a number or string.
- Formulation: properties={{id, name, type, description}}. natural_key="id". \
Id is inferred from the formulation heading (e.g., "Formulation 1"). \
Type is the approach (e.g., "ODE-based control", "Q-learning MDP").

Relation types to extract:
- USES_EQUATION: Formulation → Equation (which equations each formulation uses)
- MODULATES: Variable → Variable (with properties: direction="positive"|"negative", \
equation_ref). Extract from equations where one variable influences another.

Facts: produce one atomic fact per equation (what it computes/means), one per \
parameter (its source and role). Each fact must be a single, self-contained statement.\
"""

FORMALIZER_USER = (
    "Extract entities, relations, and facts from this formalization document:\n\n{text}"
)

# ---------------------------------------------------------------------------
# Reasoner extraction
# ---------------------------------------------------------------------------

REASONER_SYSTEM = f"""\
You are a knowledge extraction agent. You receive a Reasoner JSON specification \
that validates and refines a formulation. Extract structured entities, relations, \
and atomic facts.

Output ONLY valid JSON matching this schema (no markdown fences, no commentary):
{_JSON_SCHEMA}

{_CANONICAL_DIRECTIVE}

Node types to extract:
- Parameter: properties={{name, default_value, source, range}}. natural_key="name". \
Extract from the "parameters" array. Use the default from the spec (may differ from \
the formalizer's defaults — the reasoner has validated/updated them).
- Formulation: properties={{id, name, type, description}}. natural_key="id". \
Extract from formulation_id and name fields.

Relation types to extract:
- DERIVES_FROM: Parameter → Postulate. properties={{derivation_chain}}. \
For each parameter, trace which postulate justifies it by examining the "source" \
field and "rules" array (rules reference source_postulate). The derivation_chain \
is a string describing the logical path from postulate to parameter value.

Facts: produce one fact per validation check (expected_behaviors entries — whether \
each can be tested), one per env_mapping decision (how perception maps to variables, \
which actions are used, what the reward source is). Each fact must be atomic.\
"""

REASONER_USER = (
    "Extract entities, relations, and facts from this Reasoner specification:\n\n{text}"
)

# ---------------------------------------------------------------------------
# Builder extraction
# ---------------------------------------------------------------------------

BUILDER_SYSTEM = f"""\
You are a knowledge extraction agent. You receive Python model code generated by \
the Builder agent, possibly followed by test results. Extract structured entities, \
relations, and atomic facts.

Output ONLY valid JSON matching this schema (no markdown fences, no commentary):
{_JSON_SCHEMA}

Node types to extract:
- Model: properties={{formulation_id, class_name, passed, failure_reason}}. \
natural_key="formulation_id". Extract formulation_id from the module docstring or \
filename pattern. class_name is the main model class that implements the \
DecisionModel contract (has decide, update, get_state methods). passed is a boolean \
test outcome (true if all tests pass, false otherwise); omit it when no test output \
is present. failure_reason is a brief description when passed is false, otherwise \
null. Emit exactly one Model node — do NOT emit a separate TestResult node; fold \
test outcomes into the Model's properties.

Relation types to extract:
- IMPLEMENTS: Model → Formulation (the model implements a formulation). \
Use the formulation_id as both the Model's and the Formulation's natural key value.

Facts: produce one fact per test outcome (e.g., "Model X passes behavior test B1: \
<description>"), one per notable code pattern (e.g., "uses Q-learning with softmax", \
"implements PI controller with anti-windup"). Each fact must be atomic.\
"""

BUILDER_USER = (
    "Extract entities, relations, and facts from this Builder output:\n\n{text}"
)

# ---------------------------------------------------------------------------
# Importance scoring (Haiku — batch all facts in one call)
# ---------------------------------------------------------------------------

IMPORTANCE_SCORING_SYSTEM = """\
You are a knowledge importance scorer for a decision-making research lab. \
You receive a list of facts extracted from a pipeline stage and rate each \
fact's importance on a 1-10 scale.

Scoring guide:
- 1-3: Trivial — grid dimensions, formatting details, generic implementation notes
- 4-5: Contextual — variable names, standard parameter values, common patterns
- 6-7: Informative — specific mechanisms, named equations, cited sources
- 8-10: Fundamental — core paradigm mechanisms, key findings, validated parameters, \
novel insights

Call the provided tool to return a structured object. Each entry must repeat the \
exact fact text you scored. Importance values are floats in [1.0, 10.0].\
"""

IMPORTANCE_SCORING_USER = "Rate the importance of each fact for a researcher studying decision-making paradigms:\n\n{facts_json}"

# ---------------------------------------------------------------------------
# Conflict classification (Sonnet — called per duplicate pair)
# ---------------------------------------------------------------------------

CONFLICT_CLASSIFICATION_SYSTEM = """\
You are a memory conflict resolver for a decision-making research lab. \
You receive an existing memory and a new fact, along with their source \
stages and timestamps, and classify their relationship.

Classifications:
- DUPLICATE: The new fact conveys the same information as the existing memory. \
No new knowledge is added.
- CORROBORATION: The new fact independently confirms the existing memory. \
Both come from different sources or stages.
- ENRICHMENT: The new fact adds meaningful detail to the existing memory \
(e.g., a source citation, a more precise value, additional context). \
Provide merged_content that combines both.
- CONTRADICTION: The new fact conflicts with the existing memory \
(e.g., different parameter values, opposing claims). \
The new fact should supersede the old one.

Output ONLY valid JSON (no markdown fences, no commentary):
{
  "classification": "DUPLICATE" | "CORROBORATION" | "ENRICHMENT" | "CONTRADICTION",
  "reasoning": "<brief explanation>",
  "merged_content": "<combined text — required for ENRICHMENT, null otherwise>"
}\
"""

CONFLICT_CLASSIFICATION_USER = """\
Existing memory (stage: {existing_stage}, created: {existing_timestamp}):
{existing_content}

New fact (stage: {new_stage}):
{new_content}

Classify the relationship between the existing memory and the new fact.\
"""

# ---------------------------------------------------------------------------
# Reflection generation (Haiku — called per cluster of >=3 memories)
# ---------------------------------------------------------------------------

REFLECTION_SYSTEM = """\
You are a research synthesis agent for a decision-making research lab. \
You receive a cluster of related facts from a pipeline run and synthesize \
1-2 higher-level insights that capture the key pattern or finding.

Guidelines:
- Be specific and scientific — no vague generalities
- Each insight should integrate information across multiple facts
- Insights should be actionable for future research runs
- Keep each insight to 1-2 sentences

Call the provided tool to return the structured object. The ``insights`` \
list contains 1-2 entries — emit a second insight only when there is a \
genuinely distinct second pattern.\
"""

REFLECTION_USER = """\
Synthesize higher-level insights from these related facts discovered during \
a research pipeline run:

{numbered_facts}\
"""

# ---------------------------------------------------------------------------
# Contradiction detection (Haiku — checks if two reflections contradict)
# ---------------------------------------------------------------------------

CONTRADICTION_CHECK_SYSTEM = """\
You are a contradiction detector. You receive two reflections (higher-level \
insights) from a research knowledge base. Determine whether they contradict \
each other.

Output ONLY valid JSON (no markdown fences, no commentary):
{
  "contradicts": true | false,
  "reasoning": "<brief explanation>"
}\
"""

CONTRADICTION_CHECK_USER = """\
Reflection A:
{reflection_a}

Reflection B:
{reflection_b}

Do these reflections contradict each other?\
"""
