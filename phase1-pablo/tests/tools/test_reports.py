import pytest

from decisionlab.router import PipelineState, Stage
from decisionlab.tools.reports import (
    READ_REPORT_SCHEMA,
    slugify,
    create_read_report,
    generate_tree_map,
    save_deep_report,
    save_summary_report,
)


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


def test_save_deep_report(tmp_path):
    path = save_deep_report(tmp_path, "Homeostatic regulation", "# Report content")
    assert path.exists()
    assert path.name == "homeostatic-regulation.md"
    assert "Report content" in path.read_text()


def test_save_summary_report(tmp_path):
    path = save_summary_report(tmp_path, "# Summary")
    assert path.exists()
    assert path.name == "report.md"
    assert "Summary" in path.read_text()


@pytest.mark.asyncio
async def test_read_report_returns_content(tmp_path):
    save_deep_report(tmp_path, "Homeostatic regulation", "# Full report content")
    fn = create_read_report(tmp_path)
    result = await fn({"paradigm": "Homeostatic regulation"})
    assert "Full report content" in result


@pytest.mark.asyncio
async def test_read_report_missing_file(tmp_path):
    fn = create_read_report(tmp_path)
    result = await fn({"paradigm": "nonexistent"})
    assert "No report found" in result


@pytest.mark.asyncio
async def test_read_report_missing_param(tmp_path):
    fn = create_read_report(tmp_path)
    with pytest.raises(ValueError, match="paradigm"):
        await fn({})


# ---------------------------------------------------------------------------
# generate_tree_map tests
# ---------------------------------------------------------------------------


def _make_state(tmp_path, paradigms, formulations=None):
    """Helper: create PipelineState with paradigm/formulation IDs and deep report files."""
    state = PipelineState(
        stage=Stage.REVIEW_FORMALIZE, problem="test", reports_dir=tmp_path,
    )
    deep_dir = tmp_path / "deep"
    deep_dir.mkdir(parents=True, exist_ok=True)
    for slug, title in paradigms:
        state.assign_paradigm_id(slug)
        (deep_dir / f"{slug}.md").write_text(f"# {title} — Deep Research\n\nContent...")
    for slug, name in (formulations or []):
        state.assign_formulation_id(slug, name)
    return state


class TestGenerateTreeMap:
    def test_single_paradigm_no_formulations(self, tmp_path):
        state = _make_state(tmp_path, [("homeostatic-regulation", "Homeostatic Regulation")])
        save_summary_report(tmp_path, "# Report\n\nSome content.")

        tree = generate_tree_map(state)

        assert "T01: " in tree
        assert "T01-P01: Homeostatic Regulation" in tree

    def test_paradigm_with_formulations(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation")],
            [("homeostatic-regulation", "PI Controller"), ("homeostatic-regulation", "Dual-Process Model")],
        )
        save_summary_report(tmp_path, "# Report\n\nSome content.")

        tree = generate_tree_map(state)

        assert "T01-P01-F01: PI Controller" in tree
        assert "T01-P01-F02: Dual-Process Model" in tree

    def test_multiple_paradigms_with_formulations(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation"), ("hedonic-reward", "Hedonic Reward")],
            [
                ("homeostatic-regulation", "PI Controller"),
                ("homeostatic-regulation", "Dual-Process Model"),
                ("hedonic-reward", "Temporal Difference"),
            ],
        )
        save_summary_report(tmp_path, "# Report\n\nSome content.")

        tree = generate_tree_map(state)

        assert "├──" in tree or "└──" in tree
        assert "T01-P01: Homeostatic Regulation" in tree
        assert "T01-P02: Hedonic Reward" in tree
        assert "T01-P01-F01: PI Controller" in tree
        assert "T01-P02-F01: Temporal Difference" in tree

    def test_tree_map_inserted_into_report(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation")],
            [("homeostatic-regulation", "PI Controller")],
        )
        save_summary_report(tmp_path, "# Report\n\nSome content.")

        generate_tree_map(state)

        report = (tmp_path / "report.md").read_text()
        assert "## Research Tree Map" in report
        assert "Some content." in report  # original content preserved

    def test_tree_map_replaced_on_rerun(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation")],
            [("homeostatic-regulation", "PI Controller")],
        )
        save_summary_report(tmp_path, "# Report\n\nSome content.")

        generate_tree_map(state)
        # Add a new formulation (simulating rerun)
        state.assign_formulation_id("homeostatic-regulation", "New Model")
        generate_tree_map(state)

        report = (tmp_path / "report.md").read_text()
        assert report.count("## Research Tree Map") == 1
        assert "T01-P01-F02: New Model" in report
        assert "T01-P01-F01: PI Controller" in report  # original formulation still present

    def test_tree_uses_correct_characters(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("paradigm-a", "Paradigm A"), ("paradigm-b", "Paradigm B")],
            [("paradigm-a", "F1"), ("paradigm-b", "F1")],
        )
        save_summary_report(tmp_path, "# Report")

        tree = generate_tree_map(state)

        # First paradigm uses ├── (not last), second uses └── (last)
        lines = tree.strip().split("\n")
        paradigm_lines = [line for line in lines if "T01-P0" in line and "F0" not in line]
        assert "├──" in paradigm_lines[0]
        assert "└──" in paradigm_lines[1]

    def test_paradigm_name_fallback_to_slug(self, tmp_path):
        """If deep report doesn't exist, fall back to slug."""
        state = PipelineState(
            stage=Stage.REVIEW_FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("unknown-paradigm")
        save_summary_report(tmp_path, "# Report")

        tree = generate_tree_map(state)

        assert "T01-P01: unknown-paradigm" in tree

    def test_empty_registry(self, tmp_path):
        state = PipelineState(
            stage=Stage.REVIEW_FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        save_summary_report(tmp_path, "# Report")

        tree = generate_tree_map(state)

        assert "T01" in tree  # At least topic level

    def test_no_report_file_creates_one(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation")],
            [("homeostatic-regulation", "PI Controller")],
        )
        # Don't call save_summary_report — report.md doesn't exist

        generate_tree_map(state)

        report_path = tmp_path / "report.md"
        assert report_path.exists()
        report = report_path.read_text()
        assert "## Research Tree Map" in report
        assert "T01-P01-F01: PI Controller" in report

    def test_replacement_preserves_following_sections(self, tmp_path):
        state = _make_state(
            tmp_path,
            [("homeostatic-regulation", "Homeostatic Regulation")],
            [("homeostatic-regulation", "PI Controller")],
        )
        save_summary_report(tmp_path, "# Report\n\nContent.")

        generate_tree_map(state)
        # Simulate a section added after tree map
        report_path = tmp_path / "report.md"
        content = report_path.read_text()
        report_path.write_text(content + "\n## References\n\nSome refs.\n")

        # Re-generate tree map — should not eat the References section
        state.assign_formulation_id("homeostatic-regulation", "New Model")
        generate_tree_map(state)

        report = report_path.read_text()
        assert "## References" in report
        assert "Some refs." in report
        assert "T01-P01-F02: New Model" in report
