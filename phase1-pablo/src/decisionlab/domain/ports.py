from __future__ import annotations

from typing import Protocol, runtime_checkable

from decisionlab.domain.models import SearchResult


@runtime_checkable
class WebSearchPort(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...
