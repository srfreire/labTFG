"""Tests for the FeedbackPort protocol and its three implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.feedback_port import (
    AutoApproveFeedback,
    CLIFeedback,
    FeedbackPort,
    WebFeedback,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_research_dir(tmp_path: Path, slugs: list[str]) -> Path:
    deep = tmp_path / "deep"
    deep.mkdir()
    for slug in slugs:
        (deep / f"{slug}.md").write_text(f"# {slug}\n\nContent.")
    return tmp_path


def _make_reasoner_dir(tmp_path: Path, specs: list[dict[str, Any]]) -> Path:
    reasoner = tmp_path / "reasoner"
    reasoner.mkdir()
    for spec in specs:
        slug = spec["formulation_id"]
        (reasoner / f"{slug}.json").write_text(json.dumps(spec))
    return tmp_path


# ---------------------------------------------------------------------------
# Protocol satisfaction (structural subtyping checks)
# ---------------------------------------------------------------------------


class TestProtocolSatisfaction:
    """Each implementation must satisfy FeedbackPort structurally."""

    def test_cli_feedback_is_port(self):
        cli: FeedbackPort = CLIFeedback()
        assert isinstance(cli, CLIFeedback)

    def test_web_feedback_is_port(self):
        emit = AsyncMock()
        web: FeedbackPort = WebFeedback(emit)
        assert isinstance(web, WebFeedback)

    def test_auto_approve_is_port(self):
        auto: FeedbackPort = AutoApproveFeedback()
        assert isinstance(auto, AutoApproveFeedback)


# ---------------------------------------------------------------------------
# CLIFeedback — must delegate so existing patches keep working
# ---------------------------------------------------------------------------


class TestCLIFeedbackDelegation:
    """Patches against ``decisionlab.feedback.review_*`` must still take effect."""

    @pytest.mark.asyncio
    async def test_review_research_delegates(self, tmp_path):
        cli = CLIFeedback()
        with patch(
            "decisionlab.feedback.review_research",
            new=AsyncMock(return_value=(["foo"], None)),
        ) as mock:
            result = await cli.review_research(tmp_path, run_id="r1")
        assert result == (["foo"], None)
        mock.assert_awaited_once_with(tmp_path)

    @pytest.mark.asyncio
    async def test_review_formalize_delegates_with_run_id(self, tmp_path):
        from unittest.mock import MagicMock

        storage = MagicMock()
        cli = CLIFeedback(storage=storage)
        with patch(
            "decisionlab.feedback.review_formalize",
            new=AsyncMock(return_value={"foo": [1, 2]}),
        ) as mock:
            result = await cli.review_formalize(tmp_path, ["foo"], run_id="run-1")
        assert result == {"foo": [1, 2]}
        mock.assert_awaited_once_with(
            tmp_path, ["foo"], run_id="run-1", storage=storage
        )

    @pytest.mark.asyncio
    async def test_get_env_spec_delegates(self):
        cli = CLIFeedback()
        with patch(
            "decisionlab.feedback.get_env_spec",
            new=AsyncMock(return_value=Path("/tmp/env.json")),
        ):
            assert await cli.get_env_spec() == Path("/tmp/env.json")

    @pytest.mark.asyncio
    async def test_review_reason_delegates(self, tmp_path):
        cli = CLIFeedback()
        with patch(
            "decisionlab.feedback.review_reason",
            new=AsyncMock(return_value=(["a"], [], [])),
        ):
            assert await cli.review_reason(tmp_path) == (["a"], [], [])

    @pytest.mark.asyncio
    async def test_review_build_delegates(self, tmp_path):
        cli = CLIFeedback()
        with patch(
            "decisionlab.feedback.review_build",
            new=AsyncMock(return_value=([], [], [])),
        ) as mock:
            await cli.review_build(tmp_path, {"foo": "ok"})
        mock.assert_awaited_once_with(tmp_path, {"foo": "ok"})


# ---------------------------------------------------------------------------
# WebFeedback — must propagate emit
# ---------------------------------------------------------------------------


class TestWebFeedbackDelegation:
    @pytest.mark.asyncio
    async def test_review_research_passes_emit(self, tmp_path):
        from unittest.mock import MagicMock

        emit = AsyncMock()
        storage = MagicMock()
        web = WebFeedback(emit, storage=storage)
        with patch(
            "decisionlab.web_feedback.review_research",
            new=AsyncMock(return_value=([], None)),
        ) as mock:
            await web.review_research(tmp_path, run_id="r1")
        mock.assert_awaited_once_with(tmp_path, emit, run_id="r1", storage=storage)

    @pytest.mark.asyncio
    async def test_review_formalize_passes_emit_and_run_id(self, tmp_path):
        from unittest.mock import MagicMock

        emit = AsyncMock()
        storage = MagicMock()
        web = WebFeedback(emit, storage=storage)
        with patch(
            "decisionlab.web_feedback.review_formalize",
            new=AsyncMock(return_value={}),
        ) as mock:
            await web.review_formalize(tmp_path, ["foo"], run_id="r1")
        mock.assert_awaited_once_with(
            tmp_path, ["foo"], emit, run_id="r1", storage=storage
        )

    @pytest.mark.asyncio
    async def test_get_env_spec_passes_emit(self):
        emit = AsyncMock()
        web = WebFeedback(emit)
        with patch(
            "decisionlab.web_feedback.get_env_spec",
            new=AsyncMock(return_value=Path("/x")),
        ) as mock:
            await web.get_env_spec()
        mock.assert_awaited_once_with(emit)

    @pytest.mark.asyncio
    async def test_review_build_passes_emit(self, tmp_path):
        emit = AsyncMock()
        web = WebFeedback(emit)
        with patch(
            "decisionlab.web_feedback.review_build",
            new=AsyncMock(return_value=([], [], [])),
        ) as mock:
            await web.review_build(tmp_path, {})
        mock.assert_awaited_once_with(tmp_path, {}, emit)


# ---------------------------------------------------------------------------
# AutoApproveFeedback
# ---------------------------------------------------------------------------


class TestAutoApproveResearch:
    @pytest.mark.asyncio
    async def test_returns_all_discovered_slugs_sorted_from_local(self, tmp_path):
        _make_research_dir(tmp_path, ["beta", "alpha", "gamma"])
        auto = AutoApproveFeedback()
        approved, additional = await auto.review_research(tmp_path, run_id="r1")
        assert approved == ["alpha", "beta", "gamma"]
        assert additional is None

    @pytest.mark.asyncio
    async def test_falls_back_to_s3_when_local_empty(self, tmp_path):
        async def fake_list(prefix):
            assert prefix == "research/run-x/deep/"
            return [
                "research/run-x/deep/zeta.md",
                "research/run-x/deep/alpha.md",
                "research/run-x/deep/ignored.txt",
            ]

        storage = type("S", (), {"list": staticmethod(fake_list)})()
        auto = AutoApproveFeedback(storage=storage)
        approved, additional = await auto.review_research(tmp_path, run_id="run-x")
        assert approved == ["alpha", "zeta"]
        assert additional is None

    @pytest.mark.asyncio
    async def test_missing_deep_dir_and_s3_failure_returns_empty(self, tmp_path):
        async def fake_list(prefix):
            raise RuntimeError("S3 unreachable")

        storage = type("S", (), {"list": staticmethod(fake_list)})()
        auto = AutoApproveFeedback(storage=storage)
        approved, additional = await auto.review_research(tmp_path, run_id="r1")
        assert approved == []
        assert additional is None

    @pytest.mark.asyncio
    async def test_filters_and_limits_discovered_slugs(self, tmp_path):
        _make_research_dir(
            tmp_path,
            ["optimal-foraging-theory", "reinforcement-learning", "prospect-theory"],
        )
        auto = AutoApproveFeedback(
            approved_paradigms=[
                "reinforcement-learning",
                "optimal-foraging-theory",
            ],
            max_paradigms=1,
        )
        approved, additional = await auto.review_research(tmp_path, run_id="r1")
        assert approved == ["reinforcement-learning"]
        assert additional is None

    @pytest.mark.asyncio
    async def test_synthesizes_missing_allowlisted_deep_report_from_summary(
        self, tmp_path
    ):
        writes: dict[str, str] = {}

        async def fake_list(prefix):
            assert prefix == "research/run-x/deep/"
            return ["research/run-x/deep/optimal-foraging-theory.md"]

        async def fake_get_text(key):
            assert key == "research/run-x/report.md"
            return "# Summary\n\nQ-learning belongs to reinforcement learning."

        async def fake_put_text(key, text):
            writes[key] = text

        storage = type(
            "S",
            (),
            {
                "list": staticmethod(fake_list),
                "get_text": staticmethod(fake_get_text),
                "put_text": staticmethod(fake_put_text),
            },
        )()
        auto = AutoApproveFeedback(
            storage=storage,
            approved_paradigms=[
                "reinforcement-learning",
                "optimal-foraging-theory",
            ],
        )
        approved, additional = await auto.review_research(tmp_path, run_id="run-x")
        assert approved == ["reinforcement-learning", "optimal-foraging-theory"]
        assert additional is None
        key = "research/run-x/deep/reinforcement-learning.md"
        assert key in writes
        assert "Q-learning belongs to reinforcement learning" in writes[key]


class TestAutoApproveFormalize:
    @pytest.mark.asyncio
    async def test_returns_all_formulation_numbers(self, tmp_path):
        sample = (
            "Some preamble.\n\n"
            "## Formulation 1: First\nbody1\n\n"
            "## Formulation 2: Second\nbody2\n"
        )

        async def fake_get_text(_key):
            return sample

        storage = type("S", (), {"get_text": staticmethod(fake_get_text)})()
        auto = AutoApproveFeedback(storage=storage)
        result = await auto.review_formalize(tmp_path, ["foo"], run_id="r1")
        assert result == {"foo": [1, 2]}

    @pytest.mark.asyncio
    async def test_missing_file_yields_empty_list(self, tmp_path):
        async def fake_get_text(key):
            raise FileNotFoundError(key)

        storage = type("S", (), {"get_text": staticmethod(fake_get_text)})()
        auto = AutoApproveFeedback(storage=storage)
        result = await auto.review_formalize(tmp_path, ["missing"], run_id="r1")
        assert result == {"missing": []}

    @pytest.mark.asyncio
    async def test_limits_formulations_per_paradigm(self, tmp_path):
        sample = (
            "## Formulation 1: First\n"
            "## Formulation 2: Second\n"
            "## Formulation 3: Third\n"
        )

        async def fake_get_text(_key):
            return sample

        storage = type("S", (), {"get_text": staticmethod(fake_get_text)})()
        auto = AutoApproveFeedback(
            storage=storage,
            max_formulations_per_paradigm=2,
        )
        result = await auto.review_formalize(tmp_path, ["foo"], run_id="r1")
        assert result == {"foo": [1, 2]}


class TestAutoApproveEnvSpec:
    @pytest.mark.asyncio
    async def test_returns_path_when_valid(self, tmp_path):
        env = tmp_path / "env.json"
        env.write_text(json.dumps({"width": 5, "height": 5}))
        auto = AutoApproveFeedback(env_spec_path=env)
        assert await auto.get_env_spec() == env

    @pytest.mark.asyncio
    async def test_raises_when_no_path_set(self):
        auto = AutoApproveFeedback()
        with pytest.raises(RuntimeError, match="env_spec_path"):
            await auto.get_env_spec()

    @pytest.mark.asyncio
    async def test_raises_when_path_missing(self, tmp_path):
        auto = AutoApproveFeedback(env_spec_path=tmp_path / "nope.json")
        with pytest.raises(FileNotFoundError):
            await auto.get_env_spec()

    @pytest.mark.asyncio
    async def test_raises_when_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{")
        auto = AutoApproveFeedback(env_spec_path=bad)
        with pytest.raises(RuntimeError, match="not valid JSON"):
            await auto.get_env_spec()


class TestAutoApproveReason:
    @pytest.mark.asyncio
    async def test_falls_back_to_s3_reasoner_specs(self, tmp_path):
        objects = {
            "models/run-x/reasoner/rl/q-learning.json": json.dumps(
                {"formulation_id": "q-learning", "status": "valid"}
            ),
            "models/run-x/reasoner/oft/foraging.json": json.dumps(
                {"formulation_id": "foraging"}
            ),
        }

        async def fake_list(prefix):
            assert prefix == "models/run-x/reasoner/"
            return [
                "models/run-x/reasoner/rl/q-learning.json",
                "models/run-x/reasoner/oft/foraging.json",
                "models/run-x/reasoner/ignored.txt",
            ]

        async def fake_get_text(key):
            return objects[key]

        storage = type(
            "S",
            (),
            {
                "list": staticmethod(fake_list),
                "get_text": staticmethod(fake_get_text),
            },
        )()
        auto = AutoApproveFeedback(storage=storage, run_id="run-x")
        approved, rejections, reruns = await auto.review_reason(tmp_path)
        assert approved == ["foraging", "q-learning"]
        assert rejections == []
        assert reruns == []

    @pytest.mark.asyncio
    async def test_s3_reasoner_fallback_skips_invalid_specs(self, tmp_path):
        objects = {
            "models/run-x/reasoner/rl/ok.json": json.dumps(
                {"formulation_id": "ok", "status": "valid"}
            ),
            "models/run-x/reasoner/rl/bad.json": json.dumps(
                {"formulation_id": "bad", "status": "invalid"}
            ),
        }

        async def fake_list(_prefix):
            return list(objects)

        async def fake_get_text(key):
            return objects[key]

        storage = type(
            "S",
            (),
            {
                "list": staticmethod(fake_list),
                "get_text": staticmethod(fake_get_text),
            },
        )()
        auto = AutoApproveFeedback(storage=storage, run_id="run-x")
        approved, rejections, reruns = await auto.review_reason(tmp_path)
        assert approved == ["ok"]
        assert rejections == []
        assert reruns == []

    @pytest.mark.asyncio
    async def test_skips_invalid_specs_keeps_valid(self, tmp_path):
        _make_reasoner_dir(
            tmp_path,
            [
                {"formulation_id": "ok-a", "status": "valid"},
                {"formulation_id": "bad-b", "status": "invalid"},
                {"formulation_id": "ok-c"},  # no status field → keep
            ],
        )
        auto = AutoApproveFeedback()
        approved, rejections, reruns = await auto.review_reason(tmp_path)
        assert sorted(approved) == ["ok-a", "ok-c"]
        assert rejections == []
        assert reruns == []

    @pytest.mark.asyncio
    async def test_missing_reasoner_dir_returns_empty(self, tmp_path):
        auto = AutoApproveFeedback()
        approved, _, _ = await auto.review_reason(tmp_path)
        assert approved == []


class TestAutoApproveBuild:
    @pytest.mark.asyncio
    async def test_always_returns_empty_tuple(self, tmp_path):
        auto = AutoApproveFeedback()
        approved, rejections, reruns = await auto.review_build(tmp_path, {"a": "ok"})
        assert approved == []
        assert rejections == []
        assert reruns == []
