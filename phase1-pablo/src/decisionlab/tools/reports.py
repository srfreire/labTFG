"""Tools for persisting and reading research reports."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

READ_REPORT_SCHEMA: dict[str, Any] = {
    "name": "read_report",
    "description": "Read a previously saved deep research report by paradigm name. Use only if you need more detail than the summary returned by launch_deep_research.",
    "input_schema": {
        "type": "object",
        "properties": {
            "paradigm": {"type": "string", "description": "Paradigm name (as used in launch_deep_research)"},
        },
        "required": ["paradigm"],
    },
}


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-").replace("/", "-").replace(":", "")


def create_read_report(reports_dir: Path) -> Callable[[dict], Awaitable[str]]:
    async def read_report(params: dict) -> str:
        if "paradigm" not in params:
            raise ValueError("read_report requires 'paradigm' parameter")
        slug = _slugify(params["paradigm"])
        path = reports_dir / "deep" / f"{slug}.md"
        if not path.exists():
            return f"No report found for '{params['paradigm']}' at {path}"
        return path.read_text()
    return read_report


def save_deep_report(reports_dir: Path, paradigm: str, content: str) -> Path:
    """Save a deep research report to disk. Returns the file path."""
    deep_dir = reports_dir / "deep"
    deep_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(paradigm)
    path = deep_dir / f"{slug}.md"
    path.write_text(content)
    logger.info("Saved deep report: %s", path)
    return path


def save_summary_report(reports_dir: Path, summary: str) -> Path:
    """Save the final research summary to disk. Returns the file path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "report.md"
    path.write_text(summary)
    logger.info("Saved summary report: %s", path)
    return path
