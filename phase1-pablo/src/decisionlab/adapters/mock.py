from __future__ import annotations

from decisionlab.domain.models import PaperResult, SearchResult


class MockWebSearch:
    def __init__(self, results: list[SearchResult] | None = None):
        self._results = results or [
            SearchResult(
                title="Homeostatic regulation of food intake",
                url="https://example.com/homeostatic",
                snippet="Homeostatic model based on hormonal signals (ghrelin, leptin).",
            ),
            SearchResult(
                title="Hedonic aspects of feeding",
                url="https://example.com/hedonic",
                snippet="Reward-based model using reinforcement learning.",
            ),
            SearchResult(
                title="Prospect theory and food choice",
                url="https://example.com/prospect",
                snippet="Decision-making under uncertainty applied to food.",
            ),
        ]

    async def search(self, query: str) -> list[SearchResult]:
        return self._results


class MockPaperSearch:
    def __init__(self, results: list[PaperResult] | None = None):
        self._results = results or [
            PaperResult(
                paper_id="jacquier2014",
                title="A predictive model of body weight dynamics",
                abstract="We present a model of food intake regulation...",
                authors=("Jacquier", "Alvarez"),
                year=2014,
            ),
        ]

    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        return self._results[:limit]

    async def fetch(self, paper_id: str) -> PaperResult:
        for p in self._results:
            if p.paper_id == paper_id:
                return p
        raise KeyError(f"Paper '{paper_id}' not found in mock data")
