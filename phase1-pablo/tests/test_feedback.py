"""Tests for non-interactive helpers in decisionlab.feedback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from decisionlab.feedback import _discover_paradigm_slugs

if TYPE_CHECKING:
    from pathlib import Path


def test_discover_paradigm_slugs_returns_sorted(tmp_path: Path):
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "homeostatic.md").write_text("x")
    (deep / "hedonic.md").write_text("x")
    (deep / "actor-critic.md").write_text("x")
    slugs = _discover_paradigm_slugs(tmp_path)
    assert slugs == ["actor-critic", "hedonic", "homeostatic"]


def test_discover_paradigm_slugs_returns_empty_when_no_dir(tmp_path: Path):
    assert _discover_paradigm_slugs(tmp_path) == []


def test_discover_paradigm_slugs_ignores_non_md(tmp_path: Path):
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "homeostatic.md").write_text("x")
    (deep / "notes.txt").write_text("x")
    (deep / "config.yaml").write_text("x")
    assert _discover_paradigm_slugs(tmp_path) == ["homeostatic"]


def test_discover_paradigm_slugs_strips_extension(tmp_path: Path):
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "abc.md").write_text("x")
    assert _discover_paradigm_slugs(tmp_path) == ["abc"]


def test_discover_paradigm_slugs_with_file_at_root_returns_empty(tmp_path: Path):
    """A non-directory `deep` doesn't crash — returns empty."""
    (tmp_path / "deep").write_text("not a dir")
    assert _discover_paradigm_slugs(tmp_path) == []
