"""Query rewriter — turn raw multi-sentence queries into a focal noun
phrase and a small bag of keywords.

Feeds both vector retrieval (dense embedding uses the focal phrase only;
sparse BM25 uses the original query plus the keywords) and KG NER (which
gets the keywords as a hint).

In-process cache keyed by sha1(query[:512]) avoids re-rewriting on
duplicate queries inside a single eval run. The cache is process-local;
that is fine for eval suites that fit in one process.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic import BaseModel, Field

from decisionlab.structured import call_structured

logger = logging.getLogger(__name__)


class _QueryRewrite(BaseModel):
    focal_concept: str = Field(
        description="Short noun phrase capturing the topic. Used for dense embedding."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="3-7 lemmas relevant to the topic. Used for BM25 + KG NER hint.",
    )


_SYSTEM_PROMPT = """\
You are a query rewriter. Given a research question, produce:
- focal_concept: the single noun phrase that best names the topic
  (e.g. "drift-diffusion model", "reinforcement learning",
  "prospect theory")
- keywords: 3-7 lemmas useful for keyword search (e.g.
  ["evidence accumulation", "decision boundary", "reaction time"])

Be concise. Lowercase. No punctuation. Do not paraphrase the question;
extract.
"""

_MAX_TOKENS = 256
_MODEL = "claude-haiku-4-5-20251001"
_cache: dict[str, _QueryRewrite] = {}


def _cache_key(query: str) -> str:
    return hashlib.sha1(query[:512].encode("utf-8")).hexdigest()


async def rewrite(query: str, *, client) -> _QueryRewrite:
    """Rewrite *query* into focal_concept + keywords. Cached per process.

    On any rewrite failure (network, parse, etc.) returns a passthrough
    rewrite (focal=query, keywords=[]) so callers can always proceed.
    """
    key = _cache_key(query)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    try:
        result = await call_structured(
            client=client,
            messages=[{"role": "user", "content": query}],
            system=_SYSTEM_PROMPT,
            schema=_QueryRewrite,
            max_tokens=_MAX_TOKENS,
            model=_MODEL,
        )
    except Exception as exc:
        logger.warning("query_rewriter: rewrite failed; using passthrough: %s", exc)
        result = _QueryRewrite(focal_concept=query, keywords=[])
    _cache[key] = result
    return result
