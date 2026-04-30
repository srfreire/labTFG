"""Core extraction logic: dispatches to stage-specific prompts, calls Haiku, parses JSON."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from decisionlab.config import SETTINGS
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
from decisionlab.runtime.usage import record as record_usage

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_FAST_MODEL = SETTINGS.knowledge_fast_model
_MAX_TOKENS = 32768

_STAGE_PROMPTS: dict[str, tuple[str, str]] = {
    "researcher": (RESEARCHER_SYSTEM, RESEARCHER_USER),
    "formalizer": (FORMALIZER_SYSTEM, FORMALIZER_USER),
    "reasoner": (REASONER_SYSTEM, REASONER_USER),
    "builder": (BUILDER_SYSTEM, BUILDER_USER),
}


async def extract(
    stage: str,
    output_text: str,
    run_id: str,
    client: AsyncAnthropic,
) -> ExtractionResult:
    """Extract entities, relations, and facts from a pipeline stage's output.

    Dispatches to the appropriate stage-specific prompt, calls Haiku, and parses
    the structured JSON response. Retries once on a JSON parse failure; raises
    if both attempts produce unparseable output. Output truncation
    (``stop_reason="max_tokens"``) is also raised — see ``_call_haiku``.
    """
    if stage not in _STAGE_PROMPTS:
        raise ValueError(
            f"Unknown stage: {stage!r}. Expected one of {list(_STAGE_PROMPTS)}"
        )

    system_prompt, user_template = _STAGE_PROMPTS[stage]
    user_message = user_template.replace("{text}", output_text)

    raw_json = await _call_haiku(client, system_prompt, user_message)
    parsed = _try_parse_json(raw_json)

    if parsed is None:
        logger.warning("Malformed JSON from Haiku for stage %r, retrying once", stage)
        raw_json = await _call_haiku(client, system_prompt, user_message)
        parsed = _try_parse_json(raw_json)

        if parsed is None:
            raise RuntimeError(
                f"Haiku returned unparseable JSON for stage {stage!r} on both attempts"
            )

    return _build_result(parsed, stage, run_id)


async def _call_haiku(
    client: AsyncAnthropic,
    system_prompt: str,
    user_message: str,
) -> str:
    """Make a single Haiku API call and return the text response.

    Uses the streaming API because the SDK requires streaming for any request
    whose ``max_tokens`` could exceed the 10-minute non-streaming timeout.
    """
    async with client.messages.stream(
        model=_FAST_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = await stream.get_final_message()

    record_usage(_FAST_MODEL, getattr(response, "usage", None))

    if getattr(response, "stop_reason", None) == "max_tokens":
        usage = getattr(response, "usage", None)
        out_tokens = getattr(usage, "output_tokens", None) if usage else None
        raise RuntimeError(
            f"Haiku output truncated at max_tokens={_MAX_TOKENS} "
            f"(output_tokens={out_tokens}); raise _MAX_TOKENS or chunk the input"
        )

    if not response.content:
        logger.warning("Haiku returned empty content list")
        return ""
    return response.content[0].text


def _try_parse_json(text: str) -> dict | None:
    """Attempt to parse JSON from the LLM response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` fences
        lines = cleaned.split("\n")
        # Drop first line (```json) and last line (```)
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    return data


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
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = raw.get("label")
        properties = raw.get("properties")
        natural_key = raw.get("natural_key")
        if label and isinstance(properties, dict) and natural_key:
            nodes.append(
                NodeSpec(
                    label=str(label),
                    properties=properties,
                    natural_key=str(natural_key),
                )
            )

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
