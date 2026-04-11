"""Builder orchestrator — launches BuilderSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import shared

from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.domain.models import BuilderReport

logger = logging.getLogger(__name__)


class Builder:
    def __init__(self, *, client, models_prefix: str, run_id: str | None = None, project_root: Path):
        self.client = client
        self.models_prefix = models_prefix
        self.run_id = run_id
        self.project_root = project_root

    async def run(self, spec_ids: list[str] | None = None) -> BuilderReport:
        """Build models from reasoner specs.

        *spec_ids* — formulation IDs (e.g. ``["T01-P01-F01"]``).
        When provided, only those specs are built.  When ``None`` or
        empty, all ``reasoner/*.json`` files are discovered from S3.
        """
        reasoner_prefix = f"{self.models_prefix}/reasoner/"

        if spec_ids:
            spec_files = []
            for sid in spec_ids:
                key = f"{reasoner_prefix}{sid}.json"
                if await shared.storage.exists(key):
                    spec_files.append((sid, f"reasoner/{sid}.json"))
        else:
            keys = await shared.storage.list(reasoner_prefix)
            spec_files = []
            for key in keys:
                if key.endswith(".json"):
                    filename = key[len(reasoner_prefix):]
                    fid = filename.removesuffix(".json")
                    spec_files.append((fid, f"reasoner/{filename}"))
            logger.info(
                "Discovered %d spec(s) from S3: %s",
                len(spec_files),
                [f[0] for f in spec_files],
            )

        # Dispatch one BuilderSubAgent per spec (keyed by formulation ID)
        fids: list[str] = []
        tasks: list = []
        for fid, spec_path in spec_files:
            fids.append(fid)
            tasks.append(
                BuilderSubAgent(
                    client=self.client,
                    models_prefix=self.models_prefix,
                    run_id=self.run_id,
                    project_root=self.project_root,
                ).run(fid, spec_path)
            )

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for fid, outcome in zip(fids, outcomes):
            if isinstance(outcome, BaseException):
                logger.error("BuilderSubAgent failed for %s: %s", fid, outcome)
            else:
                results[fid] = outcome

        return BuilderReport(results=results)
