"""Builder orchestrator — launches BuilderSubAgents in parallel."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.domain.models import BuilderReport

logger = logging.getLogger(__name__)


class Builder:
    def __init__(self, *, client, reports_dir: Path, project_root: Path):
        self.client = client
        self.reports_dir = reports_dir
        self.project_root = project_root

    async def run(self, paradigm_slugs: list[str]) -> BuilderReport:
        # 1. Discover and group specs by paradigm
        reasoner_dir = self.reports_dir / "reasoner"
        specs_by_paradigm: dict[str, list[str]] = defaultdict(list)
        for spec_file in sorted(reasoner_dir.glob("*.json")):
            data = json.loads(spec_file.read_text())
            paradigm = data["paradigm"]
            specs_by_paradigm[paradigm].append(f"reasoner/{spec_file.name}")

        # 2. Filter by paradigm_slugs if provided
        if paradigm_slugs:
            specs_by_paradigm = {k: v for k, v in specs_by_paradigm.items() if k in paradigm_slugs}
        else:
            logger.info("Discovered %d paradigms: %s", len(specs_by_paradigm), list(specs_by_paradigm.keys()))

        # 3. Dispatch one BuilderSubAgent per paradigm
        slugs = list(specs_by_paradigm.keys())
        tasks = [
            BuilderSubAgent(client=self.client, reports_dir=self.reports_dir, project_root=self.project_root)
            .run(slug, specs_by_paradigm[slug])
            for slug in slugs
        ]

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. Collect results, log failures
        results: dict[str, str] = {}
        for slug, outcome in zip(slugs, outcomes):
            if isinstance(outcome, BaseException):
                logger.error("BuilderSubAgent failed for %s: %s", slug, outcome)
            else:
                results[slug] = outcome

        return BuilderReport(results=results)
