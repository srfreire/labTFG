"""Tests for ``decisionlab.eval.suite``.

Covers:
- YAML parsing (happy + error paths)
- ``run_suite`` end-to-end with a stubbed runner
- Budget watchdog (with a fake runner that bumps usage)
- ``skip_kg_ops`` flag — KG assertions report skipped, no Cypher dispatched
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.eval import suite as suite_mod
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import (
    SetupAction,
    SuiteSpec,
    TopicSpec,
    parse_stages,
    run_suite,
)
from decisionlab.router import Stage
from shared.services import Services


def _services(*, kg=None, vectors=None, embeddings=None):
    return Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=kg,
        vectors=vectors,
        embeddings=embeddings,
    )

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
                services=_services(),
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
                services=_services(),
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
                services=_services(),
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=True,
            )

        outcome = result.topic_results[0].assertions["research"][0]
        assert outcome.detail.startswith("skipped")
        assert not outcome.passed

    @pytest.mark.asyncio
    async def test_reset_called_when_flag_set(self, tmp_path, monkeypatch):
        # The eval-KG segregation guard requires the marker before reset
        # is dispatched.
        monkeypatch.setenv("LABTFG_EVAL_KG", "1")
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
            services = _services()
            await run_suite(
                spec,
                services=services,
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=False,
            )
        reset_mock.assert_awaited_once_with(services, confirm=True)


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
                    services=_services(),
                    client=AsyncMock(),
                    search=AsyncMock(),
                    skip_kg_ops=True,
                )

        assert result.budget_exhausted
        # First topic ran and triggered the cap; subsequent topics should
        # be skipped (so we expect at most 1 topic_result).
        assert len(result.topic_results) >= 1
        assert result.topic_results[-1].run.error is not None


# ---------------------------------------------------------------------------
# Setup-action parser
# ---------------------------------------------------------------------------


class TestSuiteSetupParsing:
    def test_setup_block_parsed_into_actions(self, tmp_path):
        path = tmp_path / "with-setup.yaml"
        path.write_text(
            "name: setup-suite\n"
            "topics: [alpha]\n"
            "setup:\n"
            "  - kind: seed_canonical_paradigms\n"
            "    args:\n"
            "      fixture_path: evals/fixtures/canonical-paradigms.json\n"
        )
        spec = SuiteSpec.from_yaml(path)
        assert spec.setup == (
            SetupAction(
                kind="seed_canonical_paradigms",
                args={"fixture_path": "evals/fixtures/canonical-paradigms.json"},
            ),
        )

    def test_setup_block_optional(self, tmp_path):
        path = tmp_path / "no-setup.yaml"
        path.write_text("name: bare\ntopics: [alpha]\n")
        spec = SuiteSpec.from_yaml(path)
        assert spec.setup == ()

    def test_setup_must_be_list(self, tmp_path):
        path = tmp_path / "bad-setup.yaml"
        path.write_text("name: x\ntopics: [a]\nsetup:\n  kind: foo\n")
        with pytest.raises(ValueError, match="setup must be a list"):
            SuiteSpec.from_yaml(path)

    def test_setup_entry_must_have_kind(self, tmp_path):
        path = tmp_path / "no-kind.yaml"
        path.write_text("name: x\ntopics: [a]\nsetup:\n  - args: {fixture_path: f}\n")
        with pytest.raises(ValueError, match="setup entry missing 'kind'"):
            SuiteSpec.from_yaml(path)

    def test_setup_args_must_be_mapping(self, tmp_path):
        path = tmp_path / "bad-args.yaml"
        path.write_text(
            "name: x\ntopics: [a]\nsetup:\n  - kind: seed_canonical_paradigms\n"
            "    args: 'not-a-dict'\n"
        )
        with pytest.raises(ValueError, match="setup args must be a mapping"):
            SuiteSpec.from_yaml(path)

    def test_setup_args_default_empty_dict(self, tmp_path):
        path = tmp_path / "no-args.yaml"
        path.write_text(
            "name: x\ntopics: [a]\nsetup:\n  - kind: seed_canonical_paradigms\n"
        )
        spec = SuiteSpec.from_yaml(path)
        assert spec.setup == (SetupAction(kind="seed_canonical_paradigms", args={}),)


# ---------------------------------------------------------------------------
# Setup-action dispatcher
# ---------------------------------------------------------------------------


class TestDispatchSetupAction:
    @pytest.mark.asyncio
    async def test_seed_canonical_paradigms_invokes_seed_function(self):
        seed_mock = AsyncMock(
            return_value={"nodes_created": 3, "nodes_merged": 2, "vectors_indexed": 0}
        )
        fake_kg = MagicMock()
        services = _services(kg=fake_kg)
        with patch("decisionlab.knowledge.seed.seed_canonical_paradigms", seed_mock):
            await suite_mod._dispatch_setup_action(
                SetupAction(
                    kind="seed_canonical_paradigms",
                    args={"fixture_path": "/tmp/canon.json"},
                ),
                services,
            )
        seed_mock.assert_awaited_once()
        kwargs = seed_mock.await_args.kwargs
        args = seed_mock.await_args.args
        # First positional arg is the KG; fixture_path passed as kwarg.
        assert args[0] is fake_kg
        assert kwargs["fixture_path"].as_posix() == "/tmp/canon.json"

    @pytest.mark.asyncio
    async def test_seed_canonical_paradigms_omits_fixture_path_when_absent(self):
        seed_mock = AsyncMock(
            return_value={"nodes_created": 0, "nodes_merged": 0, "vectors_indexed": 0}
        )
        fake_kg = MagicMock()
        services = _services(kg=fake_kg)
        with patch("decisionlab.knowledge.seed.seed_canonical_paradigms", seed_mock):
            await suite_mod._dispatch_setup_action(
                SetupAction(kind="seed_canonical_paradigms"),
                services,
            )
        assert seed_mock.await_args.kwargs["fixture_path"] is None

    @pytest.mark.asyncio
    async def test_seed_canonical_paradigms_aborts_when_kg_missing(self):
        services = _services(kg=None)
        with pytest.raises(RuntimeError, match="needs a live KG"):
            await suite_mod._dispatch_setup_action(
                SetupAction(kind="seed_canonical_paradigms"),
                services,
            )

    @pytest.mark.asyncio
    async def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="unknown setup action kind"):
            await suite_mod._dispatch_setup_action(
                SetupAction(kind="not-a-thing"), _services()
            )


# ---------------------------------------------------------------------------
# Eval-KG segregation guard
# ---------------------------------------------------------------------------


class TestEvalKGGuard:
    def test_marker_env_var_truthy_passes(self, monkeypatch):
        monkeypatch.setenv("LABTFG_EVAL_KG", "1")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)
        suite_mod._assert_eval_kg_segregation()  # should not raise

    def test_eval_in_uri_passes(self, monkeypatch):
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://eval-neo4j:7687")
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)
        suite_mod._assert_eval_kg_segregation()

    def test_eval_in_database_passes(self, monkeypatch):
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_DATABASE", "labtfg-eval")
        suite_mod._assert_eval_kg_segregation()

    def test_no_marker_anywhere_raises(self, monkeypatch):
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://prod-cluster:7687")
        monkeypatch.setenv("NEO4J_DATABASE", "labtfg")
        with pytest.raises(RuntimeError, match="Refusing to reset KG"):
            suite_mod._assert_eval_kg_segregation()

    def test_falsy_marker_value_raises(self, monkeypatch):
        monkeypatch.setenv("LABTFG_EVAL_KG", "0")
        monkeypatch.setenv("NEO4J_URI", "bolt://prod-cluster:7687")
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)
        with pytest.raises(RuntimeError, match="Refusing to reset KG"):
            suite_mod._assert_eval_kg_segregation()

    def test_substring_collision_does_not_pass(self, monkeypatch):
        """A host like ``evaluation-prod`` must NOT pass the guard.

        The token boundary check is the difference between "this is the
        eval cluster" and "this happens to contain the letters e-v-a-l".
        """
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://evaluation-prod.internal:7687")
        monkeypatch.setenv("NEO4J_DATABASE", "evaluations")
        with pytest.raises(RuntimeError, match="Refusing to reset KG"):
            suite_mod._assert_eval_kg_segregation()

    def test_token_at_end_of_database_passes(self, monkeypatch):
        """Trailing token ``labtfg-eval`` is a legitimate delimited match."""
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_DATABASE", "labtfg-eval")
        suite_mod._assert_eval_kg_segregation()

    def test_database_named_exactly_eval_passes(self, monkeypatch):
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_DATABASE", "eval")
        suite_mod._assert_eval_kg_segregation()


class TestRunSuiteSetupIntegration:
    @pytest.mark.asyncio
    async def test_setup_actions_run_after_reset(self, tmp_path, monkeypatch):
        """When both reset and setup are configured, reset must come first."""
        monkeypatch.setenv("LABTFG_EVAL_KG", "1")
        spec_path = tmp_path / "with-setup.yaml"
        spec_path.write_text(
            "name: ordered\n"
            "reset_kg_before: true\n"
            "setup:\n"
            "  - kind: seed_canonical_paradigms\n"
            "topics: [alpha]\n"
        )
        spec = SuiteSpec.from_yaml(spec_path)

        call_order: list[str] = []

        async def _reset(services, *, confirm):
            call_order.append("reset")
            return 0

        async def _dispatch(action, services):
            call_order.append(f"setup:{action.kind}")

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with (
            patch("decisionlab.eval.kgadmin.reset", _reset),
            patch("decisionlab.eval.kgadmin.stats", AsyncMock(side_effect=Exception)),
            patch.object(suite_mod, "_dispatch_setup_action", _dispatch),
            patch(
                "decisionlab.eval.suite.run_pipeline",
                new=AsyncMock(side_effect=_stub),
            ),
        ):
            await run_suite(
                spec,
                services=_services(),
                client=AsyncMock(),
                search=AsyncMock(),
            )

        assert call_order == ["reset", "setup:seed_canonical_paradigms"]

    @pytest.mark.asyncio
    async def test_setup_skipped_when_skip_kg_ops(self, tmp_path):
        spec_path = tmp_path / "skip.yaml"
        spec_path.write_text(
            "name: skip\nreset_kg_before: true\n"
            "setup:\n  - kind: seed_canonical_paradigms\n"
            "topics: [alpha]\n"
        )
        spec = SuiteSpec.from_yaml(spec_path)

        dispatch_mock = AsyncMock()

        async def _stub(topic, **kw):
            return _fake_pipeline_result(topic)

        with (
            patch.object(suite_mod, "_dispatch_setup_action", dispatch_mock),
            patch(
                "decisionlab.eval.suite.run_pipeline",
                new=AsyncMock(side_effect=_stub),
            ),
        ):
            await run_suite(
                spec,
                services=_services(),
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=True,
            )

        dispatch_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reset_aborts_without_eval_marker(self, tmp_path, monkeypatch):
        """The guard fires before reset, so the suite returns an error."""
        monkeypatch.delenv("LABTFG_EVAL_KG", raising=False)
        monkeypatch.setenv("NEO4J_URI", "bolt://prod-cluster:7687")
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)

        spec_path = tmp_path / "guarded.yaml"
        spec_path.write_text("name: g\nreset_kg_before: true\ntopics: [alpha]\n")
        spec = SuiteSpec.from_yaml(spec_path)

        reset_mock = AsyncMock(return_value=0)
        with patch("decisionlab.eval.kgadmin.reset", reset_mock):
            result = await run_suite(
                spec,
                services=_services(),
                client=AsyncMock(),
                search=AsyncMock(),
                skip_kg_ops=False,
            )

        reset_mock.assert_not_awaited()
        assert result.error is not None
        assert "Refusing to reset KG" in result.error
