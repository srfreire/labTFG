from __future__ import annotations

from decisionlab.domain.models import SearchResult


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
