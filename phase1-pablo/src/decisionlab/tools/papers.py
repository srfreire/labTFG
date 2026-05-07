"""OpenAlex API tool for searching academic papers.

Replaces the previous Semantic Scholar adapter — same tool name
(``search_papers``) and same schema, so the Researcher / DeepResearcher
prompts don't change. OpenAlex's public API is more reliable under load
than Semantic Scholar's best-effort unkeyed tier, has no rate-limit
ceiling for normal usage, and exposes the same fields the KG cares
about (DOI, authors, year, citation count, abstract).

Caveat: OpenAlex stopped serving plain-text abstracts in 2023 because
of copyright. Each work carries an ``abstract_inverted_index`` —
``{token: [positions, ...]}`` — and we reconstruct the abstract from
those positions before handing it to the agent.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.openalex.org/works"
_SELECT_FIELDS = (
    "id,title,authorships,publication_year,doi,cited_by_count,abstract_inverted_index"
)
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 25
_TIMEOUT = 30.0
# OpenAlex requests a contact email for the "polite pool" (faster
# response, lower throttling risk). Bare-string is fine; if the deployer
# wants to override they can set OPENALEX_MAILTO env var.
_DEFAULT_MAILTO = "decisionlab@usc.es"

SEARCH_PAPERS_SCHEMA: dict[str, Any] = {
    "name": "search_papers",
    "description": (
        "Search OpenAlex for academic papers. "
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
                "description": (
                    f"Max number of results (default {_DEFAULT_LIMIT}, max {_MAX_LIMIT})"
                ),
            },
        },
        "required": ["query"],
    },
}


def _reconstruct_abstract(inverted: dict | None) -> str:
    """Rebuild plain-text abstract from OpenAlex's inverted index.

    The index maps each token to its positions in the original abstract.
    Walk all (position, token) pairs in order; join with spaces. Cleans
    up trivially missing pieces by leaving gaps as single spaces.
    """
    if not isinstance(inverted, dict) or not inverted:
        return "No abstract available."
    positions: list[tuple[int, str]] = []
    for token, idxs in inverted.items():
        if not isinstance(idxs, list):
            continue
        for idx in idxs:
            if isinstance(idx, int):
                positions.append((idx, str(token)))
    if not positions:
        return "No abstract available."
    positions.sort(key=lambda p: p[0])
    return " ".join(token for _, token in positions)


def _doi_str(raw: str | None) -> str:
    """Strip OpenAlex's ``https://doi.org/`` URL prefix to bare DOI."""
    if not raw:
        return "N/A"
    if raw.startswith("https://doi.org/"):
        return raw[len("https://doi.org/") :]
    return raw


def create_search_papers() -> Callable[[dict], Awaitable[str]]:
    async def search_papers(params: dict) -> str:
        if "query" not in params:
            raise ValueError("search_papers requires 'query' parameter")

        query = params["query"]
        limit = min(int(params.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)

        request_params = {
            "search": query,
            "per-page": str(limit),
            "select": _SELECT_FIELDS,
            "mailto": _DEFAULT_MAILTO,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_API_BASE, params=request_params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("OpenAlex API error: %s", exc)
            return (
                f"Error querying OpenAlex (HTTP {exc.response.status_code}). "
                "Try a different query."
            )
        except httpx.HTTPError as exc:
            logger.warning("OpenAlex request failed: %s", exc)
            return f"Error connecting to OpenAlex: {exc}"

        try:
            data = resp.json()
        except ValueError:
            logger.warning("OpenAlex returned non-JSON response")
            return "Error: OpenAlex returned an unreadable response. Try again later."

        works = data.get("results", []) if isinstance(data, dict) else []
        if not works:
            return f"No papers found for query: {query}"

        lines: list[str] = []
        for w in works:
            if not isinstance(w, dict):
                continue
            title = w.get("title") or "Untitled"
            year = w.get("publication_year") or "N/A"
            doi = _doi_str(w.get("doi"))
            citations = w.get("cited_by_count", "N/A")
            authors = ", ".join(
                (a.get("author") or {}).get("display_name", "?")
                for a in (w.get("authorships") or [])
                if isinstance(a, dict)
            )
            abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
            lines.append(
                f"**{title}**\n"
                f"  Authors: {authors}\n"
                f"  Year: {year}\n"
                f"  DOI: {doi}\n"
                f"  Citations: {citations}\n"
                f"  Abstract: {abstract}"
            )
        return "\n\n".join(lines)

    return search_papers
