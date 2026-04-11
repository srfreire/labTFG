"""Builder orchestrator — launches BuilderSubAgents in parallel."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.domain.models import BuilderReport

logger = logging.getLogger(__name__)


class Builder:
    def __init__(self, *, client, reports_dir: Path, project_root: Path):
        self.client = client
        self.reports_dir = reports_dir
        self.project_root = project_root

    async def run(self, spec_ids: list[str] | None = None) -> BuilderReport:
        """Build models from reasoner specs.

        *spec_ids* — formulation IDs (e.g. ``["T01-P01-F01"]``).
        When provided, only those specs are built.  When ``None`` or
        empty, all ``reasoner/*.json`` files are discovered from disk.
        """
        reasoner_dir = self.reports_dir / "reasoner"

        if spec_ids:
            spec_files = [
                reasoner_dir / f"{sid}.json"
                for sid in spec_ids
                if (reasoner_dir / f"{sid}.json").exists()
            ]
        else:
            spec_files = sorted(reasoner_dir.glob("*.json"))
            logger.info(
                "Discovered %d spec(s) from disk: %s",
                len(spec_files),
                [f.stem for f in spec_files],
            )

        # Dispatch one BuilderSubAgent per spec (keyed by formulation ID)
        fids: list[str] = []
        tasks: list = []
        for spec_file in spec_files:
            fid = spec_file.stem
            fids.append(fid)
            tasks.append(
                BuilderSubAgent(
                    client=self.client,
                    reports_dir=self.reports_dir,
                    project_root=self.project_root,
                ).run(fid, f"reasoner/{spec_file.name}")
            )

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, str] = {}
        for fid, outcome in zip(fids, outcomes):
            if isinstance(outcome, BaseException):
                logger.error("BuilderSubAgent failed for %s: %s", fid, outcome)
            else:
                results[fid] = outcome

        return BuilderReport(results=results)
