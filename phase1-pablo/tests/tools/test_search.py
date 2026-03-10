import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.tools.search import (
    WEB_SEARCH_SCHEMA,
    create_web_search,
)


def test_web_search_schema_has_required_fields():
    assert WEB_SEARCH_SCHEMA["name"] == "web_search"
    assert "query" in WEB_SEARCH_SCHEMA["input_schema"]["properties"]


@pytest.mark.asyncio
async def test_web_search_function_delegates_to_port():
    adapter = MockWebSearch()
    fn = create_web_search(adapter)
    result = await fn({"query": "homeostatic regulation"})
    assert "Homeostatic" in result


@pytest.mark.asyncio
async def test_web_search_missing_query_raises():
    adapter = MockWebSearch()
    fn = create_web_search(adapter)
    with pytest.raises(ValueError, match="query"):
        await fn({})
