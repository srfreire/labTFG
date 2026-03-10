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
async def test_mock_paper_fetch_returns_paper():
    adapter = MockPaperSearch()
    paper = await adapter.fetch("paper123")
    assert paper.paper_id == "paper123"
