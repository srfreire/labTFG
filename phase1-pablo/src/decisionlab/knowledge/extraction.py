"""Core extraction logic: dispatches to stage-specific prompts, calls Sonnet, parses JSON.

Switched to ``decisionlab.structured.call_structured`` (forced tool-use +
Pydantic) so a malformed model response now raises
``StructuredOutputError`` immediately. The pre-rewrite path silently
retried once and then crashed, which on cumulative-growth t1 voided the
whole topic without any actionable signal in the trace.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from decisionlab.config import SETTINGS
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.knowledge.prompts import (
    _CANONICAL,
    BUILDER_SYSTEM,
    BUILDER_USER,
    FORMALIZER_SYSTEM,
    FORMALIZER_USER,
    REASONER_SYSTEM,
    REASONER_USER,
    RESEARCHER_SYSTEM,
    RESEARCHER_USER,
)
from decisionlab.structured import call_structured

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_MAX_TOKENS = 32768

_STAGE_PROMPTS: dict[str, tuple[str, str]] = {
    "researcher": (RESEARCHER_SYSTEM, RESEARCHER_USER),
    "formalizer": (FORMALIZER_SYSTEM, FORMALIZER_USER),
    "reasoner": (REASONER_SYSTEM, REASONER_USER),
    "builder": (BUILDER_SYSTEM, BUILDER_USER),
}

# Per-stage extraction model tiering. Judgment-heavy stages (Researcher
# filters paradigm slugs across nested entities; Reasoner walks
# DERIVES_FROM chains) get the structured Sonnet slot; mechanical stages
# (Formalizer pulls from rigid tables, Builder extracts a single Model
# node) get the fast Haiku slot. Replaces a blanket Sonnet default that
# was 10× more expensive than the architecture doc claimed — see
# docs/specs/memory-refactor/phase-0-stop-lying.md §R1.
_STAGE_MODELS: dict[str, str] = {
    "researcher": SETTINGS.knowledge_structured_model,
    "formalizer": SETTINGS.knowledge_fast_model,
    "reasoner": SETTINGS.knowledge_structured_model,
    "builder": SETTINGS.knowledge_fast_model,
}


# Pydantic schemas mirror the pre-rewrite prompt JSON shape so the
# downstream ``_build_result`` parser still sees the same dict structure.
# ``properties`` stays ``dict[str, Any]`` on the wire, but slug-bearing
# labels (Paradigm/Variable/Postulate) get a typed sub-validator dispatched
# by ``_NodeRaw``'s ``model_validator`` — malformed slugs raise
# ``ValidationError`` (which ``call_structured`` translates to
# ``StructuredOutputError``). This is the gate that keeps minted-variant
# slugs like ``q-eligibility-traces`` out of the KG.

# Build the canonical-slug Literal at module import. ``Literal[tuple]``
# unpacks the tuple into the literal's args at runtime — Pydantic still
# validates membership the same way as a hand-written
# ``Literal["a", "b", ...]``. ``__NEW__`` is the LLM's "doesn't fit any of
# these" escape; routed through ``_verify_merge`` later by P1-003.
_CANONICAL_SLUGS: tuple[str, ...] = (
    *(p["slug"] for p in _CANONICAL),
    "__NEW__",
)
ParadigmSlug = Literal[_CANONICAL_SLUGS]  # type: ignore[valid-type]

# Postulate ids are scoped by their parent paradigm slug to prevent
# cross-paradigm collisions (e.g. RL's "P1" colliding with Prospect
# Theory's "P1"). The regex tolerates the ``__NEW__`` escape so that an
# extraction for an unknown paradigm still parses — P1-003 routes such
# extractions through ``_verify_merge`` to mint or reuse a slug before
# they reach the KG.
_POSTULATE_ID_RE = re.compile(r"^(__NEW__|[a-z0-9-]+):P\d+$")


class _ParadigmProps(BaseModel):
    slug: ParadigmSlug  # type: ignore[valid-type]
    name: str
    description: str = ""


class _VariableProps(BaseModel):
    name: str
    paradigm_slug: ParadigmSlug  # type: ignore[valid-type]
    description: str = ""
    type: str | None = None
    range: str | None = None
    unit: str | None = None


class _PostulateProps(BaseModel):
    id: str
    statement: str
    falsifiable: bool
    paradigm_slug: ParadigmSlug  # type: ignore[valid-type]

    @field_validator("id")
    @classmethod
    def _validate_id_prefix(cls, v: str) -> str:
        # Two gates: regex enforces shape (kebab + the ``__NEW__`` escape);
        # membership check enforces canonical-set vocabulary so
        # ``valid-shape-but-fabricated:P1`` is caught.
        m = _POSTULATE_ID_RE.match(v)
        if m is None:
            raise ValueError(
                f"Postulate.id must match '<paradigm-slug>:P<num>'; got {v!r}"
            )
        prefix = m.group(1)
        if prefix not in _CANONICAL_SLUGS:
            raise ValueError(
                f"Postulate.id prefix {prefix!r} is not a canonical paradigm slug"
            )
        return v


_LABEL_TO_PROPS: dict[str, type[BaseModel]] = {
    "Paradigm": _ParadigmProps,
    "Variable": _VariableProps,
    "Postulate": _PostulateProps,
}


class _Extraction(BaseModel):
    """Permissive envelope: nodes/relations stay as raw dicts so the LLM
    emitting one bad slug among many valid nodes doesn't void the whole
    batch. Per-label validation (``_LABEL_TO_PROPS``) is applied per-node
    in ``_build_result``, where invalid items are logged and skipped.
    """

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)


async def extract(
    stage: str,
    output_text: str,
    run_id: str,
    client: AsyncAnthropic,
) -> ExtractionResult:
    """Extract entities, relations, and facts from a pipeline stage's output.

    Uses ``call_structured`` so the model is forced to emit JSON matching
    ``_Extraction``. Schema violation raises ``StructuredOutputError`` —
    callers decide whether to skip the stage or surface the failure.
    """
    if stage not in _STAGE_PROMPTS:
        raise ValueError(
            f"Unknown stage: {stage!r}. Expected one of {list(_STAGE_PROMPTS)}"
        )

    system_prompt, user_template = _STAGE_PROMPTS[stage]
    user_message = user_template.replace("{text}", output_text)

    parsed = await call_structured(
        client=client,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
        schema=_Extraction,
        max_tokens=_MAX_TOKENS,
        model=_STAGE_MODELS[stage],
    )
    return _build_result(parsed.model_dump(), stage, run_id)


_TEST_RESULT_PROPS = ("passed", "failure_reason")
_MISSING = object()


def _fold_legacy_test_results(raw_nodes: list) -> list:
    """Drop legacy ``TestResult`` nodes, merging their test props into matching Model nodes.

    Older Builder extractions emitted ``TestResult`` as a separate node. The current
    schema carries ``passed`` / ``failure_reason`` directly on ``Model``. This keeps
    old-format extractions usable: test props are copied onto the Model with the same
    ``formulation_id`` (when one exists), and the TestResult entry is discarded.
    """
    test_props_by_fid: dict[str, dict] = {}
    survivors: list = []
    for raw in raw_nodes:
        if isinstance(raw, dict) and raw.get("label") == "TestResult":
            properties = raw.get("properties")
            if isinstance(properties, dict):
                fid = properties.get("formulation_id")
                if fid is not None:
                    test_props_by_fid[str(fid)] = {
                        k: properties[k] for k in _TEST_RESULT_PROPS if k in properties
                    }
            continue
        survivors.append(raw)

    if not test_props_by_fid:
        return survivors

    matched_fids: set[str] = set()
    for raw in survivors:
        if not isinstance(raw, dict) or raw.get("label") != "Model":
            continue
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            continue
        fid = properties.get("formulation_id")
        if fid is None:
            continue
        fid_key = str(fid)
        fold = test_props_by_fid.get(fid_key)
        if not fold:
            continue
        matched_fids.add(fid_key)
        for prop_key, value in fold.items():
            existing = properties.get(prop_key, _MISSING)
            if existing is _MISSING:
                properties[prop_key] = value
            elif existing != value:
                logger.warning(
                    "Legacy TestResult conflicts with Model on formulation_id=%r "
                    "property=%r: keeping Model value %r (discarding %r)",
                    fid_key,
                    prop_key,
                    existing,
                    value,
                )

    orphans = set(test_props_by_fid) - matched_fids
    if orphans:
        logger.warning(
            "Legacy TestResult nodes without matching Model discarded for "
            "formulation_ids=%s",
            sorted(orphans),
        )
    return survivors


def _build_result(data: dict, stage: str, run_id: str) -> ExtractionResult:
    """Convert parsed JSON dict into an ExtractionResult with validated fields."""
    raw_nodes = _fold_legacy_test_results(data.get("nodes", []))
    nodes = []
    n_dropped_invalid = 0
    drop_reasons: list[str] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = raw.get("label")
        properties = raw.get("properties")
        natural_key = raw.get("natural_key")
        if not (label and isinstance(properties, dict) and natural_key):
            continue

        # Per-label property validation. Slug-bearing labels enforce the
        # canonical Literal here so a single bad node is dropped instead
        # of failing the whole list at parse time (see _Extraction).
        sub_model = _LABEL_TO_PROPS.get(str(label))
        if sub_model is not None:
            try:
                sub_model.model_validate(properties)
            except ValidationError as exc:
                n_dropped_invalid += 1
                drop_reasons.append(
                    f"{label}({properties.get('slug') or properties.get('name') or '?'}): "
                    f"{exc.error_count()} field error(s)"
                )
                continue

        nodes.append(
            NodeSpec(
                label=str(label),
                properties=properties,
                natural_key=str(natural_key),
            )
        )

    if n_dropped_invalid:
        logger.warning(
            "extract[%s]: dropped %d/%d nodes failing per-label validation: %s",
            stage,
            n_dropped_invalid,
            len(raw_nodes),
            "; ".join(drop_reasons[:5]) + (" ..." if len(drop_reasons) > 5 else ""),
        )

    # Defensive: if the LLM emitted a Paradigm in this batch, fill any missing
    # paradigm_slug on Variable nodes from it. Prevents Variables from silently
    # falling into the orphan namespace when the LLM forgets to copy the slug
    # down (which it does despite the prompt telling it to).
    paradigm_slug = next(
        (
            n.properties.get("slug")
            for n in nodes
            if n.label == "Paradigm" and isinstance(n.properties.get("slug"), str)
        ),
        None,
    )
    if paradigm_slug:
        for n in nodes:
            if n.label == "Variable" and not n.properties.get("paradigm_slug"):
                n.properties["paradigm_slug"] = paradigm_slug

    relations = []
    for raw in data.get("relations", []):
        if not isinstance(raw, dict):
            continue
        required = (
            "from_label",
            "from_key_value",
            "to_label",
            "to_key_value",
            "rel_type",
        )
        if all(raw.get(k) for k in required):
            relations.append(
                RelationSpec(
                    from_label=str(raw["from_label"]),
                    from_key_value=str(raw["from_key_value"]),
                    to_label=str(raw["to_label"]),
                    to_key_value=str(raw["to_key_value"]),
                    rel_type=str(raw["rel_type"]),
                    properties=raw.get("properties", {}),
                )
            )

    facts = []
    for raw in data.get("facts", []):
        if isinstance(raw, str) and raw.strip():
            facts.append(raw.strip())

    return ExtractionResult(
        nodes=nodes,
        relations=relations,
        facts=facts,
        stage=stage,
        run_id=run_id,
    )
