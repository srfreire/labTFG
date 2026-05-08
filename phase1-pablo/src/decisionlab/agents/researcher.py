"""Researcher agent — gap-fill discovery with enum-constrained slugs.

The pre-rewrite Researcher invented paradigm slugs freely
(``q-learning``, ``optimal-foraging-theory``) when the canonical umbrella
(``reinforcement-learning``) was already in the KG, so retrieval-based
assertions like ``paradigm: reinforcement-learning`` failed on every
topic that overlapped with prior runs. Phase C of the research-memory
rewrite replaces that with a three-step pipeline:

1. **Retrieve known paradigms** — mandatory ``retrieve_knowledge`` call
   against the topic, scoped to ``namespace=paradigm``. The result —
   top-K candidate slugs — becomes the enum the Researcher's final
   emission is restricted to.
2. **Discover** — the existing agent loop (web_search +
   launch_deep_research + read_report) runs as before, biased by the
   retrieved candidates so the model can confirm hits and only research
   genuine gaps.
3. **Emit structured** — ``call_structured`` with a Pydantic schema
   whose ``slug`` field is ``Literal[<known-slugs>, "__NEW__"]``. The
   model literally cannot return a slug outside the candidate set or
   the explicit "I'm proposing a new one" sentinel.

If ``retrieve_knowledge`` is unavailable (degraded mode, no KG) the
Researcher falls back to "every emitted slug is __NEW__" — equivalent
to the pre-rewrite free-form behaviour but explicitly marked rather
than silently fragmenting the registry.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from decisionlab.agents.classifier import UmbrellaDecision
from decisionlab.agents.deep_researcher import DeepResearcher
from decisionlab.config import SETTINGS
from decisionlab.domain.models import Paradigm, ResearchReport
from decisionlab.domain.ports import WebSearchPort
from decisionlab.runtime.loop import run_agent_loop
from decisionlab.structured import DEFAULT_MODEL as _STRUCTURED_MODEL
from decisionlab.structured import StructuredOutputError, call_structured
from decisionlab.tools.agents import (
    LAUNCH_DEEP_RESEARCH_SCHEMA,
    create_launch_deep_research,
)
from decisionlab.knowledge.retrieval.tool import list_known_slugs
from decisionlab.tools.reports import (
    READ_REPORT_SCHEMA,
    create_read_report,
    save_summary_report,
    slugify,
)
from decisionlab.tools.search import WEB_SEARCH_SCHEMA, create_web_search

logger = logging.getLogger(__name__)

# How many candidate paradigms to surface to the Researcher up front.
_RETRIEVAL_TOP_K = 8


RESEARCHER_SYSTEM_PROMPT = """\
You discover decision-making paradigms for a given problem.

Each paradigm you find will later be mathematically formalized and implemented as an \
autonomous agent in a grid-based simulation. Only select paradigms that have quantifiable \
variables, causal mechanisms, and can plausibly drive an agent's action selection.

## Process

1. The user message lists CANDIDATE paradigms already in the knowledge backbone, with \
their slugs and definitions. Treat these as authoritative — if a candidate plausibly \
explains the problem, REUSE its slug. Do not invent a new slug for a paradigm that is \
already represented.
2. If the candidates do not adequately cover the problem, run 1-2 web searches and \
launch deep research on the GENUINE GAPS only.
3. Call `launch_deep_research` ONCE per gap paradigm. Each call returns a concise summary.
4. After deep research returns, STOP searching.
5. Use `read_report` on every paradigm you researched to read the full deep reports. \
Extract the `## References` section and the `## Primary Locus` section from each one.
6. Write your final summary including a `## Cross-paradigm interaction map` and a \
consolidated `## References` section at the end.

## Constraints

- Maximum 3 web searches total.
- You may call `retrieve_knowledge` AT MOST 2 TIMES TOTAL across the whole run. \
Use it ONLY to look up the definition of a CANDIDATE paradigm listed in the user \
message when the candidate is loosely related to the topic and you need its \
definition to decide whether to reuse its slug. DO NOT use `retrieve_knowledge` \
as a free-form search tool — `web_search` is for that.
- After iteration 5, no more search or retrieval calls (no `web_search`, no \
`retrieve_knowledge`, no `launch_deep_research`). Iterations 6+ are reserved for \
synthesis: `read_report`, prose writing, and the final summary.
- Only cite authors/papers found in results. Never fabricate.
- Discard paradigms that are purely philosophical or lack quantifiable variables.

## Output format (follow exactly)

# Decision-making paradigms: {problem}

## 1. {Paradigm name}
{One-line description}
**Key authors**: {from search results}
**Key concepts**: {list}

## 2. {Paradigm name}
...

## Cross-paradigm interaction map

{Build a matrix table from the `## Primary Locus` sections of all deep reports. \
Collect every distinct brain region / neural substrate mentioned across ALL paradigms \
and use them as columns. Each row is a paradigm. Mark ✓ if the region is relevant \
to that paradigm (mentioned in its Primary Locus), ✗ otherwise.}

| Paradigm | {Region 1} | {Region 2} | {Region 3} | ... |
|----------|:---:|:---:|:---:|:---:|
| {Paradigm 1} | ✓ | ✗ | ✓ | ... |
| {Paradigm 2} | ✗ | ✓ | ✗ | ... |

## References
{Consolidated list of ALL papers cited across ALL deep reports, deduplicated. \
If the same paper appears in multiple deep reports, list it only once. Format each entry as:}
- {Author (Year)} - {Title} — DOI: {doi}
{Omit the DOI part if not available. Sort alphabetically by first author surname.}
"""


_EMISSION_SYSTEM_PROMPT = """\
You emit the final structured paradigm list for a research run.

You are given:
- the original problem description,
- the candidate paradigms retrieved from the knowledge backbone (slug + definition),
- the Researcher's full prose summary including which paradigms were investigated.

For each distinct paradigm covered by the summary, emit one ParadigmEmission.

slug field rules:
- If the paradigm is one of the listed candidates, emit its EXACT slug.
- If the paradigm is genuinely new (no candidate covers it), emit "__NEW__" and \
provide ``slug_proposal`` as a kebab-case slug derived from the paradigm's name.
- Do NOT invent slugs outside the candidate enum. The Canonicalizer downstream will \
decide whether a "__NEW__" emission becomes a fresh node or is merged into an existing one.

Each ParadigmEmission must include:
- slug: one of the candidate slugs OR "__NEW__"
- slug_proposal: required iff slug == "__NEW__", null otherwise
- definition: 1-2 sentences capturing the paradigm's core mechanism
- rationale: why this paradigm explains the problem (cite Researcher findings)

Citations: list every paper/author mentioned in the Researcher summary's References \
section. Each Citation has author (string), year (int or null), title (string), and \
doi (string or null).
"""


class Citation(BaseModel):
    author: str
    year: int | None = None
    title: str
    doi: str | None = None


def _build_emission_model(known_slugs: list[str]) -> type[BaseModel]:
    """Build a Pydantic model whose ``slug`` field is enum-constrained.

    The literal type is constructed from ``known_slugs + ["__NEW__"]`` at
    request time, so the LLM literally cannot emit a slug outside the
    candidate set (Anthropic's tool input_schema enforces the enum and
    Pydantic rejects everything else on parse).
    """
    enum_values = [*known_slugs, "__NEW__"]
    SlugEnum = Literal[tuple(enum_values)]  # type: ignore[valid-type]

    class ParadigmEmission(BaseModel):
        slug: SlugEnum  # type: ignore[valid-type]
        slug_proposal: str | None = Field(
            default=None,
            description="Kebab-case slug for a brand-new paradigm. Required iff slug == '__NEW__'.",
        )
        definition: str
        rationale: str

    class ResearcherOutput(BaseModel):
        paradigms: list[ParadigmEmission]
        citations: list[Citation] = Field(default_factory=list)

    ResearcherOutput.__name__ = "ResearcherOutput"
    return ResearcherOutput


def _slug_from_proposal(name: str, *, definition: str = "") -> str:
    """Turn a free-form paradigm name into a kebab-case slug.

    On empty ``name``, derives a deterministic short hash from the
    definition so two unrelated paradigms with empty proposals don't
    collide on a single sentinel slug. Refuses when both are empty —
    we have no signal to disambiguate from.
    """
    s = slugify(name)
    if s:
        return s
    if not definition.strip():
        raise ValueError(
            "_slug_from_proposal: both name and definition empty; cannot mint slug"
        )
    digest = hashlib.sha1(definition.strip()[:128].encode("utf-8")).hexdigest()[:10]
    return f"unnamed-{digest}"


class Researcher:
    def __init__(
        self,
        *,
        client,
        search: WebSearchPort,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.search = search
        self.run_id = run_id

        self._deep_reports: dict[str, str] = {}

        self.tools: list[dict[str, Any]] = [
            WEB_SEARCH_SCHEMA,
            LAUNCH_DEEP_RESEARCH_SCHEMA,
        ]
        self.registry: dict[str, Callable[[dict], Awaitable[str]]] = {
            "web_search": create_web_search(search),
            "launch_deep_research": create_launch_deep_research(
                self._run_deep_research
            ),
        }

        if run_id:
            self.tools.append(READ_REPORT_SCHEMA)
            self.registry["read_report"] = create_read_report(run_id)

        self._knowledge_tool_schema = knowledge_tool_schema
        self._knowledge_tool_handler = knowledge_tool_handler
        # The agent loop also exposes retrieve_knowledge so the model can
        # follow up on candidates if it wants to (e.g. to look up the
        # definition of a candidate that's only loosely related to the
        # topic).
        if knowledge_tool_schema is not None and knowledge_tool_handler is not None:
            self.tools.append(knowledge_tool_schema)
            self.registry["retrieve_knowledge"] = knowledge_tool_handler

    async def _run_deep_research(self, paradigm: str) -> str:
        logger.info("Launching DeepResearcher for paradigm: %s", paradigm)
        dr = DeepResearcher(client=self.client, search=self.search, run_id=self.run_id)
        summary = await dr.run(paradigm)
        self._deep_reports[paradigm] = summary
        logger.info("DeepResearcher finished for: %s", paradigm)
        return summary

    async def _retrieve_known_paradigms(self, problem: str) -> tuple[list[str], str]:
        """Mandatory first step: ask the KG which paradigms it already covers.

        Returns ``(known_slugs, retrieval_text)``. ``retrieval_text`` is a
        deterministic synthetic block built from ``(slug, definition)`` pairs
        — the prompt template embeds it so the model can read full
        definitions, not just the slugs. Empty when no knowledge backbone
        is wired up.
        """
        if self._knowledge_tool_handler is None:
            logger.info(
                "Researcher: knowledge backbone unavailable — no candidate slugs"
            )
            return [], ""
        try:
            pairs = await list_known_slugs(
                query=problem, namespace="paradigm", top_k=_RETRIEVAL_TOP_K
            )
        except Exception as exc:
            logger.warning(
                "Researcher: list_known_slugs raised on %r — degrading to no candidates: %s",
                problem,
                exc,
            )
            return [], ""

        slugs = [s for s, _d in pairs]
        retrieval_text = "\n".join(
            f"- **{slug}** — {defn or '(no description)'}" for slug, defn in pairs
        )
        logger.info(
            "Researcher: retrieved %d candidate slug(s) from KG: %s",
            len(slugs),
            slugs,
        )
        return slugs, retrieval_text

    async def run(
        self,
        problem: str,
        *,
        anchor_umbrella: UmbrellaDecision | None = None,
    ) -> ResearchReport:
        self._deep_reports.clear()
        logger.info("Researcher starting — problem: %s", problem)

        known_slugs, retrieval_text = await self._retrieve_known_paradigms(problem)

        # If the upstream classifier picked a canonical umbrella, ensure its
        # slug appears in the candidate list — otherwise the enum-constrained
        # emission can't reuse it. The classifier writes the umbrella to the
        # KG as well, so future retrievals find it organically; this is just
        # belt-and-braces for the run that introduces it.
        anchor_block = _format_anchor(anchor_umbrella)
        if (
            anchor_umbrella
            and anchor_umbrella.chosen_slug != "__NEW__"
            and anchor_umbrella.chosen_slug not in known_slugs
        ):
            known_slugs = [anchor_umbrella.chosen_slug, *known_slugs]

        candidate_block = _format_candidates(known_slugs, retrieval_text)
        user_message = (
            f"Problem: {problem}\n\n"
            f"{anchor_block}"
            f"{candidate_block}\n\n"
            "Investigate the problem. Reuse candidate slugs where possible; "
            "research genuine gaps only."
        )
        messages = [{"role": "user", "content": user_message}]

        cfg = SETTINGS.researcher
        response = await run_agent_loop(
            client=self.client,
            model=cfg.model,
            system=RESEARCHER_SYSTEM_PROMPT,
            tools=self.tools,
            messages=messages,
            registry=self.registry,
            max_iterations=cfg.max_iterations,
            max_tokens=cfg.max_tokens,
        )

        summary = "\n".join(b.text for b in response.content if b.type == "text")
        if not summary.strip():
            logger.warning("Researcher produced empty summary for problem: %s", problem)

        if self.run_id:
            await save_summary_report(self.run_id, summary)

        paradigms = await self._emit_structured(
            problem=problem,
            summary=summary,
            known_slugs=known_slugs,
            retrieval_text=retrieval_text,
            anchor_umbrella=anchor_umbrella,
        )

        return ResearchReport(
            paradigms=paradigms,
            summary=summary,
            deep_reports=dict(self._deep_reports),
        )

    async def _emit_structured(
        self,
        *,
        problem: str,
        summary: str,
        known_slugs: list[str],
        retrieval_text: str,
        anchor_umbrella: UmbrellaDecision | None = None,
    ) -> list[Paradigm]:
        """Run the enum-constrained final emission.

        Falls back to slug-from-deep-report when ``call_structured`` raises
        — the prose summary is still saved to S3 so the run isn't a total
        loss. The fallback marks every slug as effectively "__NEW__" by
        running them through ``slugify``; the Canonicalizer (Phase D) is
        then responsible for merging duplicates.
        """
        ResearcherOutput = _build_emission_model(known_slugs)
        anchor_block = _format_anchor(anchor_umbrella)
        emission_user = (
            f"Problem: {problem}\n\n"
            f"{anchor_block}"
            f"Candidates already in the knowledge backbone (slug — definition):\n"
            f"{_format_candidates(known_slugs, retrieval_text)}\n\n"
            f"Researcher summary:\n{summary}\n\n"
            "Emit the structured paradigm list."
        )
        try:
            output = await call_structured(
                client=self.client,
                messages=[{"role": "user", "content": emission_user}],
                system=_EMISSION_SYSTEM_PROMPT,
                schema=ResearcherOutput,
                max_tokens=8192,
                model=_STRUCTURED_MODEL,
            )
        except (StructuredOutputError, Exception) as exc:
            # Catch broadly: schema violation (StructuredOutputError) is the
            # designed failure mode, but a network blip or auth error must
            # not lose the entire run since the prose summary is already
            # saved and the deep reports exist on S3. Fallback emits slugs
            # via slugify — the Canonicalizer (Phase D) catches any
            # accidental duplication when those slugs land in the KG.
            logger.warning(
                "Researcher: structured emission failed (%s) — falling back to "
                "deep-report slugs",
                exc,
            )
            return [
                Paradigm(id=slugify(name), name=name, description="")
                for name in self._deep_reports
            ]

        paradigms: list[Paradigm] = []
        for emission in output.paradigms:
            slug = emission.slug
            name = ""
            if slug == "__NEW__":
                proposal = emission.slug_proposal or ""
                slug = _slug_from_proposal(proposal, definition=emission.definition)
                name = proposal or slug
            else:
                # Reused canonical slug — keep the slug as the name placeholder
                # since the LLM might not echo a human-readable name.
                name = slug.replace("-", " ").title()
            paradigms.append(
                Paradigm(id=slug, name=name, description=emission.definition)
            )
        return paradigms


def _format_anchor(anchor: UmbrellaDecision | None) -> str:
    """Render the anchor-umbrella block prepended to candidate listings.

    Empty string when no anchor or the classifier returned ``__NEW__`` —
    in that case the Researcher behaves as it did pre-classifier and the
    emission falls back to discovery-driven slug minting.
    """
    if anchor is None or anchor.chosen_slug == "__NEW__":
        return ""
    return (
        "## Anchor paradigm\n"
        f"This research is anchored to: **{anchor.chosen_name}** "
        f"(slug=`{anchor.chosen_slug}`)\n"
        f"Definition: {anchor.definition}\n\n"
        "Treat this umbrella as the slug for your final emission. Variants "
        "of this umbrella (e.g. Q-learning under reinforcement-learning) "
        "should be discussed as sections inside the deep reports, NOT as "
        "separate launch_deep_research calls or distinct paradigm emissions.\n\n"
    )


def _format_candidates(known_slugs: list[str], retrieval_text: str) -> str:
    """Build the candidate block embedded in both the agent-loop and emission prompts."""
    if not known_slugs:
        return (
            "No candidate paradigms in the knowledge backbone for this problem. "
            "Every paradigm you discover will be a new entry; emit slug='__NEW__' "
            "with a slug_proposal."
        )
    lines = ["Known paradigms in the knowledge backbone (use these slugs verbatim):"]
    for slug in known_slugs:
        lines.append(f"  * **{slug}**")
    if retrieval_text:
        lines.append("")
        lines.append("Definitions and provenance from retrieve_knowledge:")
        lines.append(retrieval_text)
    return "\n".join(lines)
