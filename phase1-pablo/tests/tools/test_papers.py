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


def _openalex_work(
    *,
    title: str,
    authors: list[str],
    year: int,
    doi: str,
    citations: int,
    abstract: str,
) -> dict:
    """Build a single OpenAlex work payload — including the inverted abstract index."""
    abstract_index: dict[str, list[int]] = {}
    for i, token in enumerate(abstract.split()):
        abstract_index.setdefault(token, []).append(i)
    return {
        "id": "https://openalex.org/W123",
        "title": title,
        "authorships": [{"author": {"display_name": a}} for a in authors],
        "publication_year": year,
        "doi": f"https://doi.org/{doi}" if doi else None,
        "cited_by_count": citations,
        "abstract_inverted_index": abstract_index,
    }


@pytest.mark.asyncio
async def test_successful_search():
    payload = {
        "results": [
            _openalex_work(
                title="Prospect Theory",
                authors=["Kahneman", "Tversky"],
                year=1979,
                doi="10.2307/1914185",
                citations=50000,
                abstract="An analysis of decision under risk.",
            )
        ]
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
    assert "10.2307/1914185" in result  # OpenAlex URL prefix stripped
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
    payload = {"meta": {"count": 0}, "results": []}

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
    """Default limit=5 is forwarded as OpenAlex's per-page parameter."""
    payload = {"meta": {"count": 0}, "results": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        await fn({"query": "test"})

    sent_params = mock_client.get.call_args.kwargs["params"]
    assert sent_params["per-page"] == "5"


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
async def test_inverted_abstract_is_reconstructed():
    """OpenAlex's inverted abstract index is reassembled into prose."""
    payload = {
        "results": [
            _openalex_work(
                title="Reconstruction Test",
                authors=["A. Author"],
                year=2024,
                doi="10.0/test",
                citations=1,
                abstract="Hello world this is a test abstract",
            )
        ]
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("decisionlab.tools.papers.httpx.AsyncClient", return_value=mock_client):
        fn = create_search_papers()
        result = await fn({"query": "test"})

    assert "Hello world this is a test abstract" in result


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
