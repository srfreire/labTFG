"""Tools for persisting and reading research reports via StorageService."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import shared
from shared.artifacts import register_artifact as _register_artifact

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


def create_read_report(run_id: str) -> Callable[[dict], Awaitable[str]]:
    async def read_report(params: dict) -> str:
        if "paradigm" not in params:
            raise ValueError("read_report requires 'paradigm' parameter")
        slug = slugify(params["paradigm"])
        key = f"research/{run_id}/deep/{slug}.md"
        try:
            return await shared.storage.get_text(key)
        except Exception:
            return f"No report found for paradigm '{params['paradigm']}'. It may not have been researched yet."
    return read_report


async def save_deep_report(run_id: str, paradigm: str, content: str) -> str:
    """Save a deep research report to S3. Returns the S3 key."""
    slug = slugify(paradigm)
    key = f"research/{run_id}/deep/{slug}.md"
    await shared.storage.put_text(key, content)
    await _register_artifact(key, "deep_report", len(content.encode()), run_id=run_id)
    logger.info("Saved deep report: %s", key)
    return key


async def save_summary_report(run_id: str, summary: str) -> str:
    """Save the final research summary to S3. Returns the S3 key."""
    key = f"research/{run_id}/report.md"
    await shared.storage.put_text(key, summary)
    await _register_artifact(key, "report", len(summary.encode()), run_id=run_id)
    logger.info("Saved summary report: %s", key)
    return key


# ---------------------------------------------------------------------------
# Tree map
# ---------------------------------------------------------------------------

_DEEP_TITLE_RE = re.compile(r"^#\s+(.+?)(?:\s+—\s+Deep Research)?\s*$", re.MULTILINE)
_TREE_MAP_SECTION_RE = re.compile(
    r"\n## Research Tree Map\n.*?(?=\n##|\Z)", re.DOTALL,
)


async def _paradigm_name_from_deep_report(run_id: str, slug: str) -> str:
    """Extract the paradigm title from ``deep/{slug}.md``, falling back to slug."""
    key = f"research/{run_id}/deep/{slug}.md"
    try:
        text = await shared.storage.get_text(key)
    except Exception:
        return slug
    m = _DEEP_TITLE_RE.search(text)
    return m.group(1) if m else slug


async def generate_tree_map(state: PipelineState) -> str:
    """Build a Markdown tree map from ``state.ids`` and insert it into report.md."""
    run_id = state.run_id
    report_key = f"research/{run_id}/report.md"
    tree = state.ids.tree()
    sorted_slugs = list(tree.keys())

    # Read report.md once for both topic label extraction and later replacement
    existing_content = None
    if await shared.storage.exists(report_key):
        existing_content = await shared.storage.get_text(report_key)

    topic_label = state.topic_id
    if existing_content is not None:
        first_heading = re.search(r"^#\s+(.+)$", existing_content, re.MULTILINE)
        if first_heading:
            topic_label = f"{state.topic_id}: {first_heading.group(1).strip()}"

    # Build tree lines
    lines = [topic_label]
    for i, slug in enumerate(sorted_slugs):
        entry = tree[slug]
        pid = entry["id"]
        formulations = entry["formulations"]
        is_last_paradigm = i == len(sorted_slugs) - 1
        p_prefix = "└──" if is_last_paradigm else "├──"
        p_name = await _paradigm_name_from_deep_report(run_id, slug)
        lines.append(f"{p_prefix} {pid}: {p_name}")

        flist = list(formulations.items())
        for j, (fname, fid) in enumerate(flist):
            is_last_form = j == len(flist) - 1
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
        await shared.storage.put_text(report_key, content)
    else:
        await shared.storage.put_text(report_key, section)

    logger.info("Tree map generated in %s", report_key)
    return tree_text
