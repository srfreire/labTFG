"""Reasoner orchestrator — launches ReasonerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from decisionlab.agents.reasoner_sub import ReasonerSubAgent
from decisionlab.domain.models import ReasonerReport

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

logger = logging.getLogger(__name__)


class Reasoner:
    def __init__(
        self,
        *,
        client,
        research_prefix: str,
        models_prefix: str,
        storage: StorageService,
        db: DatabaseService,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.research_prefix = research_prefix
        self.models_prefix = models_prefix
        self.run_id = run_id
        self._storage = storage
        self._db = db
        self._knowledge_tool_schema = knowledge_tool_schema
        self._knowledge_tool_handler = knowledge_tool_handler

    async def run(
        self,
        selected_formulations: dict[str, list[str]] | list[str],
    ) -> ReasonerReport:
        # Accept either {slug: [fid, ...]} or legacy [slug, ...] list
        if isinstance(selected_formulations, list):
            selected_formulations = {slug: [] for slug in selected_formulations}

        if not selected_formulations:
            formulations_prefix = f"{self.research_prefix}/formulations/"
            keys = await self._storage.list(formulations_prefix)
            paradigm_slugs = [
                k[len(formulations_prefix) :].removesuffix(".md")
                for k in keys
                if k.endswith(".md")
            ]
            logger.info(
                "Discovered %d paradigms from S3: %s",
                len(paradigm_slugs),
                paradigm_slugs,
            )
            selected_formulations = {slug: [] for slug in paradigm_slugs}

        paradigm_slugs = list(selected_formulations.keys())

        tasks = [
            ReasonerSubAgent(
                client=self.client,
                research_prefix=self.research_prefix,
                models_prefix=self.models_prefix,
                storage=self._storage,
                db=self._db,
                run_id=self.run_id,
                knowledge_tool_schema=self._knowledge_tool_schema,
                knowledge_tool_handler=self._knowledge_tool_handler,
            ).run(slug, formulation_slugs=selected_formulations[slug] or None)
            for slug in paradigm_slugs
        ]

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for slug, outcome in zip(paradigm_slugs, outcomes, strict=False):
            if isinstance(outcome, BaseException):
                logger.error("ReasonerSubAgent failed for %s: %s", slug, outcome)
            else:
                results[slug] = outcome

        return ReasonerReport(specs=results)
