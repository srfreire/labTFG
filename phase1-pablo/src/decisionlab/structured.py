"""Sonnet 4.6 + Pydantic structured-output wrapper.

Single entry point ``call_structured`` that constrains the model's output
to a Pydantic schema via Anthropic forced tool-use, then validates the
returned tool input through Pydantic. Raises ``StructuredOutputError`` on
schema violation rather than silently falling back to a default — that
silent fallback is what made ``_score_importance`` log
``Importance scoring failed — defaulting all facts to 5.0`` on every topic
of the cumulative-growth eval.

Why forced tool-use instead of Anthropic's native ``output_format``: the
project routes the Anthropic SDK through OpenRouter
(``ANTHROPIC_BASE_URL=https://openrouter.ai/api``). OpenRouter mediates
the request and reliably honours forced tool-use across every model in
its catalogue, while ``output_format`` is a newer Anthropic-direct
feature whose pass-through behaviour is provider-specific. Forced
tool-use produces the same grammar-level guarantee in practice — the
model cannot emit a tool_use block that doesn't match the input_schema.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ValidationError

from decisionlab.runtime.usage import record as record_usage

logger = logging.getLogger(__name__)

# Default model for every structured call introduced by the research-memory
# rewrite — see plan decision (1): "anthropic/claude-sonnet-4.6 for every
# LLM call". Keep this overridable per call so tests can stub it.
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


class StructuredOutputError(RuntimeError):
    """Raised when the model's response cannot be coerced to the target schema.

    Carries the raw model response for diagnosis. Never caught silently —
    the whole point of structured outputs is to surface these cases.
    """

    def __init__(self, message: str, *, raw: object | None = None) -> None:
        super().__init__(message)
        self.raw = raw


def _schema_for(schema: type[BaseModel]) -> dict:
    """Return a JSON schema dict suitable for an Anthropic tool input_schema.

    Strips Pydantic-specific keys Anthropic's tool schema rejects (e.g.
    ``$defs`` is allowed but ``additionalProperties`` placement matters).
    """
    raw = schema.model_json_schema()
    raw.setdefault("type", "object")
    return raw


async def call_structured[T: BaseModel](
    *,
    client,
    messages: list[dict],
    system: str,
    schema: type[T],
    max_tokens: int = 4096,
    model: str = DEFAULT_MODEL,
    extra_system: str | None = None,
) -> T:
    """Run a single Sonnet 4.6 call constrained to *schema*.

    The model is forced to emit exactly one ``tool_use`` block whose input
    matches the ``schema``. The tool's name is ``emit_<schema_class_name>``
    purely for traceability in logs; the tool itself is a no-op carrier
    for the JSON payload.

    Raises ``StructuredOutputError`` if:
      - the response contains no tool_use block,
      - the tool input is unparseable, or
      - Pydantic validation fails.
    """
    tool_name = f"emit_{schema.__name__}"
    tool = {
        "name": tool_name,
        "description": (
            f"Return the response as a {schema.__name__} object matching the "
            f"input_schema. Always call this tool exactly once."
        ),
        "input_schema": _schema_for(schema),
    }
    sys_prompt = system if extra_system is None else f"{system}\n\n{extra_system}"

    # Mirror runtime.loop's streaming threshold: above ~24k tokens the SDK
    # rejects non-streaming requests (10-minute estimated-runtime guard).
    # extraction.py runs at 32k for Researcher outputs and trips this.
    if max_tokens >= 24000:
        async with client.messages.stream(
            model=model,
            system=sys_prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=messages,
            max_tokens=max_tokens,
        ) as stream:
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=model,
            system=sys_prompt,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=messages,
            max_tokens=max_tokens,
        )
    record_usage(model, getattr(response, "usage", None))

    if getattr(response, "stop_reason", None) == "max_tokens":
        usage = getattr(response, "usage", None)
        out_tokens = getattr(usage, "output_tokens", None) if usage else None
        raise StructuredOutputError(
            f"call_structured truncated at max_tokens={max_tokens} "
            f"(output_tokens={out_tokens}); raise max_tokens or split the call",
            raw=response,
        )

    blocks = getattr(response, "content", []) or []
    tool_inputs = [
        b.input
        for b in blocks
        if getattr(b, "type", None) == "tool_use" and b.name == tool_name
    ]
    if not tool_inputs:
        raise StructuredOutputError(
            f"call_structured: no tool_use block named {tool_name!r} in response "
            f"(stop_reason={getattr(response, 'stop_reason', '?')!r})",
            raw=response,
        )

    payload = tool_inputs[0]
    # Tool inputs come back as already-parsed dicts on the Anthropic SDK,
    # but defensively re-parse if a string slips through (e.g. some
    # OpenRouter-mediated responses serialize tool input as JSON string).
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                f"call_structured: tool input is not valid JSON: {exc}",
                raw=payload,
            ) from exc

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"call_structured: Pydantic validation failed for {schema.__name__}: {exc}",
            raw=payload,
        ) from exc
