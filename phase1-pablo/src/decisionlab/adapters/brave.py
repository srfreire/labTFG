"""Brave Search adapter — primary web-search provider for the Researcher.

Brave leads agent-search benchmarks (14.89 score / 669 ms in Firecrawl's
2026 review) and we already keep ``BRAVE_API_KEY`` in ``.env``. Returns an
empty list rather than raising on transient HTTP failures so the chained
adapter (``adapters/__init__.py``) can fall back to Tavily / DuckDuckGo
without aborting the run.
"""

from __future__ import annotations

import logging
import os

import httpx

from decisionlab.domain.models import SearchResult

logger = logging.getLogger(__name__)

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_DEFAULT_TIMEOUT = 15.0


class BraveAdapter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_results: int = 10,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self._max_results = max_results
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> list[SearchResult]:
        if not self._api_key:
            logger.debug("BraveAdapter: BRAVE_API_KEY missing — returning [] ")
            return []

        params = {"q": query, "count": str(self._max_results)}
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    _BRAVE_ENDPOINT, params=params, headers=headers
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("BraveAdapter: search failed for %r: %s", query, exc)
            return []

        web = payload.get("web") if isinstance(payload, dict) else None
        results = web.get("results", []) if isinstance(web, dict) else []
        out: list[SearchResult] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            out.append(
                SearchResult(
                    title=str(r.get("title", "")),
                    url=str(r.get("url", "")),
                    snippet=str(r.get("description", "")),
                )
            )
        return out
