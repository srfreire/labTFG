"""LLM-based feedback classifier for pipeline re-routing."""

from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic

from decisionlab.domain.models import RerunRequest

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 256

CLASSIFIER_SYSTEM_PROMPT = """\
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
"""


def _build_user_message(
    feedback: str,
    paradigms: list[str],
    spec_content: str | None,
    build_output: str | None,
) -> str:
    parts: list[str] = []

    parts.append(f"## Paradigms in this run\n{', '.join(paradigms)}")

    if spec_content:
        parts.append(f"## Reasoner spec\n{spec_content}")

    if build_output:
        parts.append(f"## Builder output / errors\n{build_output}")

    parts.append(f"## User feedback\n{feedback}")

    return "\n\n".join(parts)


async def classify_feedback(
    client: AsyncAnthropic,
    feedback: str,
    paradigms: list[str],
    spec_content: str | None = None,
    build_output: str | None = None,
) -> RerunRequest:
    """Classify free-form user feedback to determine which agent must re-execute.

    Uses Claude Haiku to parse the feedback and map it to a pipeline target.
    Retries once on JSON parse failure before raising.
    """
    user_message = _build_user_message(feedback, paradigms, spec_content, build_output)

    for attempt in range(2):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = "\n".join(b.text for b in response.content if b.type == "text").strip()
        # Strip markdown code fences if present (```json ... ```)
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
        cleaned = fence_match.group(1).strip() if fence_match else raw

        try:
            data = json.loads(cleaned)
            target = data["target"]
            _VALID_TARGETS = {"researcher", "formalizer", "reasoner", "builder"}
            if target not in _VALID_TARGETS:
                raise ValueError(f"Invalid target '{target}', expected one of {_VALID_TARGETS}")
            return RerunRequest(
                target=target,
                paradigm=data["paradigm"],
                feedback=feedback,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            if attempt == 0:
                logger.warning(
                    "classify_feedback: JSON parse failed on attempt 1, retrying. raw=%r exc=%s",
                    raw,
                    exc,
                )
                continue
            raise ValueError(
                f"classify_feedback: could not parse Haiku response after 2 attempts. raw={raw!r}"
            ) from exc

    # Unreachable, but satisfies type checker
    raise RuntimeError("classify_feedback: unexpected exit from retry loop")
