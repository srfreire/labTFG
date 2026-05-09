"""Formalizer orchestrator — launches FormalizerSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from decisionlab.agents.formalizer_sub import FormalizerSubAgent
from decisionlab.domain.models import FormalizationReport

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

logger = logging.getLogger(__name__)


class Formalizer:
    def __init__(
        self,
        *,
        client,
        research_prefix: str,
        storage: StorageService,
        db: DatabaseService,
        run_id: str | None = None,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.research_prefix = research_prefix
        self.run_id = run_id
        self._storage = storage
        self._db = db
        self._knowledge_tool_schema = knowledge_tool_schema
        self._knowledge_tool_handler = knowledge_tool_handler

    async def run(self, paradigm_slugs: list[str]) -> FormalizationReport:
        if not paradigm_slugs:
            deep_prefix = f"{self.research_prefix}/deep/"
            keys = await self._storage.list(deep_prefix)
            paradigm_slugs = [
                k[len(deep_prefix) :].removesuffix(".md")
                for k in keys
                if k.endswith(".md")
            ]
            logger.info(
                "Discovered %d paradigms from S3: %s",
                len(paradigm_slugs),
                paradigm_slugs,
            )

        tasks = [
            FormalizerSubAgent(
                client=self.client,
                research_prefix=self.research_prefix,
                storage=self._storage,
                db=self._db,
                run_id=self.run_id,
                knowledge_tool_schema=self._knowledge_tool_schema,
                knowledge_tool_handler=self._knowledge_tool_handler,
            ).run(slug)
            for slug in paradigm_slugs
        ]

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for slug, outcome in zip(paradigm_slugs, outcomes, strict=False):
            if isinstance(outcome, BaseException):
                logger.error("FormalizerSubAgent failed for %s: %s", slug, outcome)
            else:
                results[slug] = outcome

        return FormalizationReport(formulations=results)
