import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.domain.ports import WebSearchPort


def test_mock_web_search_satisfies_port():
    assert isinstance(MockWebSearch(), WebSearchPort)


@pytest.mark.asyncio
async def test_mock_web_search_returns_results():
    adapter = MockWebSearch()
    results = await adapter.search("test query")
    assert len(results) > 0
    assert results[0].title
