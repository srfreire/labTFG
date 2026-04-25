"""Corrective RAG evaluator with web search fallback.

Classifies reranked results as CORRECT/AMBIGUOUS/INCORRECT via Haiku,
then routes to pass-through, supplemented, or web-fallback action.
"""

from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic

from decisionlab.config import SETTINGS
from decisionlab.domain.models import SearchResult
from decisionlab.domain.ports import WebSearchPort
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.runtime.usage import record as record_usage
from shared.embedding import EmbeddingService

logger = logging.getLogger(__name__)

_FAST_MODEL = SETTINGS.knowledge_fast_model
_MAX_TOKENS = 1024

_EVAL_SYSTEM_PROMPT = """\
You are a relevance evaluator for a scientific knowledge retrieval system.

Given a query, a task context (what the downstream agent needs), and a list of \
retrieved passages, classify each passage as:
- CORRECT: relevant and useful for the task
- AMBIGUOUS: partially relevant or uncertain
- INCORRECT: not useful, stale, or from wrong domain

Return ONLY a JSON object (no markdown, no explanation outside JSON):
{"evaluations": [{"index": <int>, "classification": "<CORRECT|AMBIGUOUS|INCORRECT>", "reasoning": "<brief>"}]}

Evaluate ALL passages. Index starts at 0.
"""


async def _classify_results(
    query: str,
    task_context: str,
    results: list[RetrievalResult],
    client: AsyncAnthropic,
) -> list[dict]:
    """Call Haiku to classify each result. Returns list of evaluation dicts.

    On failure, returns all-CORRECT evaluations (fail-open).
    """
    fallback = [
        {"index": i, "classification": "CORRECT", "reasoning": "Default (evaluation failed)"}
        for i in range(len(results))
    ]

    try:
        passages = "\n\n".join(
            f"[{i}] {r.text}" for i, r in enumerate(results)
        )
        user_msg = (
            f"Query: {query}\n"
            f"Task context: {task_context}\n\n"
            f"Passages:\n{passages}"
        )

        response = await client.messages.create(
            model=_FAST_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_EVAL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        record_usage(_FAST_MODEL, getattr(response, "usage", None))

        raw = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()

        # Strip markdown fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
        cleaned = fence_match.group(1).strip() if fence_match else raw

        data = json.loads(cleaned)
        evaluations = data.get("evaluations", [])

        # Validate structure and bounds
        valid = []
        for ev in evaluations:
            if (
                isinstance(ev, dict)
                and isinstance(ev.get("index"), int)
                and 0 <= ev["index"] < len(results)
                and "classification" in ev
                and ev["classification"] in ("CORRECT", "AMBIGUOUS", "INCORRECT")
            ):
                valid.append(ev)

        if not valid:
            logger.warning("CRAG: no valid evaluations parsed, falling back to all-CORRECT")
            return fallback

        # Fill missing indices with CORRECT
        evaluated_indices = {ev["index"] for ev in valid}
        for i in range(len(results)):
            if i not in evaluated_indices:
                valid.append({
                    "index": i,
                    "classification": "CORRECT",
                    "reasoning": "Not evaluated (missing from response)",
                })

        return valid

    except Exception as exc:
        logger.warning("CRAG evaluation failed, defaulting all to CORRECT: %s", exc)
        return fallback


async def web_fallback(
    query: str,
    search_adapter: WebSearchPort,
    embedding_service: EmbeddingService,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Fetch fresh results from web search and return as RetrievalResults."""
    raw_results: list[SearchResult] = await search_adapter.search(query)

    if not raw_results:
        return []

    texts = [f"{r.title}. {r.snippet}" for r in raw_results]

    ranked = await embedding_service.rerank(query=query, documents=texts, top_k=top_k)

    return [
        RetrievalResult(
            text=texts[r.index],
            score=r.score,
            source="web",
            metadata={
                "url": raw_results[r.index].url,
                "title": raw_results[r.index].title,
            },
        )
        for r in ranked
        if r.index < len(raw_results)
    ]


async def evaluate_results(
    query: str,
    task_context: str,
    results: list[RetrievalResult],
    client: AsyncAnthropic,
    search_adapter: WebSearchPort | None = None,
    embedding_service: EmbeddingService | None = None,
) -> CRAGResult:
    """Run CRAG evaluation: classify results, route action, fallback if needed."""
    if not results:
        return CRAGResult(results=[], action="pass_through", evaluations=[], web_results_used=0)

    evaluations = await _classify_results(query, task_context, results, client)

    # Count classifications
    by_class: dict[str, list[int]] = {"CORRECT": [], "AMBIGUOUS": [], "INCORRECT": []}
    for ev in evaluations:
        cls = ev["classification"]
        if cls in by_class:
            by_class[cls].append(ev["index"])

    n_correct = len(by_class["CORRECT"])
    n_ambiguous = len(by_class["AMBIGUOUS"])
    n_incorrect = len(by_class["INCORRECT"])

    # Action routing
    if n_ambiguous == 0 and n_incorrect == 0:
        # All CORRECT → pass through
        return CRAGResult(
            results=results,
            action="pass_through",
            evaluations=evaluations,
            web_results_used=0,
        )

    if n_correct == 0 and n_ambiguous == 0:
        # All INCORRECT → full web fallback
        if search_adapter and embedding_service:
            web_results = await web_fallback(query, search_adapter, embedding_service)
            return CRAGResult(
                results=web_results,
                action="web_fallback",
                evaluations=evaluations,
                web_results_used=len(web_results),
            )
        return CRAGResult(
            results=[],
            action="web_fallback",
            evaluations=evaluations,
            web_results_used=0,
        )

    if n_ambiguous == 0 and n_correct > 0:
        # CORRECT + INCORRECT, no AMBIGUOUS → keep CORRECT only
        correct_results = [r for i, r in enumerate(results) if i in set(by_class["CORRECT"])]
        return CRAGResult(
            results=correct_results,
            action="pass_through",
            evaluations=evaluations,
            web_results_used=0,
        )

    # Has AMBIGUOUS → supplement with web
    kept_indices = set(by_class["CORRECT"] + by_class["AMBIGUOUS"])
    kept_results = [r for i, r in enumerate(results) if i in kept_indices]

    if search_adapter and embedding_service:
        web_results = await web_fallback(query, search_adapter, embedding_service)

        # Merge stored + web, rerank the combined set
        combined = kept_results + web_results
        combined_texts = [r.text for r in combined]

        reranked = await embedding_service.rerank(
            query=query,
            documents=combined_texts,
            top_k=len(combined),
        )

        final = [
            RetrievalResult(
                text=combined[r.index].text,
                score=r.score,
                source=combined[r.index].source,
                metadata=dict(combined[r.index].metadata),
            )
            for r in reranked
            if r.index < len(combined)
        ]

        return CRAGResult(
            results=final,
            action="supplemented",
            evaluations=evaluations,
            web_results_used=len(web_results),
        )

    # No search adapter — return kept results only
    return CRAGResult(
        results=kept_results,
        action="supplemented",
        evaluations=evaluations,
        web_results_used=0,
    )
