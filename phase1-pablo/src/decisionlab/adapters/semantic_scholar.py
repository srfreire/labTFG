from __future__ import annotations

import asyncio
import json
import logging
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from decisionlab.domain.models import PaperResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year"


class SemanticScholarAdapter:
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._sync_search, query, limit))

    async def fetch(self, paper_id: str) -> PaperResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._sync_fetch, paper_id))

    def _sync_search(self, query: str, limit: int) -> list[PaperResult]:
        url = f"{_BASE_URL}/paper/search?query={quote(query)}&limit={limit}&fields={_FIELDS}"
        data = self._get_json(url)
        if "error" in data or "message" in data:
            raise RuntimeError(f"Semantic Scholar API error: {data.get('error') or data.get('message')}")
        papers = data.get("data")
        if papers is None:
            raise RuntimeError(f"Unexpected API response: missing 'data' key. Keys: {list(data.keys())}")
        return [self._to_paper(p) for p in papers if p.get("title")]

    def _sync_fetch(self, paper_id: str) -> PaperResult:
        url = f"{_BASE_URL}/paper/{quote(paper_id)}?fields={_FIELDS}"
        data = self._get_json(url)
        paper = self._to_paper(data)
        if not paper.title:
            raise RuntimeError(f"Paper '{paper_id}' has no title — likely an error response")
        return paper

    def _get_json(self, url: str) -> dict:
        req = Request(url, headers={"User-Agent": "decisionlab/0.1"})
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            raise RuntimeError(f"Semantic Scholar HTTP {e.code} for {url}") from e
        except URLError as e:
            raise RuntimeError(f"Semantic Scholar connection error: {e.reason}") from e

    def _to_paper(self, raw: dict) -> PaperResult:
        return PaperResult(
            paper_id=raw.get("paperId", ""),
            title=raw.get("title", ""),
            abstract=raw.get("abstract", "") or "",
            authors=tuple(a.get("name", "") for a in raw.get("authors", [])),
            year=raw.get("year", 0) or 0,
        )
