from __future__ import annotations

import asyncio
import logging
from functools import partial

from ddgs import DDGS

from decisionlab.domain.models import SearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoAdapter:
    def __init__(self, max_results: int = 10):
        self._max_results = max_results

    async def search(self, query: str) -> list[SearchResult]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._sync_search, query))

    def _sync_search(self, query: str) -> list[SearchResult]:
        try:
            raw = list(DDGS().text(query, max_results=self._max_results))
        except Exception as e:
            raise RuntimeError(f"DuckDuckGo search failed: {e}") from e
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
            )
            for r in raw
        ]
