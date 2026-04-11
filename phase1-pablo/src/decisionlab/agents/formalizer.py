"""Formalizer orchestrator — launches FormalizerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging

import shared

from decisionlab.agents.formalizer_sub import FormalizerSubAgent
from decisionlab.domain.models import FormalizationReport

logger = logging.getLogger(__name__)


class Formalizer:
    def __init__(self, *, client, research_prefix: str, run_id: str | None = None):
        self.client = client
        self.research_prefix = research_prefix
        self.run_id = run_id

    async def run(self, paradigm_slugs: list[str]) -> FormalizationReport:
        if not paradigm_slugs:
            deep_prefix = f"{self.research_prefix}/deep/"
            keys = await shared.storage.list(deep_prefix)
            paradigm_slugs = [
                k[len(deep_prefix):].removesuffix(".md")
                for k in keys
                if k.endswith(".md")
            ]
            logger.info("Discovered %d paradigms from S3: %s", len(paradigm_slugs), paradigm_slugs)

        tasks = [
            FormalizerSubAgent(
                client=self.client,
                research_prefix=self.research_prefix,
                run_id=self.run_id,
            ).run(slug)
            for slug in paradigm_slugs
        ]

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for slug, outcome in zip(paradigm_slugs, outcomes):
            if isinstance(outcome, BaseException):
                logger.error("FormalizerSubAgent failed for %s: %s", slug, outcome)
            else:
                results[slug] = outcome

        return FormalizationReport(formulations=results)
