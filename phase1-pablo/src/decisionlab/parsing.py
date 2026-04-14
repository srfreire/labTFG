"""Shared parsing helpers for formulation markdown files."""

from __future__ import annotations

import re

FORMULATION_HEADER_RE = re.compile(
    r"^##\s+Formulation\s+(\d+)\s*:\s*(.+)$", re.MULTILINE,
)


def parse_formulation_headers(text: str) -> list[tuple[int, str, int, int]]:
    """Parse ``## Formulation N: name`` headers.

    Returns list of ``(number, name, start_pos, end_pos)`` tuples where
    *start_pos* is the index of the ``#`` and *end_pos* is the start of
    the next header (or EOF).
    """
    matches = list(FORMULATION_HEADER_RE.finditer(text))
    results: list[tuple[int, str, int, int]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        results.append((int(m.group(1)), m.group(2).strip(), start, end))
    return results


def filter_formulations_md(text: str, keep_numbers: list[int]) -> str:
    """Rewrite a formulations markdown keeping only selected formulations."""
    headers = parse_formulation_headers(text)
    if not headers:
        return text
    preamble = text[: headers[0][2]]
    kept_sections = [
        text[start:end] for num, _, start, end in headers if num in keep_numbers
    ]
    return (preamble + "".join(kept_sections)).rstrip() + "\n"
