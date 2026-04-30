"""WebSocket-based feedback functions for each pipeline review stage.

Mirror of ``feedback.py`` but uses asyncio.Event + WS messages instead of
questionary prompts.  Every public function has the same return type as its
CLI counterpart, with an extra *emit* callback parameter.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

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

from decisionlab.parsing import (  # noqa: E402  — kept here next to its consumers
    filter_formulations_md,
    parse_formulation_headers,
)


def _discover_paradigm_slugs(reports_dir: Path) -> list[str]:
    deep_dir = reports_dir / "deep"
    if not deep_dir.is_dir():
        return []
    return sorted(p.stem for p in deep_dir.glob("*.md"))


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
        paradigms_data.append(
            {
                "slug": slug,
                "title": title,
                "summary": summary,
                "content": content,
            }
        )

    response = await wait_for_review(
        "review_research",
        emit,
        {
            "paradigms": paradigms_data,
        },
    )

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
    *,
    run_id: str = "",
) -> dict[str, list[int]]:
    """WebSocket review of formalization results.

    Returns ``{paradigm_slug: [1-based formulation numbers]}``.
    Also rewrites each paradigm's formulation file in S3.
    """
    import shared

    paradigms_data: list[dict] = []
    for slug in paradigm_slugs:
        s3_key = f"research/{run_id}/formulations/{slug}.md"
        try:
            text = await shared.storage.get_text(s3_key)
        except Exception:
            continue
        headers = parse_formulation_headers(text)
        formulations = [
            {"id": num, "name": name, "content": text[start:end]}
            for num, name, start, end in headers
        ]
        paradigms_data.append(
            {
                "slug": slug,
                "content": text,
                "formulations": formulations,
            }
        )

    response = await wait_for_review(
        "review_formalize",
        emit,
        {
            "paradigms": paradigms_data,
        },
    )

    # response shape: {"selected": {"slug": [1, 3], ...}}
    selections: dict[str, list[int]] = response.get("selected", {})

    # Rewrite formulation files in S3 to keep only selected formulations
    for slug, kept in selections.items():
        if kept:
            s3_key = f"research/{run_id}/formulations/{slug}.md"
            try:
                text = await shared.storage.get_text(s3_key)
                filtered = filter_formulations_md(text, kept)
                await shared.storage.put_text(s3_key, filtered)
            except Exception:
                pass

    return selections


# ---------------------------------------------------------------------------
# GET_ENV_SPEC
# ---------------------------------------------------------------------------


async def get_env_spec(
    emit: Callable[[dict], Awaitable[None]],
) -> Path:
    """WebSocket prompt for env_spec.json content.

    The frontend sends either a file path or the JSON content directly.
    Returns a Path to a validated JSON file (caller uploads to S3).
    """
    import tempfile

    response = await wait_for_review(
        "get_env_spec",
        emit,
        {
            "message": "Please provide the environment specification (env_spec.json).",
        },
    )

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
                specs_data.append(
                    {
                        "id": spec_id,
                        "spec_id": spec_id,
                        "paradigm": paradigm,
                        "name": spec_id,
                        "status": "invalid",
                        "problems": data.get("problems", []),
                        "full_spec": data,
                    }
                )
            else:
                specs_data.append(
                    {
                        "id": spec_id,
                        "spec_id": spec_id,
                        "paradigm": paradigm,
                        "name": data.get("name", spec_file.stem),
                        "description": data.get("description", ""),
                        "variables": data.get("variables", []),
                        "env_mapping": data.get("env_mapping", {}),
                        "full_spec": data,
                    }
                )

    response = await wait_for_review(
        "review_reason",
        emit,
        {
            "specs": specs_data,
        },
    )

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
    reports_dir: Path,
    build_results: dict[str, str],
    emit: Callable[[dict], Awaitable[None]],
) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """WebSocket review of builder results.

    Returns ``(approved_slugs, [(slug, paradigm, feedback)], reasoner_rerun_slugs)``.
    """
    models_data: list[dict] = []

    # Add invalid builds from validation reports
    builder_dir = reports_dir / "builder"
    if builder_dir.is_dir():
        for vfile in sorted(builder_dir.glob("*_validation.json")):
            try:
                data = json.loads(vfile.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("status") != "invalid":
                continue
            fid = data.get("formulation_id", vfile.stem)
            paradigm = data.get("paradigm", "unknown")
            models_data.append(
                {
                    "slug": fid,
                    "paradigm": paradigm,
                    "status": "invalid",
                    "problems": data.get("problems", []),
                    "code": "",
                    "test_results": "",
                    "passed": False,
                }
            )

    # Add valid builds
    for slug, content in build_results.items():
        lower = content.lower()
        has_issues = any(
            w in lower for w in ("error", "fail", "traceback", "exception")
        )
        models_data.append(
            {
                "slug": slug,
                "code": content,
                "test_results": content,
                "passed": not has_issues,
            }
        )

    response = await wait_for_review(
        "review_build",
        emit,
        {
            "models": models_data,
        },
    )

    # response shape: {"decisions": {"slug": {"approved": bool, "feedback": "...", "rerun_reasoner": bool}}}
    decisions = response.get("decisions", {})
    approved: list[str] = []
    rejections: list[tuple[str, str, str]] = []
    reasoner_reruns: list[str] = []

    for slug, decision in decisions.items():
        # Find paradigm for this slug from models_data
        paradigm = "unknown"
        for m in models_data:
            if m["slug"] == slug:
                paradigm = m.get("paradigm", "unknown")
                break
        if decision.get("rerun_reasoner", False):
            if paradigm not in reasoner_reruns:
                reasoner_reruns.append(paradigm)
        elif decision.get("approved", False):
            approved.append(slug)
        else:
            rejections.append((slug, paradigm, decision.get("feedback", "")))

    return approved, rejections, reasoner_reruns
