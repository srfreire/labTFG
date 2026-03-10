from decisionlab.domain.ports import WebSearchPort
from decisionlab.domain.models import SearchResult


class FakeSearch:
    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(title="T", url="http://x", snippet="S")]


def test_fake_search_satisfies_web_search_port():
    assert isinstance(FakeSearch(), WebSearchPort)
