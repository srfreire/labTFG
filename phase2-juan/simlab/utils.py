"""
Shared utilities for extracting and cleaning LLM outputs.

LLMs often return JSON wrapped in markdown fences or with extra text.
These helpers extract the actual content reliably.
"""

from __future__ import annotations

import re
from typing import Any


def strip_markdown_fences(text: str) -> str:
    """Extract JSON from LLM output, handling markdown fences and surrounding text.

    Tries in order:
      1. Extract content from ```json ... ``` fences
      2. Find the first raw JSON object ({...}) or array ([...])
      3. Return the text as-is if nothing matches
    """
    stripped = text.strip()

    # 1. Try to extract fenced block
    match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Try to find raw JSON object or array
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = stripped.find(open_char)
        end = stripped.rfind(close_char)
        if start != -1 and end > start:
            return stripped[start : end + 1]

    # 3. Nothing found — return as-is
    return stripped


def get_q_values(state: dict) -> dict | None:
    """Extract Q-values from a model state dict, trying common key names."""
    for key in ("q_values", "Q", "q_table"):
        val = state.get(key)
        if isinstance(val, dict):
            return val
    return None


def group_by_agent(events: list) -> dict[str, list]:
    """Group events by agent_id into a dict."""
    by_agent: dict[str, list] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)
    return by_agent


def extract_text(response: Any) -> str:
    """Extract the text content from a Claude API response.

    Finds the first text block, strips markdown fences, and returns clean content.
    Raises RuntimeError if the response contains no text.
    """
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text or not text.strip():
        raise RuntimeError(
            f"LLM produced no text output (stop_reason={response.stop_reason})"
        )
    return strip_markdown_fences(text)
