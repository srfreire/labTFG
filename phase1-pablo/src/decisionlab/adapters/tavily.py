"""Tavily Search adapter — secondary failover when Brave returns nothing.

Tavily indexes academic content well, so it's the right fallback for the
Researcher's deep-citation queries that Brave occasionally misses. Empty
on missing key or transient failure (the chain advances to DuckDuckGo).
"""

from __future__ import annotations

import logging
import os

import httpx

from decisionlab.domain.models import SearchResult

logger = logging.getLogger(__name__)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_DEFAULT_TIMEOUT = 20.0


class TavilyAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_results: int = 10,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._max_results = max_results
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[SearchResult]:
        if not self._api_key:
            logger.debug("TavilyAdapter: TAVILY_API_KEY missing — returning [] ")
            return []

        body = {
            "api_key": self._api_key,
            "query": query,
            "max_results": self._max_results,
            "search_depth": "basic",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(_TAVILY_ENDPOINT, json=body)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("TavilyAdapter: search failed for %r: %s", query, exc)
            return []

        results = payload.get("results", []) if isinstance(payload, dict) else []
        out: list[SearchResult] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            out.append(
                SearchResult(
                    title=str(r.get("title", "")),
                    url=str(r.get("url", "")),
                    snippet=str(r.get("content", "")),
                )
            )
        return out
