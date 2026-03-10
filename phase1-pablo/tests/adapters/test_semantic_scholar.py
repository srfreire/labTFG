import pytest

from decisionlab.adapters.semantic_scholar import SemanticScholarAdapter
from decisionlab.domain.ports import PaperSearchPort


def test_satisfies_port():
    assert isinstance(SemanticScholarAdapter(), PaperSearchPort)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_search_returns_papers():
    adapter = SemanticScholarAdapter()
    results = await adapter.search("homeostatic food intake model", limit=3)
    assert len(results) > 0
    assert results[0].title


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_fetch_returns_paper():
    adapter = SemanticScholarAdapter()
    results = await adapter.search("Jacquier predictive model body weight", limit=1)
    if results:
        paper = await adapter.fetch(results[0].paper_id)
        assert paper.title
