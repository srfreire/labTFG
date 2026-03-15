import pytest

from decisionlab.domain.models import SearchResult, Paradigm, ResearchReport, FormalizationReport


def test_search_result_creation():
    r = SearchResult(title="Homeostatic regulation", url="https://example.com", snippet="A model of...")
    assert r.title == "Homeostatic regulation"
    assert r.url == "https://example.com"


def test_paradigm_creation():
    p = Paradigm(id="homeostatic", name="Homeostatic model", description="Desc")
    assert p.id == "homeostatic"


def test_research_report_creation():
    paradigm = Paradigm(id="h", name="H", description="D")
    report = ResearchReport(
        paradigms=[paradigm],
        summary="# Summary",
        deep_reports={"h": "# Deep report"},
    )
    assert len(report.paradigms) == 1
    assert "h" in report.deep_reports


def test_formalization_report_creation():
    report = FormalizationReport(formulations={"homeostatic": "# Formulation"})
    assert "homeostatic" in report.formulations
    assert report.formulations["homeostatic"] == "# Formulation"


def test_formalization_report_is_frozen():
    report = FormalizationReport(formulations={"a": "b"})
    with pytest.raises(AttributeError):
        report.formulations = {}


def test_frozen_dataclasses_are_immutable():
    r = SearchResult(title="T", url="U", snippet="S")
    with pytest.raises(AttributeError):
        r.title = "X"
