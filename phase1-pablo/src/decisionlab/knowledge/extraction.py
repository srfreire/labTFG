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
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.knowledge.prompts import (
    BUILDER_SYSTEM,
    BUILDER_USER,
    FORMALIZER_SYSTEM,
    FORMALIZER_USER,
    REASONER_SYSTEM,
    REASONER_USER,
    RESEARCHER_SYSTEM,
    RESEARCHER_USER,
)
from decisionlab.structured import DEFAULT_MODEL as _STRUCTURED_MODEL
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


# Pydantic schemas mirror the pre-rewrite prompt JSON shape so the
# downstream ``_build_result`` parser still sees the same dict structure.
# ``properties`` is left as ``dict`` (free-form) because each node label
# carries different keys; the Pydantic root validates only the envelope.


class _NodeRaw(BaseModel):
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    natural_key: str = ""


class _RelationRaw(BaseModel):
    from_label: str
    from_key_value: str
    to_label: str
    to_key_value: str
    rel_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class _Extraction(BaseModel):
    nodes: list[_NodeRaw] = Field(default_factory=list)
    relations: list[_RelationRaw] = Field(default_factory=list)
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
        model=_STRUCTURED_MODEL,
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


_PARTIAL_UUID_RE = re.compile(r"^[0-9a-f]{4,}-[0-9a-f]{4,}", re.IGNORECASE)


def _is_garbage_paradigm_slug(slug: str) -> bool:
    """Reject paradigm slugs that obviously aren't paradigms.

    Catches the residue the prompt can't fully prevent: partial UUID/hash
    fragments (e.g. ``b47e-b402d07b1163``) and short single-word stubs that
    are almost always extraction noise rather than named theories. The
    prompt itself filters the rest (aspects, adjectives, web chrome).
    """
    if not isinstance(slug, str) or not slug:
        return True
    if len(slug) >= 12 and _PARTIAL_UUID_RE.match(slug):
        return True
    return "-" not in slug and len(slug) <= 4


def _build_result(data: dict, stage: str, run_id: str) -> ExtractionResult:
    """Convert parsed JSON dict into an ExtractionResult with validated fields."""
    raw_nodes = _fold_legacy_test_results(data.get("nodes", []))
    nodes = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = raw.get("label")
        properties = raw.get("properties")
        natural_key = raw.get("natural_key")
        if label and isinstance(properties, dict) and natural_key:
            if label == "Paradigm":
                slug = properties.get("slug")
                if _is_garbage_paradigm_slug(slug if isinstance(slug, str) else ""):
                    logger.info(
                        "Dropping garbage Paradigm extraction: slug=%r name=%r",
                        slug,
                        properties.get("name"),
                    )
                    continue
            nodes.append(
                NodeSpec(
                    label=str(label),
                    properties=properties,
                    natural_key=str(natural_key),
                )
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
