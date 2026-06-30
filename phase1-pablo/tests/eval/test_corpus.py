from __future__ import annotations

import zipfile

import pytest

from decisionlab.eval import corpus as corpus_mod
from decisionlab.eval.corpus import EvalPaperCorpus


def _zip_with_pdf(path, filename="paper.pdf"):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(filename, b"%PDF fake")


@pytest.mark.asyncio
async def test_loads_zip_and_web_searches_only_corpus(monkeypatch, tmp_path):
    archive = tmp_path / "case.zip"
    _zip_with_pdf(archive, "dietary_choice_2013.pdf")

    monkeypatch.setattr(
        corpus_mod,
        "_extract_pdf_text",
        lambda _path: (
            "Abstract Human dietary choice depends on valuation and self-control. "
            "Rangel describes value computation for food decisions."
        ),
    )

    corpus = EvalPaperCorpus.from_archives([archive], cache_root=tmp_path / "cache")

    assert len(corpus.papers) == 1
    assert corpus.papers[0].source_archive == "case.zip"

    results = await corpus.web_search().search("dietary valuation")
    assert len(results) == 1
    assert results[0].url.startswith("eval-corpus://")
    assert "Corpus-only PDF result" in results[0].snippet


@pytest.mark.asyncio
async def test_search_papers_returns_document_text(monkeypatch, tmp_path):
    archive = tmp_path / "case.zip"
    _zip_with_pdf(archive)
    text = "Abstract Homeostatic reinforcement learning links reward and set points. "

    monkeypatch.setattr(corpus_mod, "_extract_pdf_text", lambda _path: text * 20)

    corpus = EvalPaperCorpus.from_archives([archive], cache_root=tmp_path / "cache")
    search_papers = corpus.create_search_papers(max_chars_per_paper=120)

    out = await search_papers({"query": "homeostatic reinforcement", "limit": 1})

    assert "Text excerpt:" in out
    assert "Homeostatic reinforcement learning" in out
    assert "excerpt truncated after 120 characters" in out


@pytest.mark.asyncio
async def test_search_papers_default_returns_top_match_only(monkeypatch, tmp_path):
    archive = tmp_path / "case.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("dietary.pdf", b"%PDF fake")
        zf.writestr("interoception.pdf", b"%PDF fake")

    def fake_text(path):
        if path.name == "dietary.pdf":
            return (
                "Abstract Dietary choice depends on tastiness, healthiness, "
                "valuation, and self-control. "
            )
        return (
            "Abstract Interoception and body regulation explain physiological control. "
        )

    monkeypatch.setattr(corpus_mod, "_extract_pdf_text", fake_text)

    corpus = EvalPaperCorpus.from_archives([archive], cache_root=tmp_path / "cache")
    search_papers = corpus.create_search_papers(max_chars_per_paper=200)

    out = await search_papers({"query": "dietary valuation self-control"})

    assert "**Dietary**" in out or "**Dietary.Pdf**" in out
    assert "interoception" not in out.lower()


def test_export_to_copies_manifest_and_sources(monkeypatch, tmp_path):
    archive = tmp_path / "case.zip"
    _zip_with_pdf(archive)
    monkeypatch.setattr(corpus_mod, "_extract_pdf_text", lambda _path: "Abstract x")

    corpus = EvalPaperCorpus.from_archives([archive], cache_root=tmp_path / "cache")
    manifest = corpus.export_to(tmp_path / "bundle")

    assert manifest.exists()
    assert list((tmp_path / "bundle" / "pdfs").glob("*.pdf"))
    assert list((tmp_path / "bundle" / "texts").glob("*.txt"))
