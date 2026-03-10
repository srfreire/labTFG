from __future__ import annotations

import asyncio
from functools import partial

from duckduckgo_search import DDGS

from decisionlab.domain.models import SearchResult


class DuckDuckGoAdapter:
    def __init__(self, max_results: int = 10):
        self._max_results = max_results

    async def search(self, query: str) -> list[SearchResult]:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, partial(self._sync_search, query))
        return results

    def _sync_search(self, query: str) -> list[SearchResult]:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=self._max_results))
        return [
            SearchResult(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", ""))
            for r in raw
        ]
