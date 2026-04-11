"""Reasoner orchestrator — launches ReasonerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging

import shared

from decisionlab.agents.reasoner_sub import ReasonerSubAgent
from decisionlab.domain.models import ReasonerReport

logger = logging.getLogger(__name__)


class Reasoner:
    def __init__(self, *, client, research_prefix: str, models_prefix: str, run_id: str | None = None):
        self.client = client
        self.research_prefix = research_prefix
        self.models_prefix = models_prefix
        self.run_id = run_id

    async def run(
        self,
        selected_formulations: dict[str, list[str]] | list[str],
    ) -> ReasonerReport:
        # Accept either {slug: [fid, ...]} or legacy [slug, ...] list
        if isinstance(selected_formulations, list):
            selected_formulations = {slug: [] for slug in selected_formulations}

        if not selected_formulations:
            formulations_prefix = f"{self.research_prefix}/formulations/"
            keys = await shared.storage.list(formulations_prefix)
            paradigm_slugs = [
                k[len(formulations_prefix):].removesuffix(".md")
                for k in keys
                if k.endswith(".md")
            ]
            logger.info("Discovered %d paradigms from S3: %s", len(paradigm_slugs), paradigm_slugs)
            selected_formulations = {slug: [] for slug in paradigm_slugs}

        paradigm_slugs = list(selected_formulations.keys())

        tasks = [
            ReasonerSubAgent(
                client=self.client,
                research_prefix=self.research_prefix,
                models_prefix=self.models_prefix,
                run_id=self.run_id,
            )
            .run(slug, formulation_ids=selected_formulations[slug] or None)
            for slug in paradigm_slugs
        ]

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for slug, outcome in zip(paradigm_slugs, outcomes):
            if isinstance(outcome, BaseException):
                logger.error("ReasonerSubAgent failed for %s: %s", slug, outcome)
            else:
                results[slug] = outcome

        return ReasonerReport(specs=results)
