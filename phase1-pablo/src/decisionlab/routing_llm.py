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
You classify user feedback about a decision-making model into the pipeline agent that must re-execute.

Agents (from low-level to high-level):
- "builder": code-level problem. The Python implementation has a bug, crash, import error, type error, or test failure. The spec is correct but the code doesn't match it.
- "reasoner": spec-level problem. The JSON specification has a wrong decision rule, incorrect pseudocode, bad environment mapping, or missing action. The math is correct but the translation to spec is wrong.
- "formalizer": math-level problem. The mathematical formulation has wrong equations, missing variables, incorrect differential equations, or a flawed mathematical model. The underlying theory is correct but the math is wrong.
- "researcher": theory-level problem. The paradigm research is incomplete, cites wrong authors, misses key theories, or has incorrect foundational postulates.

Pick the LOWEST-level agent that can fix the problem. If the code crashes, that's "builder" even if the spec also looks wrong.

The "paradigm" field MUST be one of the slugs listed in the user message.

Respond with ONLY a JSON object (no markdown, no explanation outside JSON):
{"target": "...", "paradigm": "...", "reason": "..."}

## Examples

User feedback: "The model throws a TypeError because decide() returns a string instead of an Action object"
{"target": "builder", "paradigm": "homeostatic-regulation", "reason": "Return type bug in decide() implementation"}

User feedback: "The spec says the agent should move away from food when hungry, but it should move toward food"
{"target": "reasoner", "paradigm": "homeostatic-regulation", "reason": "Decision rule in spec has inverted direction"}

User feedback: "The drive function uses a linear equation but should be exponential decay"
{"target": "formalizer", "paradigm": "homeostatic-regulation", "reason": "Wrong functional form in drive equation"}

User feedback: "The research completely misses allostasis, only covers classic homeostasis"
{"target": "researcher", "paradigm": "homeostatic-regulation", "reason": "Missing key theory branch in research"}
"""


def _build_user_message(
    feedback: str,
    paradigms: list[str],
    spec_content: str | None,
    build_output: str | None,
) -> str:
    parts: list[str] = []

    parts.append(f"## Paradigms in this run (use EXACTLY one of these as \"paradigm\")\n{', '.join(paradigms)}")

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
            paradigm_value = data["paradigm"]
            if paradigms and paradigm_value not in paradigms:
                raise ValueError(
                    f"Invalid paradigm '{paradigm_value}', expected one of {paradigms}"
                )
            return RerunRequest(
                target=target,
                paradigm=paradigm_value,
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
