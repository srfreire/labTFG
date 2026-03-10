import pytest

from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.domain.ports import WebSearchPort, PaperSearchPort


def test_mock_web_search_satisfies_port():
    assert isinstance(MockWebSearch(), WebSearchPort)


def test_mock_paper_search_satisfies_port():
    assert isinstance(MockPaperSearch(), PaperSearchPort)


@pytest.mark.asyncio
async def test_mock_web_search_returns_results():
    adapter = MockWebSearch()
    results = await adapter.search("test query")
    assert len(results) > 0
    assert results[0].title


@pytest.mark.asyncio
async def test_mock_paper_search_returns_results():
    adapter = MockPaperSearch()
    results = await adapter.search("test query")
    assert len(results) > 0


@pytest.mark.asyncio
async def test_mock_paper_search_respects_limit():
    adapter = MockPaperSearch()
    results = await adapter.search("test", limit=1)
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_mock_paper_fetch_returns_known_paper():
    adapter = MockPaperSearch()
    paper = await adapter.fetch("jacquier2014")
    assert paper.paper_id == "jacquier2014"
    assert "predictive model" in paper.title.lower()
    assert paper.year == 2014


@pytest.mark.asyncio
async def test_mock_paper_fetch_raises_on_unknown_id():
    adapter = MockPaperSearch()
    with pytest.raises(KeyError, match="paper123"):
        await adapter.fetch("paper123")
