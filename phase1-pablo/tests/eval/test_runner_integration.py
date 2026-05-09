"""End-to-end runner test against live Postgres + Neo4j + MinIO.

Stubs the Researcher (so we make zero LLM calls) and the MemoryAgent
(so we control exactly what lands in the KG), but uses a real
``Router``, real ``shared`` infrastructure, and real ``run_pipeline``.
This exercises:

- ``_create_run_row`` — verify a Run row appears in Postgres
- ``Router.run`` orchestration with ``AutoApproveFeedback``
- ``Router.memory_results`` mirror — read by the runner
- ``PipelineRunResult`` shape coming out clean

Run with:

    docker compose up -d postgres minio neo4j qdrant
    cd shared && uv run alembic upgrade head
    uv run pytest tests/eval/test_runner_integration.py -m integration
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.domain.models import Paradigm, ResearchReport
from decisionlab.eval.runner import run_pipeline
from decisionlab.knowledge.models import MemoryAgentResult
from decisionlab.router import Stage
from shared.services import init_services, shutdown_services

pytestmark = pytest.mark.integration

# Module-level holder so the in-test fakes (which don't see fixture args)
# can write KG nodes through the same connection ``run_pipeline`` uses.
_live_services = None


@pytest.fixture
async def live_infra(tmp_path):
    global _live_services
    services = await init_services()
    if services.kg is None or services.db is None:
        await shutdown_services(services)
        pytest.skip("Live infra not reachable")
    _live_services = services
    await services.kg.query("MATCH (n) DETACH DELETE n")
    try:
        yield tmp_path, services
    finally:
        try:
            await services.kg.query("MATCH (n) DETACH DELETE n")
        finally:
            _live_services = None
            await shutdown_services(services)


class _FakeResearcher:
    """Returns a canned ResearchReport and writes deep reports to S3.

    The runtime's ``AutoApproveFeedback`` discovers paradigm slugs by
    listing ``research/{run_id}/deep/*.md`` in S3 — the fake mirrors
    what the real Researcher+DeepResearcher chain does so the rest of
    the pipeline (Memory Agent, review) sees plausible state.
    """

    def __init__(self, **kw):
        self.run_id = kw.get("run_id")

    async def run(self, problem: str, *, anchor_umbrella=None):
        deep_reports = {
            "reinforcement-learning": "# Reinforcement learning\n\ndeep content",
            "prospect-theory": "# Prospect theory\n\ndeep content",
        }
        if self.run_id:
            from decisionlab.tools.reports import save_deep_report

            for slug, content in deep_reports.items():
                await save_deep_report(self.run_id, slug, content)
        return ResearchReport(
            paradigms=[
                Paradigm(id="rl", name="Reinforcement learning", description=""),
                Paradigm(id="prospect", name="Prospect theory", description=""),
            ],
            summary=f"# Paradigms for: {problem}\n\nrl, prospect.",
            deep_reports=deep_reports,
        )


class _FakeMemoryAgent:
    """Writes a few canned nodes to the live KG and returns a real
    MemoryAgentResult so the Router's ``_record_memory_result`` and
    the runner's ``memory_per_stage`` mirror both work end-to-end."""

    def __init__(self, **kw):
        pass

    async def run(self, stage: str, output: str, run_id: str, emit=None):
        # Write distinctive nodes so the test can prove the integration
        # path actually executed. Slug includes run_id to dodge the
        # Paradigm.slug uniqueness constraint when multiple runs land in
        # the same Neo4j instance during a test session.
        await _live_services.kg.query(
            "CREATE (p:Paradigm {slug: $s, run_id: $r})",
            {"s": f"stub-{stage}-{run_id[:8]}", "r": run_id},
        )
        return MemoryAgentResult(
            nodes_created=1,
            nodes_merged=0,
            relations_created=0,
            facts_stored=0,
            duplicates_skipped=0,
            conflicts_resolved=0,
            duration_ms=10,
        )


# ---------------------------------------------------------------------------
# run_pipeline e2e
# ---------------------------------------------------------------------------


class TestRunPipelineE2E:
    @pytest.mark.asyncio
    async def test_research_only_round_trip(self, live_infra):
        tmp_path, services = live_infra
        run_id = str(uuid.uuid4())

        with (
            patch("decisionlab.agents.researcher.Researcher", _FakeResearcher),
            patch("decisionlab.agents.memory_agent.MemoryAgent", _FakeMemoryAgent),
        ):
            result = await run_pipeline(
                "Foraging in uncertain environments",
                stages=[Stage.RESEARCH],
                project_root=tmp_path,
                client=MagicMock(),
                search=DuckDuckGoAdapter(),
                reports_root=tmp_path / "reports",
                run_id=run_id,
            )

        # Result shape
        assert result.succeeded
        assert result.run_id == run_id
        assert result.failed_at is None
        # AutoApproveFeedback approves both deep reports → both land in
        # state.approved_paradigms.
        assert "reinforcement-learning" in result.paradigms
        assert "prospect-theory" in result.paradigms

        # The fake MemoryAgent wrote one node per stage; verify it
        # actually landed in Neo4j with the right run_id tag.
        rows = await services.kg.query(
            "MATCH (p:Paradigm {run_id: $r}) RETURN count(p) AS c",
            {"r": run_id},
        )
        assert rows[0]["c"] == 1
        # And the runner captured the per-stage payload.
        assert result.memory_per_stage["researcher"]["nodes_created"] == 1

    @pytest.mark.asyncio
    async def test_run_row_inserted_and_updated(self, live_infra):
        """The runner must insert a Run row before the Router starts
        (otherwise mid-pipeline updates from the Router silently no-op)."""
        from sqlalchemy import select

        from shared.models import Run

        tmp_path, services = live_infra
        run_id = str(uuid.uuid4())

        with (
            patch("decisionlab.agents.researcher.Researcher", _FakeResearcher),
            patch("decisionlab.agents.memory_agent.MemoryAgent", _FakeMemoryAgent),
        ):
            await run_pipeline(
                "topic-x",
                stages=[Stage.RESEARCH],
                project_root=tmp_path,
                client=MagicMock(),
                search=DuckDuckGoAdapter(),
                reports_root=tmp_path / "reports",
                run_id=run_id,
            )

        async with services.db.get_session() as session:
            row = await session.scalar(select(Run).where(Run.id == uuid.UUID(run_id)))
        assert row is not None
        assert row.problem_description == "topic-x"
        assert row.s3_prefix == f"research/{run_id}"
        # P3-003 AC2: eval driver tags inserts with kind='eval' so the
        # retention prune command can reap them by age.
        assert row.kind == "eval"

    @pytest.mark.asyncio
    async def test_kg_writes_attribute_to_correct_run_id(self, live_infra):
        """Two runs in the same process must produce KG nodes tagged
        with their own run_ids — verifies that ``_create_run_row`` and
        the AutoApproveFeedback's S3 listing use the runner's run_id
        rather than leaking state between calls."""
        tmp_path, services = live_infra
        run_a = str(uuid.uuid4())
        run_b = str(uuid.uuid4())

        with (
            patch("decisionlab.agents.researcher.Researcher", _FakeResearcher),
            patch("decisionlab.agents.memory_agent.MemoryAgent", _FakeMemoryAgent),
        ):
            await run_pipeline(
                "topic-a",
                stages=[Stage.RESEARCH],
                project_root=tmp_path,
                client=MagicMock(),
                search=DuckDuckGoAdapter(),
                reports_root=tmp_path / "reports",
                run_id=run_a,
            )
            await run_pipeline(
                "topic-b",
                stages=[Stage.RESEARCH],
                project_root=tmp_path,
                client=MagicMock(),
                search=DuckDuckGoAdapter(),
                reports_root=tmp_path / "reports",
                run_id=run_b,
            )

        rows_a = await services.kg.query(
            "MATCH (p:Paradigm {run_id: $r}) RETURN count(p) AS c",
            {"r": run_a},
        )
        rows_b = await services.kg.query(
            "MATCH (p:Paradigm {run_id: $r}) RETURN count(p) AS c",
            {"r": run_b},
        )
        assert rows_a[0]["c"] == 1
        assert rows_b[0]["c"] == 1
