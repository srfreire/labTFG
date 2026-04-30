from decisionlab.domain.models import SearchResult
from decisionlab.domain.ports import WebSearchPort


class FakeSearch:
    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(title="T", url="http://x", snippet="S")]


def test_fake_search_satisfies_web_search_port():
    assert isinstance(FakeSearch(), WebSearchPort)
