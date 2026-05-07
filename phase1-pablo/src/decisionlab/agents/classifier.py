"""Umbrella classifier — picks the canonical paradigm an problem belongs under.

Phase C's enum-constrained Researcher emission only works when the
canonical umbrella (e.g. ``reinforcement-learning``) is already in the KG.
The 2026-05-07 paradigm-canonicalization eval showed the failure mode: the
first run minted variant slugs (``q-learning-td-action-value``,
``td-rl-foraging``) and subsequent runs retrieved those variants as
candidates, never accumulating the umbrella. This classifier pre-anchors
the Researcher to a canonical paradigm before any extraction happens, so
the final emission collapses to the umbrella's slug rather than a variant.

Single Haiku call routed through ``call_structured`` so the model
literally cannot return a slug outside the known set or the explicit
``__NEW__`` sentinel.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from decisionlab.config import SETTINGS
from decisionlab.structured import call_structured

logger = logging.getLogger(__name__)


class UmbrellaDecision(BaseModel):
    """Classifier output — which canonical umbrella a problem belongs under."""

    chosen_slug: str = Field(
        description=(
            "One of the known umbrella slugs, OR '__NEW__' when no umbrella fits."
        ),
    )
    chosen_name: str = Field(description="Human-readable name of the chosen umbrella.")
    definition: str = Field(description="One-sentence definition of the umbrella.")
    rationale: str = Field(
        description="One sentence explaining why THIS umbrella vs adjacent ones."
    )
    confidence: float = Field(ge=0.0, le=1.0)


_CLASSIFIER_SYSTEM = """\
You classify a decision-making problem under the broadest established \
paradigm that explains it. Given a list of known umbrella paradigms with \
definitions, pick the slug whose mechanism best subsumes the problem.

Rules:
- PREFER the BROADEST matching umbrella. If reinforcement-learning fits, \
choose it over q-learning or temporal-difference-learning — variants are \
discussed inside research, not as separate umbrellas.
- Choose ``__NEW__`` ONLY when the problem genuinely doesn't fit any known \
umbrella — e.g. a paradigm not in mainstream decision-making literature, \
or one where the mechanism is fundamentally distinct.
- ``rationale`` should be one sentence naming the mechanism that decided \
the call (e.g. "uses noisy evidence accumulation to a bound" → \
drift-diffusion-model).
- ``confidence`` reflects how cleanly the problem maps to the umbrella's \
mechanism: 0.9+ for textbook fits, 0.6-0.8 when adjacent umbrellas could \
also apply, below 0.5 leans toward __NEW__.
"""


def _build_decision_model(known_slugs: list[str]) -> type[BaseModel]:
    """Build a copy of ``UmbrellaDecision`` whose ``chosen_slug`` is enum-constrained.

    The Literal is constructed at request time from ``known_slugs + ["__NEW__"]``,
    so the LLM cannot emit a slug outside the canonical set or the explicit
    novelty sentinel.
    """
    enum_values = [*known_slugs, "__NEW__"]
    SlugEnum = Literal[tuple(enum_values)]  # type: ignore[valid-type]

    class _UmbrellaDecisionConstrained(BaseModel):
        chosen_slug: SlugEnum  # type: ignore[valid-type]
        chosen_name: str
        definition: str
        rationale: str
        confidence: float = Field(ge=0.0, le=1.0)

    _UmbrellaDecisionConstrained.__name__ = "UmbrellaDecision"
    return _UmbrellaDecisionConstrained


def _format_known(known_umbrellas: list[dict]) -> str:
    if not known_umbrellas:
        return "(no canonical umbrellas registered — every problem is __NEW__)"
    lines = []
    for u in known_umbrellas:
        slug = u["slug"]
        name = u.get("name", slug)
        definition = u.get("definition", "")
        lines.append(f"- **{slug}** — {name}: {definition}")
    return "\n".join(lines)


async def classify_umbrella(
    problem: str,
    *,
    client,
    known_umbrellas: list[dict],
) -> UmbrellaDecision:
    """Pick the broadest canonical paradigm for a problem.

    ``known_umbrellas`` is the list of canonical paradigms (each a dict
    with ``slug``, ``name``, ``definition``). When the list is empty, every
    problem returns ``__NEW__`` — the system degrades to discovery-driven
    behaviour rather than failing.
    """
    DecisionModel = _build_decision_model([u["slug"] for u in known_umbrellas])
    user = (
        f"Problem:\n{problem}\n\n"
        f"Known umbrella paradigms:\n{_format_known(known_umbrellas)}\n\n"
        "Pick the broadest umbrella whose mechanism explains the problem. "
        "Use '__NEW__' only when no umbrella fits."
    )
    decision = await call_structured(
        client=client,
        messages=[{"role": "user", "content": user}],
        system=_CLASSIFIER_SYSTEM,
        schema=DecisionModel,
        max_tokens=1024,
        model=SETTINGS.knowledge_fast_model,
    )
    logger.info(
        "Umbrella classified: slug=%s confidence=%.2f rationale=%s",
        decision.chosen_slug,
        decision.confidence,
        decision.rationale,
    )
    return UmbrellaDecision(**decision.model_dump())
