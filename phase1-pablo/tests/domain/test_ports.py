from decisionlab.domain.ports import WebSearchPort, PaperSearchPort
from decisionlab.domain.models import SearchResult, PaperResult


class FakeSearch:
    async def search(self, query: str) -> list[SearchResult]:
        return [SearchResult(title="T", url="http://x", snippet="S")]


class FakePapers:
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        return []

    async def fetch(self, paper_id: str) -> PaperResult:
        return PaperResult(paper_id=paper_id, title="T", abstract="A", authors=[], year=2020)


def test_fake_search_satisfies_web_search_port():
    assert isinstance(FakeSearch(), WebSearchPort)


def test_fake_papers_satisfies_paper_search_port():
    assert isinstance(FakePapers(), PaperSearchPort)
