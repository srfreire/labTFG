import pytest

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.domain.ports import WebSearchPort


def test_satisfies_port():
    assert isinstance(DuckDuckGoAdapter(), WebSearchPort)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_search_returns_results():
    adapter = DuckDuckGoAdapter()
    results = await adapter.search("homeostatic regulation food intake")
    assert len(results) > 0
    assert results[0].title
    assert results[0].url
