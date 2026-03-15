"""Shared utilities for simlab agents."""
from __future__ import annotations


def strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the LLM wraps the output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
