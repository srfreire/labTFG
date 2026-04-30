"""Semantic Scholar API tool for searching academic papers."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,authors,year,abstract,externalIds,citationCount"
_DEFAULT_LIMIT = 5
_RATE_LIMIT_INTERVAL = 1.0  # seconds between requests

SEARCH_PAPERS_SCHEMA: dict[str, Any] = {
    "name": "search_papers",
    "description": (
        "Search Semantic Scholar for academic papers. "
        "Returns titles, authors, year, DOI, abstract, and citation count. "
        "Use for finding verified academic references on decision-making paradigms."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for academic papers",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of results (default 5, max 100)",
            },
        },
        "required": ["query"],
    },
}


def create_search_papers() -> Callable[[dict], Awaitable[str]]:
    last_request_time: float = 0.0
    lock = asyncio.Lock()

    async def _rate_limited_wait() -> None:
        nonlocal last_request_time
        async with lock:
            now = time.monotonic()
            elapsed = now - last_request_time
            if elapsed < _RATE_LIMIT_INTERVAL:
                await asyncio.sleep(_RATE_LIMIT_INTERVAL - elapsed)
            last_request_time = time.monotonic()

    async def _do_request(
        client: httpx.AsyncClient, query: str, limit: int
    ) -> httpx.Response:
        await _rate_limited_wait()
        resp = await client.get(
            _API_BASE,
            params={"query": query, "limit": limit, "fields": _FIELDS},
        )
        resp.raise_for_status()
        return resp

    async def search_papers(params: dict) -> str:
        if "query" not in params:
            raise ValueError("search_papers requires 'query' parameter")

        query = params["query"]
        limit = min(params.get("limit", _DEFAULT_LIMIT), 100)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    resp = await _do_request(client, query, limit)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        retry_after = float(
                            exc.response.headers.get(
                                "Retry-After", _RATE_LIMIT_INTERVAL
                            )
                        )
                        logger.warning(
                            "Semantic Scholar rate-limited; retrying after %.1fs",
                            retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        resp = await _do_request(client, query, limit)
                    else:
                        logger.warning("Semantic Scholar API error: %s", exc)
                        return f"Error querying Semantic Scholar (HTTP {exc.response.status_code}). Try a different query."
        except httpx.HTTPStatusError as exc:
            logger.warning("Semantic Scholar API error after retry: %s", exc)
            return f"Error querying Semantic Scholar (HTTP {exc.response.status_code}). Try a different query."
        except httpx.HTTPError as exc:
            logger.warning("Semantic Scholar request failed: %s", exc)
            return f"Error connecting to Semantic Scholar: {exc}"

        try:
            data = resp.json()
        except ValueError:
            logger.warning("Semantic Scholar returned non-JSON response")
            return "Error: Semantic Scholar returned an unreadable response. Try again later."

        papers = data.get("data", [])

        if not papers:
            return f"No papers found for query: {query}"

        lines: list[str] = []
        for p in papers:
            authors = ", ".join(a.get("name", "?") for a in (p.get("authors") or []))
            doi = (p.get("externalIds") or {}).get("DOI", "N/A")
            abstract = p.get("abstract") or "No abstract available."
            lines.append(
                f"**{p.get('title', 'Untitled')}**\n"
                f"  Authors: {authors}\n"
                f"  Year: {p.get('year', 'N/A')}\n"
                f"  DOI: {doi}\n"
                f"  Citations: {p.get('citationCount', 'N/A')}\n"
                f"  Abstract: {abstract}"
            )

        return "\n\n".join(lines)

    return search_papers
