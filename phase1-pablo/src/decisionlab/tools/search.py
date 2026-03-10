from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from decisionlab.domain.ports import PaperSearchPort, WebSearchPort

WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "web_search",
    "description": "Search the web for information about decision-making paradigms. Returns a list of results with title, URL, and snippet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
}

SEARCH_PAPERS_SCHEMA: dict[str, Any] = {
    "name": "search_papers",
    "description": "Search for academic papers on a topic. Returns papers with title, abstract, authors, and year.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for academic papers"},
            "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
        },
        "required": ["query"],
    },
}

FETCH_PAPER_SCHEMA: dict[str, Any] = {
    "name": "fetch_paper",
    "description": "Fetch full details of a specific paper by its ID. Returns title, abstract, authors, and year.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Paper ID from search_papers results"},
        },
        "required": ["paper_id"],
    },
}


def create_web_search(adapter: WebSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def web_search(input: dict) -> str:
        results = await adapter.search(input["query"])
        return json.dumps(
            [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
            indent=2,
        )
    return web_search


def create_search_papers(adapter: PaperSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def search_papers(input: dict) -> str:
        results = await adapter.search(input["query"], input.get("limit", 10))
        return json.dumps(
            [{"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract,
              "authors": p.authors, "year": p.year} for p in results],
            indent=2,
        )
    return search_papers


def create_fetch_paper(adapter: PaperSearchPort) -> Callable[[dict], Awaitable[str]]:
    async def fetch_paper(input: dict) -> str:
        paper = await adapter.fetch(input["paper_id"])
        return json.dumps(
            {"paper_id": paper.paper_id, "title": paper.title, "abstract": paper.abstract,
             "authors": paper.authors, "year": paper.year},
            indent=2,
        )
    return fetch_paper
