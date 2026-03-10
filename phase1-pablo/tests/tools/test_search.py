import pytest

from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.tools.search import (
    WEB_SEARCH_SCHEMA,
    SEARCH_PAPERS_SCHEMA,
    FETCH_PAPER_SCHEMA,
    create_web_search,
    create_search_papers,
    create_fetch_paper,
)


def test_web_search_schema_has_required_fields():
    assert WEB_SEARCH_SCHEMA["name"] == "web_search"
    assert "query" in WEB_SEARCH_SCHEMA["input_schema"]["properties"]


def test_search_papers_schema_has_required_fields():
    assert SEARCH_PAPERS_SCHEMA["name"] == "search_papers"
    assert "query" in SEARCH_PAPERS_SCHEMA["input_schema"]["properties"]
    assert "limit" in SEARCH_PAPERS_SCHEMA["input_schema"]["properties"]


def test_fetch_paper_schema_has_required_fields():
    assert FETCH_PAPER_SCHEMA["name"] == "fetch_paper"
    assert "paper_id" in FETCH_PAPER_SCHEMA["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_web_search_function_delegates_to_port():
    adapter = MockWebSearch()
    fn = create_web_search(adapter)
    result = await fn({"query": "homeostatic regulation"})
    assert "Homeostatic" in result


@pytest.mark.asyncio
async def test_search_papers_function_delegates_to_port():
    adapter = MockPaperSearch()
    fn = create_search_papers(adapter)
    result = await fn({"query": "food intake", "limit": 5})
    assert "predictive model" in result.lower()


@pytest.mark.asyncio
async def test_search_papers_uses_default_limit():
    adapter = MockPaperSearch()
    fn = create_search_papers(adapter)
    result = await fn({"query": "food intake"})
    assert "predictive model" in result.lower()


@pytest.mark.asyncio
async def test_fetch_paper_function_delegates_to_port():
    adapter = MockPaperSearch()
    fn = create_fetch_paper(adapter)
    result = await fn({"paper_id": "jacquier2014"})
    assert "jacquier2014" in result.lower() or "Jacquier" in result


@pytest.mark.asyncio
async def test_web_search_missing_query_raises():
    adapter = MockWebSearch()
    fn = create_web_search(adapter)
    with pytest.raises(ValueError, match="query"):
        await fn({})


@pytest.mark.asyncio
async def test_search_papers_missing_query_raises():
    adapter = MockPaperSearch()
    fn = create_search_papers(adapter)
    with pytest.raises(ValueError, match="query"):
        await fn({"limit": 5})


@pytest.mark.asyncio
async def test_fetch_paper_missing_paper_id_raises():
    adapter = MockPaperSearch()
    fn = create_fetch_paper(adapter)
    with pytest.raises(ValueError, match="paper_id"):
        await fn({})
