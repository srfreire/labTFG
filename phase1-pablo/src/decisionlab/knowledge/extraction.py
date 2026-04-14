"""Core extraction logic: dispatches to stage-specific prompts, calls Haiku, parses JSON."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 8192

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
    the structured JSON response. If Haiku returns malformed JSON, retries once.
    On second failure, returns a partial result with whatever data was parseable.
    """
    if stage not in _STAGE_PROMPTS:
        raise ValueError(f"Unknown stage: {stage!r}. Expected one of {list(_STAGE_PROMPTS)}")

    system_prompt, user_template = _STAGE_PROMPTS[stage]
    user_message = user_template.replace("{text}", output_text)

    raw_json = await _call_haiku(client, system_prompt, user_message)
    parsed = _try_parse_json(raw_json)

    if parsed is None:
        logger.warning("Malformed JSON from Haiku for stage %r, retrying once", stage)
        raw_json = await _call_haiku(client, system_prompt, user_message)
        parsed = _try_parse_json(raw_json)

        if parsed is None:
            logger.warning("Retry also failed for stage %r, returning empty result", stage)
            return ExtractionResult(nodes=[], relations=[], facts=[], stage=stage, run_id=run_id)

    return _build_result(parsed, stage, run_id)


async def _call_haiku(
    client: AsyncAnthropic,
    system_prompt: str,
    user_message: str,
) -> str:
    """Make a single Haiku API call and return the text response."""
    response = await client.messages.create(
        model=_HAIKU_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
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
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    return data


def _build_result(data: dict, stage: str, run_id: str) -> ExtractionResult:
    """Convert parsed JSON dict into an ExtractionResult with validated fields."""
    nodes = []
    for raw in data.get("nodes", []):
        if not isinstance(raw, dict):
            continue
        label = raw.get("label")
        properties = raw.get("properties")
        natural_key = raw.get("natural_key")
        if label and isinstance(properties, dict) and natural_key:
            nodes.append(NodeSpec(label=str(label), properties=properties, natural_key=str(natural_key)))

    relations = []
    for raw in data.get("relations", []):
        if not isinstance(raw, dict):
            continue
        required = ("from_label", "from_key_value", "to_label", "to_key_value", "rel_type")
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
