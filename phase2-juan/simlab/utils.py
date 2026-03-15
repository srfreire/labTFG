"""Shared utilities for simlab agents."""
from __future__ import annotations

import re
from typing import Any


def strip_markdown_fences(text: str) -> str:
    """Extract JSON from LLM output, handling fences and surrounding text."""
    stripped = text.strip()

    # Try to extract fenced block (may have text before/after the fence)
    match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No fence — try to extract raw JSON object/array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = stripped.find(start_char)
        end = stripped.rfind(end_char)
        if start != -1 and end > start:
            return stripped[start : end + 1]

    return stripped


def extract_text(response: Any) -> str:
    """Extract and clean the text content from an LLM response."""
    text = next((b.text for b in response.content if b.type == "text"), "")
    return strip_markdown_fences(text)
