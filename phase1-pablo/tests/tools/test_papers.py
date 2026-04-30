from unittest.mock import AsyncMock, patch

import httpx
import pytest

from decisionlab.tools.papers import (
    SEARCH_PAPERS_SCHEMA,
    create_search_papers,
)


def test_schema_has_required_fields():
    assert SEARCH_PAPERS_SCHEMA["name"] == "search_papers"
    props = SEARCH_PAPERS_SCHEMA["input_schema"]["properties"]
    assert "query" in props
    assert "limit" in props
    assert SEARCH_PAPERS_SCHEMA["input_schema"]["required"] == ["query"]


@pytest.mark.asyncio
async def test_missing_query_raises():
    fn = create_search_papers()
    with pytest.raises(ValueError, match="query"):
        await fn({})


def _mock_response(json_data, status_code=200):
    return httpx.Response(
        status_code, json=json_data, request=httpx.Request("GET", "https://example.com")
    )


@pytest.mark.asyncio
async def test_successful_search():
    payload = {
        "total": 1,
        "data": [
            {
                "paperId": "abc123",
                "title": "Prospect Theory",
                "authors": [{"name": "Kahneman"}, {"name": "Tversky"}],
                "year": 1979,
                "abstract": "An analysis of decision under risk.",
                "externalIds": {"DOI": "10.2307/1914185"},
                "citationCount": 50000,
            }
        ],
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "prospect theory", "limit": 5})

    assert "Prospect Theory" in result
    assert "Kahneman" in result
    assert "10.2307/1914185" in result
    assert "1979" in result


@pytest.mark.asyncio
async def test_api_error_returns_message():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=500))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "test"})

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_empty_results():
    payload = {"total": 0, "data": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "xyznonexistent"})

    assert "No papers found" in result


@pytest.mark.asyncio
async def test_default_limit_is_5():
    """Default limit=5 is used when not specified."""
    payload = {"total": 0, "data": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        await fn({"query": "test"})

    call_kwargs = mock_client.get.call_args
    assert (
        "limit=5" in str(call_kwargs)
        or call_kwargs[1].get("params", {}).get("limit") == 5
    )


@pytest.mark.asyncio
async def test_network_error_returns_message():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "test"})

    assert "error" in result.lower()


@pytest.mark.asyncio
async def test_429_retries_once():
    """On 429, waits and retries; second attempt succeeds."""
    rate_limit_resp = _mock_response({}, status_code=429)
    rate_limit_resp.headers["Retry-After"] = "0.1"

    success_payload = {
        "total": 1,
        "data": [
            {
                "paperId": "x",
                "title": "Retry Paper",
                "authors": [],
                "year": 2020,
                "abstract": "Retried.",
                "externalIds": {},
                "citationCount": 1,
            },
        ],
    }
    ok_resp = _mock_response(success_payload)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[rate_limit_resp, ok_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "retry test"})

    assert "Retry Paper" in result
    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_malformed_json_returns_error():
    """Non-JSON 200 response returns a readable error."""
    resp = httpx.Response(
        200,
        content=b"<html>Error</html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "https://example.com"),
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "test"})

    assert "unreadable" in result.lower()
