"""Tests for the eval runner.

Covers:
- ``_validate_stages`` prefix-fill behavior
- ``run_pipeline`` happy path with a mocked Router
- ``run_pipeline`` partial-failure capture
- env_spec_path enforcement when REASON / BUILD requested
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.eval.runner import _validate_stages, run_pipeline
from decisionlab.router import Stage
from shared.services import Services


def _services():
    return Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )

# ---------------------------------------------------------------------------
# _validate_stages
# ---------------------------------------------------------------------------


class TestValidateStages:
    def test_research_only(self):
        assert _validate_stages([Stage.RESEARCH]) == (Stage.RESEARCH,)

    def test_full_pipeline(self):
        result = _validate_stages(
            [Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON, Stage.BUILD]
        )
        assert result == (Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON, Stage.BUILD)

    def test_gap_is_filled(self):
        # Asking for {RESEARCH, REASON} fills in FORMALIZE.
        result = _validate_stages([Stage.RESEARCH, Stage.REASON])
        assert result == (Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON)

    def test_top_only_fills_full_prefix(self):
        # Asking for just BUILD fills the entire prefix.
        result = _validate_stages([Stage.BUILD])
        assert result == (Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON, Stage.BUILD)

    def test_empty_returns_empty_tuple(self):
        # Offline suites that run only suite_assertions: declare ``stages: []``.
        assert _validate_stages([]) == ()

    def test_rejects_review_or_memory(self):
        with pytest.raises(ValueError, match="unsupported"):
            _validate_stages([Stage.MEMORY_RESEARCH])
        with pytest.raises(ValueError, match="unsupported"):
            _validate_stages([Stage.REVIEW_BUILD])


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------


class _FakeRouter:
    """Router test double — mimics what runner expects: ``run()`` and
    ``memory_results`` and the ``state`` it mutates."""

    def __init__(self, *, state, **_kw):
        self.state = state
        self.memory_results: dict[str, dict] = {}
        # Capture constructor kwargs for assertions.
        self.kwargs = _kw

    async def run(self):
        # Simulate one full pipeline run: mark approved paradigms, record
        # one memory stage, advance to DONE.
        self.state.approved_paradigms = ["alpha", "beta"]
        self.state.selected_formulations = {"alpha": ["alpha-base"]}
        self.state.approved_specs = {}
        self.memory_results["researcher"] = {
            "status": "ok",
            "nodes_created": 7,
            "nodes_merged": 1,
            "relations_created": 3,
            "facts_stored": 2,
            "duplicates_skipped": 0,
            "conflicts_resolved": 0,
            "duration_ms": 100,
        }
        self.state.stage = Stage.DONE


class _CrashingRouter(_FakeRouter):
    async def run(self):
        await super().run()
        raise RuntimeError("simulated mid-pipeline crash")


@pytest.fixture
def patch_run_row():
    """Skip the DB insert — we don't have postgres in unit tests."""
    with patch(
        "decisionlab.eval.runner._create_run_row", new=AsyncMock(return_value=None)
    ):
        yield


@pytest.mark.asyncio
async def test_happy_path_returns_populated_result(tmp_path, patch_run_row):
    client = AsyncMock()
    search = AsyncMock()
    with patch("decisionlab.eval.runner.Router", _FakeRouter):
        result = await run_pipeline(
            "homeostasis under uncertainty",
            services=_services(),
            stages=[Stage.RESEARCH],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
            run_id="11111111-1111-4111-8111-111111111111",
        )
    assert result.succeeded
    assert result.topic == "homeostasis under uncertainty"
    assert result.stages_run == (Stage.RESEARCH,)
    assert result.paradigms == ("alpha", "beta")
    assert result.formulations == ("alpha",)
    assert result.reasoner_specs == ("alpha-base",)
    assert result.failed_at is None
    assert result.memory_per_stage["researcher"]["nodes_created"] == 7
    assert result.total_nodes_created() == 7
    assert result.total_relations_created() == 3
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_router_exception_is_captured(tmp_path, patch_run_row):
    client = AsyncMock()
    search = AsyncMock()
    with patch("decisionlab.eval.runner.Router", _CrashingRouter):
        result = await run_pipeline(
            "topic",
            services=_services(),
            stages=[Stage.RESEARCH],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
        )
    assert not result.succeeded
    assert result.failed_at == Stage.DONE  # state was mutated to DONE before the crash
    assert "simulated mid-pipeline crash" in (result.error or "")


@pytest.mark.asyncio
async def test_env_spec_required_for_reason(tmp_path, patch_run_row):
    client = AsyncMock()
    search = AsyncMock()
    with pytest.raises(ValueError, match="env_spec_path is required"):
        await run_pipeline(
            "topic",
            services=_services(),
            stages=[Stage.REASON],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
        )


@pytest.mark.asyncio
async def test_env_spec_passed_to_feedback(tmp_path, patch_run_row):
    """env_spec_path forwarded to AutoApproveFeedback so it's available
    when GET_ENV_SPEC fires."""
    env_spec = tmp_path / "env.json"
    env_spec.write_text('{"width": 5}')

    captured = {}

    class _CapturingRouter(_FakeRouter):
        def __init__(self, **kw):
            super().__init__(**kw)
            captured["feedback"] = kw["feedback"]

    client = AsyncMock()
    search = AsyncMock()
    with patch("decisionlab.eval.runner.Router", _CapturingRouter):
        await run_pipeline(
            "topic",
            services=_services(),
            stages=[Stage.RESEARCH, Stage.FORMALIZE, Stage.REASON],
            env_spec_path=env_spec,
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
        )
    fb = captured["feedback"]
    # AutoApproveFeedback stores env_spec_path; verify by calling its public API.
    assert await fb.get_env_spec() == env_spec


@pytest.mark.asyncio
async def test_reports_dir_is_created_under_root(tmp_path, patch_run_row):
    client = AsyncMock()
    search = AsyncMock()
    captured: dict[str, Path] = {}

    class _DirCapturing(_FakeRouter):
        def __init__(self, **kw):
            super().__init__(**kw)
            captured["reports_dir"] = kw["state"].reports_dir

    with patch("decisionlab.eval.runner.Router", _DirCapturing):
        await run_pipeline(
            "Foraging in Uncertain Environments",
            services=_services(),
            stages=[Stage.RESEARCH],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
        )
    rd = captured["reports_dir"]
    assert rd.exists()
    assert rd.is_relative_to(tmp_path / "reports")


@pytest.mark.asyncio
async def test_usage_meter_is_reset_per_run(tmp_path, patch_run_row):
    """reset_usage=True must clear the global meter so the returned usage
    is per-run rather than cumulative across the process."""
    from decisionlab.runtime import usage as usage_module

    # Seed the meter with a fake call.
    class _FakeUsage:
        input_tokens = 1000
        output_tokens = 500
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0

    usage_module.record("seed-model", _FakeUsage())
    assert usage_module.snapshot()  # non-empty

    client = AsyncMock()
    search = AsyncMock()
    with patch("decisionlab.eval.runner.Router", _FakeRouter):
        result = await run_pipeline(
            "topic",
            services=_services(),
            stages=[Stage.RESEARCH],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
            reset_usage=True,
        )
    # FakeRouter doesn't make API calls, so usage should be empty after reset.
    assert result.usage == {}
