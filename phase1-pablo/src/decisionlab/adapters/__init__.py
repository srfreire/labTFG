"""Web-search adapter package — exposes the chained provider used in production.

The default ``SearchProviderChain`` walks ``Tavily → DuckDuckGo`` and returns
the first non-empty result list. Each provider has a 3-attempt cap before
failover (within a single ``search`` call) so a transient HTTP blip on
Tavily doesn't fall straight through to DuckDuckGo. The chain only returns
``[]`` when every provider returned ``[]``.

Why Tavily over Google-via-Serper or Brave: Tavily is purpose-built for
LLM agents and returns extracted prose snippets that the Researcher and
DeepResearcher prompts can cite directly. The deep-citation backbone is
Semantic Scholar (in ``tools/papers.py``), not the web search itself.
"""

from __future__ import annotations

import asyncio
import logging

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.adapters.tavily import TavilyAdapter
from decisionlab.domain.models import SearchResult
from decisionlab.domain.ports import WebSearchPort

logger = logging.getLogger(__name__)

_RETRY_CAP = 3


class SearchProviderChain:
    """``WebSearchPort`` that walks an ordered list of providers until one
    returns at least one result. Each provider is retried up to
    ``_RETRY_CAP`` times before failing over to the next.

    Adapters in this codebase return ``[]`` rather than raising on transient
    failures, so retries are useful only when an adapter raises (e.g. the
    DuckDuckGo provider raising ``RuntimeError`` on ``ddgs`` rate-limit) —
    other adapters fall through after the first attempt.
    """

    def __init__(self, providers: list[WebSearchPort]) -> None:
        if not providers:
            raise ValueError("SearchProviderChain: at least one provider required")
        self._providers = providers

    async def search(self, query: str) -> list[SearchResult]:
        for provider in self._providers:
            name = type(provider).__name__
            for attempt in range(1, _RETRY_CAP + 1):
                try:
                    results = await provider.search(query)
                except Exception as exc:
                    logger.warning(
                        "SearchProviderChain[%s] attempt %d/%d raised: %s",
                        name,
                        attempt,
                        _RETRY_CAP,
                        exc,
                    )
                    if attempt == _RETRY_CAP:
                        break
                    await asyncio.sleep(0.3 * attempt)
                    continue
                if results:
                    if name != type(self._providers[0]).__name__ or attempt > 1:
                        logger.info(
                            "SearchProviderChain: %s returned %d result(s) on attempt %d",
                            name,
                            len(results),
                            attempt,
                        )
                    return results
                # Empty list — no point retrying the same provider; advance.
                break
        logger.warning(
            "SearchProviderChain: every provider returned empty for %r", query
        )
        return []


def default_search_chain(*, max_results: int = 10) -> SearchProviderChain:
    """Construct the production chain: Tavily → DuckDuckGo.

    Tavily is the primary; without ``TAVILY_API_KEY`` it returns ``[]``
    immediately and the chain falls through to DuckDuckGo (keyless,
    last-resort fallback).
    """
    return SearchProviderChain(
        [
            TavilyAdapter(max_results=max_results),
            DuckDuckGoAdapter(max_results=max_results),
        ]
    )
