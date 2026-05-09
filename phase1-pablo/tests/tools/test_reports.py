"""Tests for reports tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.router import PipelineState, Stage
from decisionlab.tools.reports import (
    READ_REPORT_SCHEMA,
    create_read_report,
    generate_tree_map,
    slugify,
)
from shared.services import Services


def test_read_report_schema_has_required_fields():
    assert READ_REPORT_SCHEMA["name"] == "read_report"
    assert "paradigm" in READ_REPORT_SCHEMA["input_schema"]["properties"]


def test_slugify():
    assert slugify("Homeostatic regulation") == "homeostatic-regulation"
    assert slugify("Q-Learning / RL") == "q-learning-rl"
    assert slugify("Drive: Theory") == "drive-theory"
    assert slugify("a   b") == "a-b"
    assert slugify("") == ""
    assert slugify("/ leading /") == "leading"


def _make_storage_mock(files: dict[str, str] | None = None) -> MagicMock:
    """Build a mock StorageService backed by a key→content dict."""
    files = files or {}
    storage = MagicMock()
    storage.exists = AsyncMock(side_effect=lambda k: k in files)

    async def _get_text(k):
        if k not in files:
            raise FileNotFoundError(k)
        return files[k]

    storage.get_text = AsyncMock(side_effect=_get_text)
    storage.put_text = AsyncMock()
    return storage


def _make_services(*, storage=None, db=None) -> Services:
    return Services(
        db=db or MagicMock(),
        storage=storage or MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )


@pytest.mark.asyncio
async def test_read_report_missing_param(tmp_path):
    storage = _make_storage_mock({})
    fn = create_read_report("test-run", storage=storage)
    with pytest.raises(ValueError, match="paradigm"):
        await fn({})


# ---------------------------------------------------------------------------
# generate_tree_map tests
# ---------------------------------------------------------------------------


def _make_state(
    tmp_path,
    selected_formulations: dict[str, list[str]],
    problem: str = "test",
    run_id: str = "test-run",
):
    """Helper: create PipelineState with slug-based formulations."""
    return PipelineState(
        stage=Stage.REVIEW_FORMALIZE,
        problem=problem,
        reports_dir=tmp_path,
        run_id=run_id,
        selected_formulations=selected_formulations,
    )


class TestGenerateTreeMap:
    @pytest.mark.asyncio
    async def test_single_paradigm_no_formulations(self, tmp_path):
        state = _make_state(tmp_path, {"homeostatic-regulation": []})
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report\n\nSome content.",
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n\nContent...",
            }
        )
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        assert "Homeostatic Regulation" in tree

    @pytest.mark.asyncio
    async def test_paradigm_with_formulations(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "homeostatic-regulation": ["pi-controller", "dual-process-model"],
            },
        )
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report\n\nSome content.",
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n\nContent...",
            }
        )
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        assert "pi-controller" in tree
        assert "dual-process-model" in tree

    @pytest.mark.asyncio
    async def test_multiple_paradigms_with_formulations(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "hedonic-reward": ["temporal-difference"],
                "homeostatic-regulation": ["pi-controller"],
            },
        )
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report\n\nSome content.",
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n",
                "research/test-run/deep/hedonic-reward.md": "# Hedonic Reward — Deep Research\n",
            }
        )
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        assert "├──" in tree or "└──" in tree
        assert "Homeostatic Regulation" in tree
        assert "Hedonic Reward" in tree
        assert "pi-controller" in tree
        assert "temporal-difference" in tree

    @pytest.mark.asyncio
    async def test_tree_map_inserted_into_report(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "homeostatic-regulation": ["pi-controller"],
            },
        )
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report\n\nSome content.",
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n",
            }
        )
        services = _make_services(storage=storage)

        await generate_tree_map(state, services)

        storage.put_text.assert_called_once()
        written_content = storage.put_text.call_args[0][1]
        assert "## Research Tree Map" in written_content
        assert "Some content." in written_content

    @pytest.mark.asyncio
    async def test_tree_uses_correct_characters(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "paradigm-a": ["f1"],
                "paradigm-b": ["f1"],
            },
        )
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report",
                "research/test-run/deep/paradigm-a.md": "# Paradigm A — Deep Research\n",
                "research/test-run/deep/paradigm-b.md": "# Paradigm B — Deep Research\n",
            }
        )
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        lines = tree.strip().split("\n")
        paradigm_lines = [line for line in lines if "Paradigm" in line]
        assert "├──" in paradigm_lines[0]
        assert "└──" in paradigm_lines[1]

    @pytest.mark.asyncio
    async def test_paradigm_name_fallback_to_slug(self, tmp_path):
        """If deep report doesn't exist, fall back to slug."""
        state = _make_state(tmp_path, {"unknown-paradigm": []})
        files = {"research/test-run/report.md": "# Report"}
        storage = _make_storage_mock(files)
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        assert "unknown-paradigm" in tree

    @pytest.mark.asyncio
    async def test_empty_selected_formulations(self, tmp_path):
        state = _make_state(tmp_path, {})
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": "# Report",
            }
        )
        services = _make_services(storage=storage)

        tree = await generate_tree_map(state, services)

        assert "Report" in tree

    @pytest.mark.asyncio
    async def test_no_report_file_creates_one(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "homeostatic-regulation": ["pi-controller"],
            },
        )
        storage = _make_storage_mock(
            {
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n",
            }
        )
        services = _make_services(storage=storage)

        await generate_tree_map(state, services)

        storage.put_text.assert_called_once()
        written_content = storage.put_text.call_args[0][1]
        assert "## Research Tree Map" in written_content
        assert "pi-controller" in written_content

    @pytest.mark.asyncio
    async def test_replacement_preserves_following_sections(self, tmp_path):
        state = _make_state(
            tmp_path,
            {
                "homeostatic-regulation": ["pi-controller"],
            },
        )
        existing = (
            "# Report\n\nContent."
            "\n## Research Tree Map\n\n```\nold tree\n```\n"
            "\n## References\n\nSome refs.\n"
        )
        storage = _make_storage_mock(
            {
                "research/test-run/report.md": existing,
                "research/test-run/deep/homeostatic-regulation.md": "# Homeostatic Regulation — Deep Research\n",
            }
        )
        services = _make_services(storage=storage)

        await generate_tree_map(state, services)

        written_content = storage.put_text.call_args[0][1]
        assert "## References" in written_content
        assert "Some refs." in written_content
        assert "pi-controller" in written_content
        assert written_content.count("## Research Tree Map") == 1
