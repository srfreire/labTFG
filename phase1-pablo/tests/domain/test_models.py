import pytest

from decisionlab.domain.models import SearchResult, PaperResult, Paradigm, ResearchReport


def test_search_result_creation():
    r = SearchResult(title="Homeostatic regulation", url="https://example.com", snippet="A model of...")
    assert r.title == "Homeostatic regulation"
    assert r.url == "https://example.com"


def test_paper_result_creation():
    p = PaperResult(
        paper_id="abc123",
        title="A predictive model",
        abstract="We present...",
        authors=("Jacquier", "Alvarez"),
        year=2014,
    )
    assert p.paper_id == "abc123"
    assert len(p.authors) == 2


def test_paradigm_creation():
    paper = PaperResult(paper_id="1", title="T", abstract="A", authors=("X",), year=2020)
    p = Paradigm(id="homeostatic", name="Homeostatic model", description="Desc", references=(paper,))
    assert p.id == "homeostatic"
    assert len(p.references) == 1


def test_research_report_creation():
    paradigm = Paradigm(id="h", name="H", description="D", references=())
    report = ResearchReport(
        paradigms=[paradigm],
        summary="# Summary",
        deep_reports={"h": "# Deep report"},
    )
    assert len(report.paradigms) == 1
    assert "h" in report.deep_reports


def test_frozen_dataclasses_are_immutable():
    r = SearchResult(title="T", url="U", snippet="S")
    with pytest.raises(AttributeError):
        r.title = "X"

    p = PaperResult(paper_id="1", title="T", abstract="A", authors=("X",), year=2020)
    with pytest.raises(AttributeError):
        p.title = "Y"
