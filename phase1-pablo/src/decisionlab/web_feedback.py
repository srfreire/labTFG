"""WebSocket-based feedback functions for each pipeline review stage.

Mirror of ``feedback.py`` but uses asyncio.Event + WS messages instead of
questionary prompts.  Every public function has the same return type as its
CLI counterpart, with an extra *emit* callback parameter.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

# ---------------------------------------------------------------------------
# Module-level coordination between WS handler and review coroutines
# ---------------------------------------------------------------------------

_review_events: dict[str, asyncio.Event] = {}
_review_responses: dict[str, Any] = {}


def handle_review_response(stage: str, data: Any) -> None:
    """Called by ``server.py`` when a ``review_response`` message arrives."""
    _review_responses[stage] = data
    if stage in _review_events:
        _review_events[stage].set()


async def wait_for_review(
    stage: str,
    emit: Callable[[dict], Awaitable[None]],
    review_data: dict,
) -> Any:
    """Emit a ``review_request`` and block until the frontend responds."""
    event = asyncio.Event()
    _review_events[stage] = event

    await emit({"type": "review_request", "stage": stage, "data": review_data})
    await event.wait()

    response = _review_responses.pop(stage)
    del _review_events[stage]
    return response


# ---------------------------------------------------------------------------
# Helpers (shared with feedback.py logic)
# ---------------------------------------------------------------------------

_FORMULATION_HEADER_RE = re.compile(
    r"^##\s+Formulation\s+(\d+)\s*:\s*(.+)$", re.MULTILINE
)


def _discover_paradigm_slugs(reports_dir: Path) -> list[str]:
    deep_dir = reports_dir / "deep"
    if not deep_dir.is_dir():
        return []
    return sorted(p.stem for p in deep_dir.glob("*.md"))


def _parse_formulation_headers(text: str) -> list[tuple[int, str, int, int]]:
    matches = list(_FORMULATION_HEADER_RE.finditer(text))
    results: list[tuple[int, str, int, int]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        results.append((int(m.group(1)), m.group(2).strip(), start, end))
    return results


def _filter_formulations_md(text: str, keep_numbers: list[int]) -> str:
    headers = _parse_formulation_headers(text)
    if not headers:
        return text
    preamble = text[: headers[0][2]]
    kept_sections = [
        text[start:end] for num, _, start, end in headers if num in keep_numbers
    ]
    return (preamble + "".join(kept_sections)).rstrip() + "\n"


# ---------------------------------------------------------------------------
# REVIEW_RESEARCH
# ---------------------------------------------------------------------------


async def review_research(
    reports_dir: Path,
    emit: Callable[[dict], Awaitable[None]],
) -> tuple[list[str], str | None]:
    """WebSocket review of research results.

    Returns ``(approved_paradigms, additional_paradigm_name_or_None)``.
    """
    slugs = _discover_paradigm_slugs(reports_dir)

    # Read each deep report so the frontend can display it
    paradigms_data: list[dict[str, str]] = []
    deep_dir = reports_dir / "deep"
    for slug in slugs:
        md_path = deep_dir / f"{slug}.md"
        content = md_path.read_text() if md_path.exists() else ""
        # Extract title from slug
        title = slug.replace("-", " ").title()
        # Extract summary (first ~200 chars of content, trimmed to sentence)
        summary = content[:200].rsplit(".", 1)[0] + "." if content else ""
        paradigms_data.append({
            "slug": slug,
            "title": title,
            "summary": summary,
            "content": content,
        })

    response = await wait_for_review("review_research", emit, {
        "paradigms": paradigms_data,
    })

    approved: list[str] = response.get("approved", [])
    additional: str | None = response.get("additional") or None
    return approved, additional


# ---------------------------------------------------------------------------
# REVIEW_FORMALIZE
# ---------------------------------------------------------------------------


async def review_formalize(
    reports_dir: Path,
    paradigm_slugs: list[str],
    emit: Callable[[dict], Awaitable[None]],
) -> dict[str, list[int]]:
    """WebSocket review of formalization results.

    Returns ``{paradigm_slug: [1-based formulation numbers]}``.
    Also rewrites each paradigm's ``formulations/{slug}.md``.
    """
    formulations_dir = reports_dir / "formulations"

    paradigms_data: list[dict] = []
    for slug in paradigm_slugs:
        md_path = formulations_dir / f"{slug}.md"
        if not md_path.exists():
            continue
        text = md_path.read_text()
        headers = _parse_formulation_headers(text)
        formulations = [
            {"id": num, "name": name, "content": text[start:end]}
            for num, name, start, end in headers
        ]
        paradigms_data.append({
            "slug": slug,
            "content": text,
            "formulations": formulations,
        })

    response = await wait_for_review("review_formalize", emit, {
        "paradigms": paradigms_data,
    })

    # response shape: {"selected": {"slug": [1, 3], ...}}
    selections: dict[str, list[int]] = response.get("selected", {})

    # Rewrite files to keep only selected formulations
    for slug, kept in selections.items():
        md_path = formulations_dir / f"{slug}.md"
        if kept and md_path.exists():
            text = md_path.read_text()
            filtered = _filter_formulations_md(text, kept)
            md_path.write_text(filtered)

    return selections


# ---------------------------------------------------------------------------
# GET_ENV_SPEC
# ---------------------------------------------------------------------------


async def get_env_spec(
    emit: Callable[[dict], Awaitable[None]],
) -> Path:
    """WebSocket prompt for env_spec.json content.

    The frontend sends either a file path or the JSON content directly.
    Returns a Path to a validated JSON file.
    """
    import tempfile

    response = await wait_for_review("get_env_spec", emit, {
        "message": "Please provide the environment specification (env_spec.json).",
    })

    if "path" in response:
        path = Path(response["path"]).expanduser().resolve()
        # Validate
        json.loads(path.read_text())
        return path

    # env_spec key (from frontend — parsed JSON object)
    if "env_spec" in response:
        parsed = response["env_spec"]
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="env_spec_")
        with open(fd, "w") as fh:
            json.dump(parsed, fh, indent=2)
        return Path(tmp_path)

    # content key (JSON string)
    content = response.get("content", "{}")
    parsed = json.loads(content)  # validate
    fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="env_spec_")
    with open(fd, "w") as fh:
        json.dump(parsed, fh, indent=2)
    return Path(tmp_path)


# ---------------------------------------------------------------------------
# REVIEW_REASON
# ---------------------------------------------------------------------------


async def review_reason(
    reports_dir: Path,
    emit: Callable[[dict], Awaitable[None]],
) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """WebSocket review of reasoner JSON specs.

    Returns ``(approved_spec_ids, [(spec_id, paradigm_slug, feedback)], formalizer_rerun_slugs)``.
    """
    reasoner_dir = reports_dir / "reasoner"
    specs_data: list[dict] = []

    if reasoner_dir.is_dir():
        for spec_file in sorted(reasoner_dir.glob("*.json")):
            try:
                data = json.loads(spec_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            spec_id = data.get("formulation_id", spec_file.stem)
            paradigm = data.get("paradigm", "unknown")

            if data.get("status") == "invalid":
                specs_data.append({
                    "id": spec_id,
                    "spec_id": spec_id,
                    "paradigm": paradigm,
                    "name": spec_id,
                    "status": "invalid",
                    "problems": data.get("problems", []),
                    "full_spec": data,
                })
            else:
                specs_data.append({
                    "id": spec_id,
                    "spec_id": spec_id,
                    "paradigm": paradigm,
                    "name": data.get("name", spec_file.stem),
                    "description": data.get("description", ""),
                    "variables": data.get("variables", []),
                    "env_mapping": data.get("env_mapping", {}),
                    "full_spec": data,
                })

    response = await wait_for_review("review_reason", emit, {
        "specs": specs_data,
    })

    # response shape: {"decisions": {"spec_id": {"approved": bool, "feedback": "...", "rerun_formalizer": bool}}}
    decisions = response.get("decisions", {})
    approved: list[str] = []
    rejections: list[tuple[str, str, str]] = []
    formalizer_reruns: list[str] = []
    for spec_id, decision in decisions.items():
        # Find paradigm slug for this spec_id from specs_data
        paradigm = "unknown"
        for s in specs_data:
            if s["spec_id"] == spec_id:
                paradigm = s["paradigm"]
                break
        if decision.get("rerun_formalizer", False):
            if paradigm not in formalizer_reruns:
                formalizer_reruns.append(paradigm)
        elif decision.get("approved", False):
            approved.append(spec_id)
        else:
            rejections.append((spec_id, paradigm, decision.get("feedback", "")))
    return approved, rejections, formalizer_reruns


# ---------------------------------------------------------------------------
# REVIEW_BUILD
# ---------------------------------------------------------------------------


async def review_build(
    build_results: dict[str, str],
    emit: Callable[[dict], Awaitable[None]],
) -> str | None:
    """WebSocket review of builder results.

    Returns ``None`` if approved, or a feedback string for re-routing.
    """
    models_data = []
    for slug, content in build_results.items():
        lower = content.lower()
        has_issues = any(w in lower for w in ("error", "fail", "traceback", "exception"))
        models_data.append({
            "slug": slug,
            "code": content,
            "test_results": content,
            "passed": not has_issues,
        })

    response = await wait_for_review("review_build", emit, {
        "models": models_data,
    })

    # response shape: {"decisions": {"slug": {"approved": bool, "feedback": "..."}}}
    decisions = response.get("decisions", {})
    all_approved = all(d.get("approved", False) for d in decisions.values())
    if all_approved:
        return None
    feedbacks = [
        d.get("feedback", "")
        for d in decisions.values()
        if not d.get("approved", False) and d.get("feedback")
    ]
    return "; ".join(feedbacks) if feedbacks else None
