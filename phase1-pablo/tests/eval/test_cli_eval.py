"""Smoke tests for ``decisionlab eval`` and ``decisionlab kg`` CLI surfaces.

These are help/parsing tests: we don't need infra to run them. Real
end-to-end CLI runs that hit Neo4j/Anthropic are integration-marked
and live elsewhere.

Note on CI flakiness: typer renders help via rich, which wraps long
flags (``--stages``, ``--env-spec``) across physical lines when
``COLUMNS`` is narrow. CI runners default to 80 columns and split the
literal flag string, breaking the substring asserts. ``_HELP_ENV`` pins
a wide terminal and disables color so the help output is plain enough
to substring-match reliably.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from typer.testing import CliRunner

from decisionlab.cli import app
from decisionlab.cli_eval import _parse_duration

runner = CliRunner()

_HELP_ENV: dict[str, str] = {
    "COLUMNS": "200",
    "NO_COLOR": "1",
    "TERM": "dumb",
}


class TestTopLevelHelp:
    def test_eval_subcommand_appears(self):
        result = runner.invoke(app, ["--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        assert "eval" in result.stdout
        assert "kg" in result.stdout


class TestEvalHelp:
    def test_eval_root_help(self):
        result = runner.invoke(app, ["eval", "--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        for cmd in ("run", "topics", "pipeline"):
            assert cmd in result.stdout

    def test_eval_run_help(self):
        result = runner.invoke(app, ["eval", "run", "--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        assert "--stages" in result.stdout
        assert "--no-reset" in result.stdout

    def test_eval_topics_help(self):
        result = runner.invoke(app, ["eval", "topics", "--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        assert "--env-spec" in result.stdout

    def test_eval_prune_help(self):
        result = runner.invoke(app, ["eval", "prune", "--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        assert "--older-than" in result.stdout
        assert "--dry-run" in result.stdout

    def test_eval_prune_rejects_invalid_duration(self):
        # Bad duration short-circuits with exit code 2 before infra init.
        result = runner.invoke(app, ["eval", "prune", "--older-than", "two weeks"])
        assert result.exit_code == 2
        assert (
            "invalid duration" in result.stdout.lower()
            or "invalid duration" in (result.stderr or "").lower()
        )

    def test_eval_pipeline_rejects_reason_without_env_spec(self):
        # The CLI does its own pre-flight validation before calling shared.init,
        # so this short-circuits with exit code 2 even without infra.
        result = runner.invoke(
            app, ["eval", "pipeline", "topic", "--stages", "research,formalize,reason"]
        )
        assert result.exit_code == 2
        assert (
            "env-spec" in result.stdout.lower()
            or "env-spec" in (result.stderr or "").lower()
        )


class TestKGHelp:
    def test_kg_root_help(self):
        result = runner.invoke(app, ["kg", "--help"], env=_HELP_ENV)
        assert result.exit_code == 0
        for cmd in ("stats", "reset", "snapshot", "restore", "query"):
            assert cmd in result.stdout

    def test_kg_reset_requires_confirm(self):
        result = runner.invoke(app, ["kg", "reset"])
        assert result.exit_code == 2
        assert (
            "confirm" in result.stdout.lower()
            or "confirm" in (result.stderr or "").lower()
        )

    def test_kg_query_bad_param_format(self):
        # `-p foo` (no =) should fail before infra init.
        result = runner.invoke(app, ["kg", "query", "MATCH (n) RETURN n", "-p", "foo"])
        assert result.exit_code == 2


class TestParseDuration:
    """``_parse_duration`` accepts compact strings and rejects everything else.

    Backs ``cli_eval prune --older-than`` (P3-003 AC4).
    """

    def test_days(self):
        assert _parse_duration("30d") == timedelta(days=30)

    def test_hours(self):
        assert _parse_duration("24h") == timedelta(hours=24)

    def test_minutes(self):
        assert _parse_duration("60m") == timedelta(minutes=60)

    def test_strips_whitespace(self):
        assert _parse_duration(" 7d ") == timedelta(days=7)

    @pytest.mark.parametrize(
        "bad", ["", "0d", "-1d", "1d12h", "abc", "30", "30s", "1y"]
    )
    def test_rejects_garbage(self, bad):
        with pytest.raises(ValueError):
            _parse_duration(bad)
