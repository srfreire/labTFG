"""Fixtures and gating for real-LLM tests.

These tests hit the actual Anthropic API (or an OpenRouter-hosted Anthropic-compatible
endpoint via ANTHROPIC_BASE_URL) and cost real money. They're disabled by default
via the `real_llm` mark (see ../pyproject.toml `addopts`). Run them explicitly:

    cd tests && uv run pytest -m real_llm

Each test additionally skips if ANTHROPIC_API_KEY is missing.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from anthropic import AsyncAnthropic


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Auto-mark every test in this directory with `real_llm`."""
    here = os.path.dirname(__file__)
    for item in items:
        if str(item.fspath).startswith(here):
            item.add_marker(pytest.mark.real_llm)


def _skip_if_no_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — real-LLM tests skipped")


@pytest.fixture(scope="session")
def real_anthropic_client() -> AsyncAnthropic:
    """An AsyncAnthropic client wired to the real (or OpenRouter-proxied) API."""
    _skip_if_no_api_key()
    # Anthropic SDK reads ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL from env.
    return AsyncAnthropic()


@pytest_asyncio.fixture
async def real_embedding_service():
    """Yield a real EmbeddingService when both required keys are set, else skip."""
    voyage = os.environ.get("VOYAGE_API_KEY")
    ze = os.environ.get("ZEROENTROPY_API_KEY")
    if not voyage or not ze:
        pytest.skip("VOYAGE_API_KEY / ZEROENTROPY_API_KEY not set")
    from shared.embedding import EmbeddingService

    return EmbeddingService(voyage, ze)
