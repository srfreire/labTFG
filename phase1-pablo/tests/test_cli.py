"""Smoke tests for the decisionlab Typer CLI app.

These don't actually call the LLM — they verify command wiring (`--help`),
argument parsing, and the error-handling helpers in cli._run_async.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import anthropic
import pytest
from typer.testing import CliRunner

from decisionlab import cli

if TYPE_CHECKING:
    from pathlib import Path

# Force a wide terminal width so rich-rendered help output never wraps option
# names off-screen — keeps the substring assertions below stable across local
# TTYs and CI's 80-column default.
runner = CliRunner(env={"COLUMNS": "200"})


def test_app_exposes_expected_commands():
    """The CLI registers all top-level commands."""
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for cmd in (
        "research",
        "deep-research",
        "formalize",
        "reason",
        "build",
        "run",
        "resume",
    ):
        assert cmd in out


def test_research_help_lists_arguments():
    result = runner.invoke(cli.app, ["research", "--help"])
    assert result.exit_code == 0
    assert "--verbose" in result.stdout
    assert "PROBLEM" in result.stdout.upper() or "problem" in result.stdout


def test_formalize_requires_reports_dir():
    """formalize raises when --reports-dir is missing."""
    result = runner.invoke(cli.app, ["formalize"])
    assert result.exit_code != 0


def test_formalize_errors_when_deep_dir_missing(tmp_path: Path):
    """formalize prints an error and exits non-zero when deep/ is absent."""
    result = runner.invoke(
        cli.app,
        ["formalize", "--reports-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "deep/" in result.stdout


def test_reason_errors_when_formulations_missing(tmp_path: Path):
    spec = tmp_path / "env.json"
    spec.write_text("{}")
    result = runner.invoke(
        cli.app,
        [
            "reason",
            "--reports-dir",
            str(tmp_path),
            "--env-spec",
            str(spec),
        ],
    )
    assert result.exit_code == 1
    assert "formulations" in result.stdout


def test_reason_errors_when_env_spec_missing(tmp_path: Path):
    (tmp_path / "formulations").mkdir()
    result = runner.invoke(
        cli.app,
        [
            "reason",
            "--reports-dir",
            str(tmp_path),
            "--env-spec",
            str(tmp_path / "missing.json"),
        ],
    )
    assert result.exit_code == 1
    assert "env_spec" in result.stdout


def test_build_errors_when_reasoner_missing(tmp_path: Path):
    result = runner.invoke(cli.app, ["build", "--reports-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "reasoner/" in result.stdout


def test_resume_requires_run_id_or_reports_dir():
    """resume errors out when neither --run-id nor --reports-dir is provided."""
    result = runner.invoke(cli.app, ["resume"])
    assert result.exit_code == 1
    assert "--reports-dir" in result.stdout or "--run-id" in result.stdout


def test_reports_dir_uses_today_date():
    """`_reports_dir` builds a path with today's ISO date prefix."""
    p = cli._reports_dir("hello world example problem here")
    assert p.name.startswith(date.today().isoformat())
    # First five slug words live in the directory name
    parts = p.name.split("-")
    assert "hello" in parts and "world" in parts


def test_reports_dir_truncates_to_five_words():
    p = cli._reports_dir("a b c d e f g")
    name_after_date = "-".join(p.name.split("-")[3:])  # date prefix is YYYY-MM-DD
    assert name_after_date.split("-") == ["a", "b", "c", "d", "e"]


def test_run_async_handles_authentication_error():
    """_run_async catches anthropic.AuthenticationError and exits 1."""
    import httpx

    async def _boom():
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(401, request=request)
        raise anthropic.AuthenticationError(
            message="bad", response=response, body={"error": "x"}
        )

    import typer

    with pytest.raises(typer.Exit) as exc_info:
        cli._run_async(_boom())
    assert exc_info.value.exit_code == 1


def test_run_async_handles_connection_error():
    """_run_async catches APIConnectionError and exits 1."""
    import httpx

    async def _boom():
        request = httpx.Request("GET", "http://test")
        raise anthropic.APIConnectionError(request=request)

    import typer

    with pytest.raises(typer.Exit) as exc_info:
        cli._run_async(_boom())
    assert exc_info.value.exit_code == 1


def test_run_async_handles_runtime_error():
    """_run_async catches RuntimeError and exits 1."""

    async def _boom():
        raise RuntimeError("bad state")

    import typer

    with pytest.raises(typer.Exit) as exc_info:
        cli._run_async(_boom())
    assert exc_info.value.exit_code == 1


def test_run_async_returns_value_on_success():
    """_run_async returns the coroutine's value on the happy path."""

    async def _ok():
        return 42

    assert cli._run_async(_ok()) == 42
