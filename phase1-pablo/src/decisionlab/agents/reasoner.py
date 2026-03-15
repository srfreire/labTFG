"""Reasoner orchestrator — launches ReasonerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from decisionlab.agents.reasoner_sub import ReasonerSubAgent
from decisionlab.domain.models import ReasonerReport

logger = logging.getLogger(__name__)


class Reasoner:
    def __init__(self, *, client, reports_dir: Path):
        self.client = client
        self.reports_dir = reports_dir

    async def run(self, paradigm_slugs: list[str]) -> ReasonerReport:
        if not paradigm_slugs:
            formulations_dir = self.reports_dir / "formulations"
            paradigm_slugs = [p.stem for p in sorted(formulations_dir.glob("*.md"))]
            logger.info("Discovered %d paradigms from disk: %s", len(paradigm_slugs), paradigm_slugs)

        tasks = [
            ReasonerSubAgent(client=self.client, reports_dir=self.reports_dir).run(slug)
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
