import pytest

from decisionlab.tools.reports import (
    READ_REPORT_SCHEMA,
    _slugify,
    create_read_report,
    save_deep_report,
    save_summary_report,
)


def test_read_report_schema_has_required_fields():
    assert READ_REPORT_SCHEMA["name"] == "read_report"
    assert "paradigm" in READ_REPORT_SCHEMA["input_schema"]["properties"]


def test_slugify():
    assert _slugify("Homeostatic regulation") == "homeostatic-regulation"
    assert _slugify("Q-Learning / RL") == "q-learning---rl"


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
