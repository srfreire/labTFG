from __future__ import annotations

import asyncio
from functools import partial
from urllib.request import urlopen, Request
from urllib.parse import quote
import json

from decisionlab.domain.models import PaperResult

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
        return [self._to_paper(p) for p in data.get("data", []) if p.get("title")]

    def _sync_fetch(self, paper_id: str) -> PaperResult:
        url = f"{_BASE_URL}/paper/{quote(paper_id)}?fields={_FIELDS}"
        data = self._get_json(url)
        return self._to_paper(data)

    def _get_json(self, url: str) -> dict:
        req = Request(url, headers={"User-Agent": "decisionlab/0.1"})
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _to_paper(self, raw: dict) -> PaperResult:
        return PaperResult(
            paper_id=raw.get("paperId", ""),
            title=raw.get("title", ""),
            abstract=raw.get("abstract", "") or "",
            authors=[a.get("name", "") for a in raw.get("authors", [])],
            year=raw.get("year", 0) or 0,
        )
