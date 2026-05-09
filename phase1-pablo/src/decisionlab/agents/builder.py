"""Builder orchestrator — launches BuilderSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.domain.models import BuilderReport

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

logger = logging.getLogger(__name__)


class Builder:
    def __init__(
        self,
        *,
        client,
        models_prefix: str,
        storage: StorageService,
        db: DatabaseService,
        run_id: str | None = None,
        project_root: Path,
        knowledge_tool_schema: dict[str, Any] | None = None,
        knowledge_tool_handler: Callable[[dict], Awaitable[str]] | None = None,
    ):
        self.client = client
        self.models_prefix = models_prefix
        self.run_id = run_id
        self.project_root = project_root
        self._storage = storage
        self._db = db
        self._knowledge_tool_schema = knowledge_tool_schema
        self._knowledge_tool_handler = knowledge_tool_handler

    async def run(
        self,
        approved_specs: dict[str, list[str]] | None = None,
    ) -> BuilderReport:
        """Build models from reasoner specs.

        *approved_specs* — ``{paradigm_slug: [formulation_slug, ...]}``.
        When provided, only those specs are built.  When ``None`` or
        empty, all ``reasoner/{paradigm}/*.json`` files are discovered from S3.
        """
        reasoner_prefix = f"{self.models_prefix}/reasoner/"

        # Build list of (paradigm, formulation, relative_spec_path) tuples
        spec_files: list[tuple[str, str, str]] = []

        if approved_specs:
            for paradigm, formulations in approved_specs.items():
                for formulation in formulations:
                    key = f"{reasoner_prefix}{paradigm}/{formulation}.json"
                    if await self._storage.exists(key):
                        spec_files.append(
                            (
                                paradigm,
                                formulation,
                                f"reasoner/{paradigm}/{formulation}.json",
                            )
                        )
        else:
            # Discovery: list all paradigm dirs, then files within each
            keys = await self._storage.list(reasoner_prefix)
            for key in keys:
                if key.endswith(".json"):
                    rel = key[
                        len(reasoner_prefix) :
                    ]  # e.g. "homeostatic/pi-controller.json"
                    parts = rel.split("/")
                    if len(parts) == 2:
                        paradigm = parts[0]
                        formulation = parts[1].removesuffix(".json")
                        spec_files.append((paradigm, formulation, f"reasoner/{rel}"))
            logger.info(
                "Discovered %d spec(s) from S3: %s",
                len(spec_files),
                [(p, f) for p, f, _ in spec_files],
            )

        # Dispatch one BuilderSubAgent per spec
        labels: list[str] = []
        tasks: list = []
        for _paradigm, formulation, spec_path in spec_files:
            labels.append(formulation)
            tasks.append(
                BuilderSubAgent(
                    client=self.client,
                    models_prefix=self.models_prefix,
                    storage=self._storage,
                    db=self._db,
                    run_id=self.run_id,
                    project_root=self.project_root,
                    knowledge_tool_schema=self._knowledge_tool_schema,
                    knowledge_tool_handler=self._knowledge_tool_handler,
                ).run(formulation, spec_path)
            )

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for label, outcome in zip(labels, outcomes, strict=False):
            if isinstance(outcome, BaseException):
                logger.error("BuilderSubAgent failed for %s: %s", label, outcome)
            else:
                results[label] = outcome

        return BuilderReport(results=results)
