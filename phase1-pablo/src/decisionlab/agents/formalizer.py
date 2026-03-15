"""Formalizer orchestrator — launches FormalizerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from decisionlab.agents.formalizer_sub import FormalizerSubAgent
from decisionlab.domain.models import FormalizationReport

logger = logging.getLogger(__name__)


class Formalizer:
    def __init__(self, *, client, reports_dir: Path):
        self.client = client
        self.reports_dir = reports_dir

    async def run(self, paradigm_slugs: list[str]) -> FormalizationReport:
        if not paradigm_slugs:
            deep_dir = self.reports_dir / "deep"
            paradigm_slugs = [p.stem for p in sorted(deep_dir.glob("*.md"))]
            logger.info("Discovered %d paradigms from disk: %s", len(paradigm_slugs), paradigm_slugs)

        tasks = [
            FormalizerSubAgent(client=self.client, reports_dir=self.reports_dir).run(slug)
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
