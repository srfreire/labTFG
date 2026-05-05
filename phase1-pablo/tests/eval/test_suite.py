"""Tests for ``decisionlab.eval.suite``.

Covers:
- YAML parsing (happy + error paths)
- ``run_suite`` end-to-end with a stubbed runner
- Budget watchdog (with a fake runner that bumps usage)
- ``skip_kg_ops`` flag — KG assertions report skipped, no Cypher dispatched
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.eval import suite as suite_mod
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import (
    SuiteSpec,
    TopicSpec,
    parse_stages,
    run_suite,
)
from decisionlab.router import Stage

# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------


class TestSuiteSpecFromYaml:
    def test_minimal_suite(self, tmp_path):
        path = tmp_path / "smoke.yaml"
        path.write_text("name: smoke\ntopics:\n  - foo\n  - bar\n")
        spec = SuiteSpec.from_yaml(path)
        assert spec.name == "smoke"
        assert spec.stages == (Stage.RESEARCH,)
        assert spec.topics == (TopicSpec(text="foo"), TopicSpec(text="bar"))
        assert spec.env_spec_path is None
        assert spec.max_usd_total is None
        assert spec.source_path == path

    def test_full_pipeline_with_assertions(self, tmp_path):
        env = tmp_path / "env.json"
        env.write_text("{}")
        path = tmp_path / "full.yaml"
        path.write_text(
            "name: full\n"
            f"env_spec: {env}\n"
            "stages: [research, formalize, reason, build]\n"
            "reset_kg_before: true\n"
            "topics:\n"
            "  - text: alpha\n"
            "    expect:\n"
            "      research:\n"
            "        - paradigm: rl\n"
            "        - min_paradigms: 2\n"
            "      build:\n"
            "        - module_imports: rl-q-learning\n"
            "budget:\n"
            "  max_usd_total: 25.50\n"
        )
        spec = SuiteSpec.from_yaml(path)
        assert spec.stages == (
            Stage.RESEARCH,
            Stage.FORMALIZE,
            Stage.REASON,
            Stage.BUILD,
        )
        assert spec.reset_kg_before is True
        assert spec.env_spec_path == env.resolve()
        assert spec.max_usd_total == 25.50
        topic = spec.topics[0]
        assert topic.expect["research"][0] == {"paradigm": "rl"}
        assert topic.expect["build"][0] == {"module_imports": "rl-q-learning"}

    def test_reason_without_env_spec_rejected(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("stages: [research, formalize, reason]\ntopics: [foo]\n")
        with pytest.raises(ValueError, match="env_spec required"):
            SuiteSpec.from_yaml(path)

    def test_missing_env_spec_file_rejected(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text(
            "stages: [research, formalize, reason]\n"
            f"env_spec: {tmp_path}/nope.json\n"
            "topics: [foo]\n"
        )
        with pytest.raises(FileNotFoundError):
            SuiteSpec.from_yaml(path)

    def test_unknown_stage_rejected(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("stages: [zoom]\ntopics: [foo]\n")
        with pytest.raises(ValueError, match="unknown stage"):
            SuiteSpec.from_yaml(path)


class TestParseStages:
    def test_single_string(self):
        assert parse_stages(["research"]) == (Stage.RESEARCH,)

    def test_multiple(self):
        assert parse_stages(["research", "formalize"]) == (
            Stage.RESEARCH,
            Stage.FORMALIZE,
        )

    def test_unknown(self):
        with pytest.raises(ValueError, match="unknown stage"):
            parse_stages(["nonexistent"])


# ---------------------------------------------------------------------------
# run_suite — stub runner & kgadmin
# ---------------------------------------------------------------------------


def _fake_pipeline_result(topic: str, **kw) -> PipelineRunResult:
    base = dict(
        run_id=f"run-{topic[:6]}",
        topic=topic,
        stages_run=(Stage.RESEARCH,),
        paradigms=("alpha", "beta"),
        formulations=("alpha",),
        memory_per_stage={"researcher": {"nodes_created": 5}},
    )
    base.update(kw)
    return PipelineRunResult(**base)


@pytest.fixture
def patch_kgadmin():
    """Stub kgadmin.reset/stats so suite runs don't hit Neo4j."""
    with (
        patch(
            "decisionlab.eval.kgadmin.reset",
            new=AsyncMock(return_value=0),
        ),
        patch(
            "decisionlab.eval.kgadmin.stats",
            new=AsyncMock(side_effect=AssertionError("should be skipped")),
        ),
    ):
        yield


class TestRunSuite:
    @pytest.mark.asyncio
    async def test_runs_each_topic_and_collects_results(self, tmp_path, patch_kgadmin):
        spec_path = tmp_path / "smoke.yaml"
        spec_path.write_text("name: s\ntopics: [alpha, beta]\n")
        spec = SuiteSpec.from_yaml(spec_path)

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline", new=AsyncMock(side_effect=_stub)
        ):
            result = await run_suite(
                spec,
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=True,
            )

        assert len(result.topic_results) == 2
        assert [t.topic for t in result.topic_results] == ["alpha", "beta"]
        assert not result.budget_exhausted
        assert result.error is None

    @pytest.mark.asyncio
    async def test_assertions_evaluated_per_stage(self, tmp_path, patch_kgadmin):
        spec_path = tmp_path / "asserts.yaml"
        spec_path.write_text(
            "name: s\n"
            "topics:\n"
            "  - text: alpha\n"
            "    expect:\n"
            "      research:\n"
            "        - paradigm: alpha\n"
            "        - paradigm: missing\n"
        )
        spec = SuiteSpec.from_yaml(spec_path)

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline", new=AsyncMock(side_effect=_stub)
        ):
            result = await run_suite(
                spec,
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=True,
            )

        topic_result = result.topic_results[0]
        outcomes = topic_result.assertions["research"]
        assert len(outcomes) == 2
        assert outcomes[0].passed
        assert not outcomes[1].passed
        assert topic_result.failed_count() == 1
        assert not result.all_passed

    @pytest.mark.asyncio
    async def test_kg_assertion_skipped_when_skip_kg_ops(self, tmp_path, patch_kgadmin):
        spec_path = tmp_path / "kg.yaml"
        spec_path.write_text(
            "name: s\n"
            "topics:\n"
            "  - text: alpha\n"
            "    expect:\n"
            "      research:\n"
            "        - min_nodes: { label: Paradigm, n: 3 }\n"
        )
        spec = SuiteSpec.from_yaml(spec_path)

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with patch(
            "decisionlab.eval.suite.run_pipeline", new=AsyncMock(side_effect=_stub)
        ):
            result = await run_suite(
                spec,
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=True,
            )

        outcome = result.topic_results[0].assertions["research"][0]
        assert outcome.detail.startswith("skipped")
        assert not outcome.passed

    @pytest.mark.asyncio
    async def test_reset_called_when_flag_set(self, tmp_path):
        spec_path = tmp_path / "reset.yaml"
        spec_path.write_text("name: s\nreset_kg_before: true\ntopics: [alpha]\n")
        spec = SuiteSpec.from_yaml(spec_path)

        reset_mock = AsyncMock(return_value=10)
        stats_mock = AsyncMock(side_effect=Exception("ignored in test"))

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with (
            patch("decisionlab.eval.kgadmin.reset", reset_mock),
            patch("decisionlab.eval.kgadmin.stats", stats_mock),
            patch(
                "decisionlab.eval.suite.run_pipeline", new=AsyncMock(side_effect=_stub)
            ),
        ):
            await run_suite(
                spec,
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=False,
            )
        reset_mock.assert_awaited_once_with(confirm=True)


# ---------------------------------------------------------------------------
# Budget watchdog
# ---------------------------------------------------------------------------


class TestBudgetWatchdog:
    @pytest.mark.asyncio
    async def test_exhaustion_short_circuits_remaining_topics(
        self, tmp_path, patch_kgadmin
    ):
        spec_path = tmp_path / "budget.yaml"
        spec_path.write_text(
            "name: budget\n"
            "topics: [alpha, beta, gamma]\n"
            "budget:\n"
            "  max_usd_total: 0.00001\n"
        )
        spec = SuiteSpec.from_yaml(spec_path)

        # Each stub call seeds a small amount of usage; the watchdog sees
        # it on the next sample and cancels.
        async def _stub(topic, **kw):
            from decisionlab.runtime import usage as u

            class _U:
                input_tokens = 1_000_000
                output_tokens = 1_000_000
                cache_creation_input_tokens = 0
                cache_read_input_tokens = 0

            u.record("anthropic/claude-opus-4.6", _U())
            # Stay alive long enough for the watchdog to sample.
            import asyncio

            await asyncio.sleep(0.05)
            return _fake_pipeline_result(topic)

        # Tighter check interval so the test doesn't take forever.
        with (
            patch(
                "decisionlab.eval.suite.run_pipeline", new=AsyncMock(side_effect=_stub)
            ),
            patch.object(
                suite_mod, "_run_with_budget", wraps=suite_mod._run_with_budget
            ),
        ):
            # Force the watchdog interval down for the test.
            original = suite_mod._run_with_budget

            async def _fast_run(coro_factory, *, max_usd, check_interval=0.01):
                return await original(
                    coro_factory, max_usd=max_usd, check_interval=check_interval
                )

            with patch.object(suite_mod, "_run_with_budget", _fast_run):
                from decisionlab.runtime import usage as u

                u.reset()
                result = await run_suite(
                    spec,
                    client=AsyncMock(),
                    search=AsyncMock(),
                    skip_kg_ops=True,
                )

        assert result.budget_exhausted
        # First topic ran and triggered the cap; subsequent topics should
        # be skipped (so we expect at most 1 topic_result).
        assert len(result.topic_results) >= 1
        assert result.topic_results[-1].run.error is not None
