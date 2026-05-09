"""End-to-end suite test against live infra (Neo4j + Postgres + MinIO).

Exercises ``run_suite`` with the real ``kgadmin`` operations (reset,
pre-stats, post-stats) but stubs ``run_pipeline`` so we don't burn
Anthropic tokens. The point is to verify that the *suite-level*
plumbing works against real backends — KG growth deltas in the report,
budget watchdog interplay with the watchdog's sampling loop, and
KG-touching predicates like ``min_nodes`` returning real counts.

Run with:

    docker compose up -d postgres minio neo4j qdrant
    cd shared && uv run alembic upgrade head
    uv run pytest tests/eval/test_suite_integration.py -m integration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml

from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import SuiteSpec, run_suite
from decisionlab.router import Stage
from shared.services import init_services, shutdown_services

pytestmark = pytest.mark.integration

# Module-level holder so the fakes that patch ``run_pipeline`` (and run
# inside the suite, without fixture access) can reach the live Neo4j.
_live_services = None


@pytest.fixture
async def live_infra(monkeypatch):
    # P0-003 introduced a segregation guard that refuses
    # ``reset_kg_before`` against an unmarked Neo4j. Mark the test
    # instance as eval so the existing fixtures keep working without
    # adding an env-var requirement to every CI invocation.
    global _live_services
    monkeypatch.setenv("LABTFG_EVAL_KG", "1")
    services = await init_services()
    if services.kg is None:
        await shutdown_services(services)
        pytest.skip("Neo4j not reachable")
    _live_services = services
    await services.kg.query("MATCH (n) DETACH DELETE n")
    try:
        yield services
    finally:
        try:
            await services.kg.query("MATCH (n) DETACH DELETE n")
        finally:
            _live_services = None
            await shutdown_services(services)


def _write_suite(tmp_path, body: dict):
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(body))
    return SuiteSpec.from_yaml(path)


def _fake_result(topic: str) -> PipelineRunResult:
    return PipelineRunResult(
        run_id=f"run-{topic[:6]}",
        topic=topic,
        stages_run=(Stage.RESEARCH,),
        paradigms=("alpha",),
        memory_per_stage={"researcher": {"nodes_created": 0, "relations_created": 0}},
    )


# ---------------------------------------------------------------------------
# Reset + pre/post stats actually run against real Neo4j
# ---------------------------------------------------------------------------


class TestSuiteAgainstLiveKG:
    @pytest.mark.asyncio
    async def test_reset_kg_before_actually_wipes(self, live_infra, tmp_path):
        # Seed the KG with a stale node so we can prove the reset ran.
        await live_infra.kg.query("CREATE (n:Stale {slug: 'left-over'})")

        spec = _write_suite(
            tmp_path,
            {
                "name": "reset-test",
                "reset_kg_before": True,
                "topics": ["seed-topic"],
            },
        )

        async def _stub(topic, **kw):
            return _fake_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=_stub),
        ):
            result = await run_suite(spec, client=AsyncMock(), search=AsyncMock())

        # Pre-stats should be 0 (we wiped right before).
        assert result.pre_stats is not None
        assert result.pre_stats.total_nodes == 0
        # Post-stats also 0 because the stub didn't write anything.
        assert result.post_stats is not None
        assert result.post_stats.total_nodes == 0

        # Stale node from before should be gone.
        rows = await live_infra.kg.query("MATCH (n:Stale) RETURN count(n) AS c")
        assert rows[0]["c"] == 0

    @pytest.mark.asyncio
    async def test_kg_growth_delta_reflects_writes(self, live_infra, tmp_path):
        # Seed BEFORE the suite — pre-stats should see 1 node.
        await live_infra.kg.query("CREATE (n:Existing {slug: 'pre'})")

        spec = _write_suite(
            tmp_path,
            {
                "name": "growth-test",
                "reset_kg_before": False,
                "topics": ["topic"],
            },
        )

        async def _stub_that_writes(topic, **kw):
            # Simulate what the real MemoryAgent would do: drop a node.
            await live_infra.kg.query(
                "CREATE (n:WrittenByStub {slug: $s})", {"s": topic}
            )
            return _fake_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=_stub_that_writes),
        ):
            result = await run_suite(spec, client=AsyncMock(), search=AsyncMock())

        assert result.pre_stats.total_nodes == 1
        assert result.post_stats.total_nodes == 2  # 1 existing + 1 written by stub
        delta = result.post_stats.total_nodes - result.pre_stats.total_nodes
        assert delta == 1

    @pytest.mark.asyncio
    async def test_min_nodes_assertion_runs_against_real_kg(self, live_infra, tmp_path):
        spec = _write_suite(
            tmp_path,
            {
                "name": "min-nodes-test",
                "reset_kg_before": False,
                "topics": [
                    {
                        "text": "topic",
                        "expect": {
                            "research": [{"min_nodes": {"label": "Paradigm", "n": 2}}]
                        },
                    }
                ],
            },
        )

        async def _stub_writes_paradigms(topic, **kw):
            await live_infra.kg.query("CREATE (n:Paradigm {slug: 'a'})")
            await live_infra.kg.query("CREATE (n:Paradigm {slug: 'b'})")
            await live_infra.kg.query("CREATE (n:Paradigm {slug: 'c'})")
            return _fake_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=_stub_writes_paradigms),
        ):
            result = await run_suite(spec, client=AsyncMock(), search=AsyncMock())

        topic_result = result.topic_results[0]
        # We wrote 3 Paradigm nodes; the assertion checks ≥ 2.
        assert topic_result.assertions["research"][0].passed
        assert "3 nodes" in topic_result.assertions["research"][0].detail

    @pytest.mark.asyncio
    async def test_min_nodes_assertion_fails_when_threshold_missed(
        self, live_infra, tmp_path
    ):
        spec = _write_suite(
            tmp_path,
            {
                "name": "min-nodes-fail",
                "reset_kg_before": True,  # ensures a clean slate
                "topics": [
                    {
                        "text": "topic",
                        "expect": {
                            "research": [{"min_nodes": {"label": "Paradigm", "n": 5}}]
                        },
                    }
                ],
            },
        )

        # Only one Paradigm written — threshold 5 should fail.
        async def _stub(topic, **kw):
            await live_infra.kg.query("CREATE (n:Paradigm {slug: 'lonely'})")
            return _fake_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=_stub),
        ):
            result = await run_suite(spec, client=AsyncMock(), search=AsyncMock())

        topic_result = result.topic_results[0]
        assert not topic_result.assertions["research"][0].passed
        assert not result.all_passed
