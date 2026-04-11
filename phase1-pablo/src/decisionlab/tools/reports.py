"""Tools for persisting and reading research reports."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from decisionlab.router import PipelineState

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


def slugify(name: str) -> str:
    """Turn a paradigm name into a filesystem-safe slug."""
    slug = name.lower().replace(" ", "-").replace("/", "-").replace(":", "")
    return re.sub(r"-{2,}", "-", slug).strip("-")


def create_read_report(reports_dir: Path) -> Callable[[dict], Awaitable[str]]:
    async def read_report(params: dict) -> str:
        if "paradigm" not in params:
            raise ValueError("read_report requires 'paradigm' parameter")
        slug = slugify(params["paradigm"])
        path = reports_dir / "deep" / f"{slug}.md"
        if not path.exists():
            return f"No report found for paradigm '{params['paradigm']}'. It may not have been researched yet."
        return path.read_text()
    return read_report


def save_deep_report(reports_dir: Path, paradigm: str, content: str) -> Path:
    """Save a deep research report to disk. Returns the file path."""
    deep_dir = reports_dir / "deep"
    deep_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(paradigm)
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


# ---------------------------------------------------------------------------
# Tree map
# ---------------------------------------------------------------------------

_DEEP_TITLE_RE = re.compile(r"^#\s+(.+?)(?:\s+—\s+Deep Research)?\s*$", re.MULTILINE)
_TREE_MAP_SECTION_RE = re.compile(
    r"\n## Research Tree Map\n.*?(?=\n##|\Z)", re.DOTALL,
)


def _paradigm_name_from_deep_report(reports_dir: Path, slug: str) -> str:
    """Extract the paradigm title from ``deep/{slug}.md``, falling back to slug."""
    path = reports_dir / "deep" / f"{slug}.md"
    if not path.exists():
        return slug
    m = _DEEP_TITLE_RE.search(path.read_text())
    return m.group(1) if m else slug


def generate_tree_map(state: PipelineState) -> str:
    """Build a Markdown tree map from ``state.id_registry`` and insert it into report.md."""
    reports_dir = state.reports_dir
    report_path = reports_dir / "report.md"

    # Separate paradigms from formulations in the registry
    paradigms: dict[str, str] = {}
    formulations: dict[str, list[tuple[str, str]]] = {}

    for key, rid in state.id_registry.items():
        if "::" in key:
            slug, name = key.split("::", 1)
            formulations.setdefault(slug, []).append((rid, name))
        else:
            paradigms[key] = rid

    sorted_paradigms = sorted(paradigms.items(), key=lambda x: x[1])
    for slug in formulations:
        formulations[slug].sort(key=lambda x: x[0])

    # Read report.md once for both topic label extraction and later replacement
    existing_content = report_path.read_text() if report_path.exists() else None

    topic_label = state.topic_id
    if existing_content is not None:
        first_heading = re.search(r"^#\s+(.+)$", existing_content, re.MULTILINE)
        if first_heading:
            topic_label = f"{state.topic_id}: {first_heading.group(1).strip()}"

    # Build tree lines
    lines = [topic_label]
    for i, (slug, pid) in enumerate(sorted_paradigms):
        is_last_paradigm = i == len(sorted_paradigms) - 1
        p_prefix = "└──" if is_last_paradigm else "├──"
        p_name = _paradigm_name_from_deep_report(reports_dir, slug)
        lines.append(f"{p_prefix} {pid}: {p_name}")

        for j, (fid, fname) in enumerate(formulations.get(slug, [])):
            is_last_form = j == len(formulations[slug]) - 1
            f_connector = "    " if is_last_paradigm else "│   "
            f_prefix = "└──" if is_last_form else "├──"
            lines.append(f"{f_connector}{f_prefix} {fid}: {fname}")

    tree_text = "\n".join(lines)

    # Insert/replace in report.md
    section = f"\n## Research Tree Map\n\n```\n{tree_text}\n```\n"
    if existing_content is not None:
        if _TREE_MAP_SECTION_RE.search(existing_content):
            content = _TREE_MAP_SECTION_RE.sub(section, existing_content)
        else:
            content = existing_content.rstrip() + "\n" + section
        report_path.write_text(content)
    else:
        report_path.write_text(section)

    logger.info("Tree map generated in %s", report_path)
    return tree_text
