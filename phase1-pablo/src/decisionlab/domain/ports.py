from __future__ import annotations

from typing import Protocol, runtime_checkable

from decisionlab.domain.models import PaperResult, SearchResult


@runtime_checkable
class WebSearchPort(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...


@runtime_checkable
class PaperSearchPort(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[PaperResult]: ...
    async def fetch(self, paper_id: str) -> PaperResult: ...
