"""Mock pipeline server that replays sample data via WebSocket events.

Simulates the full pipeline using pre-recorded data from
``examples/sample-run/`` so the web UI can be tested without spending
API tokens.  Uses the same ``/ws`` protocol as ``server.py``.

Start with::

    cd phase1-pablo && uv run python -m decisionlab.mock_server
    # OR
    cd phase1-pablo && uv run uvicorn decisionlab.mock_server:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "sample-run"

app = FastAPI(title="DecisionLab Mock")

# ---------------------------------------------------------------------------
# Review coordination (same pattern as web_feedback.py)
# ---------------------------------------------------------------------------

_review_events: dict[str, asyncio.Event] = {}
_review_responses: dict[str, dict] = {}


def handle_review_response(stage: str, data: dict) -> None:
    _review_responses[stage] = data
    if stage in _review_events:
        _review_events[stage].set()


async def wait_for_review(stage: str, emit, review_data: dict) -> dict:
    event = asyncio.Event()
    _review_events[stage] = event
    await emit({"type": "review_request", "stage": stage, "data": review_data})
    await event.wait()
    response = _review_responses.pop(stage)
    del _review_events[stage]
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORMULATION_HEADER_RE = re.compile(
    r"^##\s+Formulation\s+(\d+)\s*:\s*(.+)$", re.MULTILINE
)


def _parse_formulation_headers(text: str) -> list[tuple[int, str, int, int]]:
    matches = list(_FORMULATION_HEADER_RE.finditer(text))
    results: list[tuple[int, str, int, int]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        results.append((int(m.group(1)), m.group(2).strip(), start, end))
    return results


def _paradigm_slugs_from_dir(subdir: str) -> list[str]:
    d = SAMPLE_DIR / subdir
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.md"))


def _reasoner_files_for_paradigm(slug: str) -> list[Path]:
    """Return reasoner JSON files whose name starts with the paradigm slug."""
    reasoner_dir = SAMPLE_DIR / "reasoner"
    if not reasoner_dir.is_dir():
        return []
    # Normalize: the file names use underscores where the slug uses hyphens
    norm = slug.replace("-", "_").replace(" ", "_").lower()
    return sorted(
        p for p in reasoner_dir.glob("*.json")
        if p.stem.lower().startswith(norm)
    )


def _builder_files_for_paradigm(slug: str) -> list[tuple[Path, Path | None]]:
    """Return (model_file, test_file_or_None) pairs for a paradigm."""
    builder_dir = SAMPLE_DIR / "builder"
    if not builder_dir.is_dir():
        return []
    norm = slug.replace("-", "_").replace(" ", "_").lower()
    model_files = sorted(
        p for p in builder_dir.glob("*_model.py")
        if p.stem.lower().startswith(norm.replace("-", "_"))
        or p.stem.lower().startswith(slug.lower())
    )
    results: list[tuple[Path, Path | None]] = []
    for mf in model_files:
        # Derive test file name: foo_model.py -> test_foo.py
        test_stem = "test_" + mf.stem.replace("_model", "")
        test_file = builder_dir / f"{test_stem}.py"
        results.append((mf, test_file if test_file.exists() else None))
    return results


# ---------------------------------------------------------------------------
# Connection manager (mirrors server.py)
# ---------------------------------------------------------------------------


class MockConnectionManager:
    def __init__(self) -> None:
        self.ws: WebSocket | None = None
        self.pipeline_task: asyncio.Task | None = None
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.current_stage: str | None = None
        self.pending_review: dict | None = None

    async def connect(self, ws: WebSocket) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        await ws.accept()
        self.ws = ws

    async def emit(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type == "node_add":
            self.nodes.append(msg["node"])
        elif msg_type == "edge_add":
            self.edges.append(msg["edge"])
        elif msg_type == "node_update":
            for n in self.nodes:
                if n["id"] == msg["id"]:
                    n["status"] = msg["status"]
                    break
        elif msg_type == "stage_change":
            self.current_stage = msg.get("stage")
        elif msg_type == "review_request":
            self.pending_review = msg
        elif msg_type == "graph_clear":
            self.nodes.clear()
            self.edges.clear()
        elif msg_type == "pipeline_done":
            self.pending_review = None

        if self.ws is not None:
            try:
                await self.ws.send_json(msg)
            except Exception:
                pass

    def reset(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.current_stage = None
        self.pending_review = None


manager = MockConnectionManager()


# ---------------------------------------------------------------------------
# Mock pipeline
# ---------------------------------------------------------------------------


async def run_mock_pipeline(emit, problem: str) -> None:  # noqa: ARG001 — problem ignored
    """Replay sample data as realistic pipeline events."""

    all_slugs = _paradigm_slugs_from_dir("deep")
    if not all_slugs:
        await emit({"type": "error", "message": "No sample data found in examples/sample-run/deep/"})
        return

    # ── RESEARCH ──────────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "research", "status": "running"})
    await emit({"type": "node_add", "node": {
        "id": "researcher", "kind": "agent", "label": "Researcher",
        "status": "running", "meta": {"color": "#4a9eff"},
    }})

    for slug in all_slugs:
        # web_search tool node
        search_id = f"search_{slug}"
        await emit({"type": "node_add", "node": {
            "id": search_id, "kind": "tool", "label": slug,
            "status": "running", "meta": {"args": {"query": slug}},
        }})
        await emit({"type": "edge_add", "edge": {"source": "researcher", "target": search_id}})
        await asyncio.sleep(0.3)
        await emit({"type": "node_update", "id": search_id, "status": "done"})

        # sub_agent deep-research node
        deep_id = f"deep_{slug}"
        await emit({"type": "node_add", "node": {
            "id": deep_id, "kind": "sub_agent", "label": slug,
            "status": "running", "meta": {"paradigm": slug},
        }})
        await emit({"type": "edge_add", "edge": {"source": "researcher", "target": deep_id}})
        await asyncio.sleep(0.4)
        await emit({"type": "node_update", "id": deep_id, "status": "done"})

        # file node
        deep_path = SAMPLE_DIR / "deep" / f"{slug}.md"
        content_preview = ""
        if deep_path.exists():
            content_preview = deep_path.read_text()[:500]
        file_id = f"file_deep_{slug}"
        await emit({"type": "node_add", "node": {
            "id": file_id, "kind": "file", "label": f"{slug}.md",
            "status": "done",
            "meta": {"path": f"deep/{slug}.md", "content": content_preview},
        }})
        await emit({"type": "edge_add", "edge": {"source": deep_id, "target": file_id}})

    await emit({"type": "node_update", "id": "researcher", "status": "done"})
    await emit({"type": "stage_change", "stage": "research", "status": "done"})

    # ── REVIEW_RESEARCH ───────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "review_research", "status": "running"})

    paradigms_data: list[dict] = []
    for slug in all_slugs:
        md_path = SAMPLE_DIR / "deep" / f"{slug}.md"
        content = md_path.read_text() if md_path.exists() else ""
        title = slug.replace("-", " ").title()
        summary = (content[:200].rsplit(".", 1)[0] + ".") if content else ""
        paradigms_data.append({
            "slug": slug, "title": title,
            "summary": summary, "content": content,
        })

    response = await wait_for_review("review_research", emit, {
        "paradigms": paradigms_data,
    })
    approved_slugs: list[str] = response.get("approved", all_slugs)
    if not approved_slugs:
        approved_slugs = all_slugs  # fallback so pipeline continues

    await emit({"type": "stage_change", "stage": "review_research", "status": "done"})

    # ── FORMALIZE ─────────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "formalize", "status": "running"})
    await emit({"type": "node_add", "node": {
        "id": "formalizer", "kind": "agent", "label": "Formalizer",
        "status": "running",
    }})
    await emit({"type": "edge_add", "edge": {"source": "researcher", "target": "formalizer"}})

    for slug in approved_slugs:
        sub_id = f"formalize_{slug}"
        await emit({"type": "node_add", "node": {
            "id": sub_id, "kind": "sub_agent", "label": slug,
            "status": "running", "meta": {"paradigm": slug},
        }})
        await emit({"type": "edge_add", "edge": {"source": "formalizer", "target": sub_id}})
        await asyncio.sleep(0.3)
        await emit({"type": "node_update", "id": sub_id, "status": "done"})

        form_path = SAMPLE_DIR / "formulations" / f"{slug}.md"
        content_preview = ""
        if form_path.exists():
            content_preview = form_path.read_text()[:500]
        file_id = f"file_form_{slug}"
        await emit({"type": "node_add", "node": {
            "id": file_id, "kind": "file", "label": f"{slug}.md",
            "status": "done",
            "meta": {"path": f"formulations/{slug}.md", "content": content_preview},
        }})
        await emit({"type": "edge_add", "edge": {"source": sub_id, "target": file_id}})

    await emit({"type": "node_update", "id": "formalizer", "status": "done"})
    await emit({"type": "stage_change", "stage": "formalize", "status": "done"})

    # ── REVIEW_FORMALIZE ──────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "review_formalize", "status": "running"})

    formalize_data: list[dict] = []
    for slug in approved_slugs:
        md_path = SAMPLE_DIR / "formulations" / f"{slug}.md"
        if not md_path.exists():
            continue
        text = md_path.read_text()
        headers = _parse_formulation_headers(text)
        formulations = [
            {"id": num, "name": name, "content": text[start:end]}
            for num, name, start, end in headers
        ]
        formalize_data.append({
            "slug": slug, "content": text,
            "formulations": formulations,
        })

    response = await wait_for_review("review_formalize", emit, {
        "paradigms": formalize_data,
    })
    # Not used to filter further in mock — we just continue with approved_slugs
    await emit({"type": "stage_change", "stage": "review_formalize", "status": "done"})

    # ── GET_ENV_SPEC ──────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "get_env_spec", "status": "running"})

    env_spec_path = SAMPLE_DIR / "env_spec.json"
    env_spec_content = ""
    if env_spec_path.exists():
        env_spec_content = env_spec_path.read_text()

    response = await wait_for_review("get_env_spec", emit, {
        "message": "Please provide the environment specification (env_spec.json).",
        "default_content": env_spec_content,
    })

    await emit({"type": "stage_change", "stage": "get_env_spec", "status": "done"})

    # ── REASON ────────────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "reason", "status": "running"})
    await emit({"type": "node_add", "node": {
        "id": "reasoner", "kind": "agent", "label": "Reasoner",
        "status": "running",
    }})
    await emit({"type": "edge_add", "edge": {"source": "formalizer", "target": "reasoner"}})

    all_spec_files: list[Path] = []
    for slug in approved_slugs:
        spec_files = _reasoner_files_for_paradigm(slug)
        all_spec_files.extend(spec_files)
        for sf in spec_files:
            spec_id = sf.stem
            sub_id = f"reason_{spec_id}"
            await emit({"type": "node_add", "node": {
                "id": sub_id, "kind": "sub_agent", "label": spec_id,
                "status": "running", "meta": {"paradigm": slug, "spec": spec_id},
            }})
            await emit({"type": "edge_add", "edge": {"source": "reasoner", "target": sub_id}})
            await asyncio.sleep(0.2)
            await emit({"type": "node_update", "id": sub_id, "status": "done"})

            content_preview = ""
            try:
                content_preview = sf.read_text()[:500]
            except OSError:
                pass
            file_id = f"file_reason_{spec_id}"
            await emit({"type": "node_add", "node": {
                "id": file_id, "kind": "file", "label": f"{spec_id}.json",
                "status": "done",
                "meta": {"path": f"reasoner/{spec_id}.json", "content": content_preview},
            }})
            await emit({"type": "edge_add", "edge": {"source": sub_id, "target": file_id}})

    await emit({"type": "node_update", "id": "reasoner", "status": "done"})
    await emit({"type": "stage_change", "stage": "reason", "status": "done"})

    # ── REVIEW_REASON ─────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "review_reason", "status": "running"})

    specs_data: list[dict] = []
    for sf in all_spec_files:
        try:
            data = json.loads(sf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        specs_data.append({
            "id": data.get("formulation_id", sf.stem),
            "spec_id": data.get("formulation_id", sf.stem),
            "paradigm": data.get("paradigm", "unknown"),
            "name": data.get("name", sf.stem),
            "description": data.get("description", ""),
            "variables": data.get("variables", []),
            "env_mapping": data.get("env_mapping", {}),
            "full_spec": data,
        })

    response = await wait_for_review("review_reason", emit, {"specs": specs_data})
    await emit({"type": "stage_change", "stage": "review_reason", "status": "done"})

    # ── BUILD ─────────────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "build", "status": "running"})
    await emit({"type": "node_add", "node": {
        "id": "builder", "kind": "agent", "label": "Builder",
        "status": "running",
    }})
    await emit({"type": "edge_add", "edge": {"source": "reasoner", "target": "builder"}})

    builder_pairs: list[tuple[Path, Path | None]] = []
    for slug in approved_slugs:
        builder_pairs.extend(_builder_files_for_paradigm(slug))

    for model_file, test_file in builder_pairs:
        model_id = model_file.stem
        sub_id = f"build_{model_id}"
        await emit({"type": "node_add", "node": {
            "id": sub_id, "kind": "sub_agent", "label": model_id,
            "status": "running", "meta": {"model": model_id},
        }})
        await emit({"type": "edge_add", "edge": {"source": "builder", "target": sub_id}})
        await asyncio.sleep(0.4)
        await emit({"type": "node_update", "id": sub_id, "status": "done"})

        code_preview = ""
        try:
            code_preview = model_file.read_text()[:800]
        except OSError:
            pass
        file_id = f"file_build_{model_id}"
        await emit({"type": "node_add", "node": {
            "id": file_id, "kind": "file", "label": model_file.name,
            "status": "done",
            "meta": {"path": f"builder/{model_file.name}", "content": code_preview},
        }})
        await emit({"type": "edge_add", "edge": {"source": sub_id, "target": file_id}})

        if test_file:
            test_preview = ""
            try:
                test_preview = test_file.read_text()[:500]
            except OSError:
                pass
            test_id = f"file_test_{model_id}"
            await emit({"type": "node_add", "node": {
                "id": test_id, "kind": "file", "label": test_file.name,
                "status": "done",
                "meta": {"path": f"builder/{test_file.name}", "content": test_preview},
            }})
            await emit({"type": "edge_add", "edge": {"source": sub_id, "target": test_id}})

    await emit({"type": "node_update", "id": "builder", "status": "done"})
    await emit({"type": "stage_change", "stage": "build", "status": "done"})

    # ── REVIEW_BUILD ──────────────────────────────────────────────────────
    await emit({"type": "stage_change", "stage": "review_build", "status": "running"})

    models_data: list[dict] = []
    for model_file, test_file in builder_pairs:
        code = ""
        try:
            code = model_file.read_text()
        except OSError:
            pass
        test_results = ""
        if test_file:
            try:
                test_results = test_file.read_text()
            except OSError:
                pass
        lower = (code + test_results).lower()
        has_issues = any(w in lower for w in ("error", "fail", "traceback", "exception"))
        models_data.append({
            "slug": model_file.stem,
            "code": code,
            "test_results": test_results,
            "passed": not has_issues,
        })

    response = await wait_for_review("review_build", emit, {"models": models_data})

    decisions = response.get("decisions", {})
    all_approved = all(d.get("approved", False) for d in decisions.values()) if decisions else True

    await emit({"type": "stage_change", "stage": "review_build", "status": "done"})

    if all_approved:
        await emit({"type": "pipeline_done"})
    else:
        # In the mock we just finish — no real rerun cascade
        await emit({"type": "pipeline_done"})


# ---------------------------------------------------------------------------
# WebSocket endpoint (mirrors server.py)
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)

    # Reconnection: re-emit pending state
    if manager.pipeline_task and not manager.pipeline_task.done():
        if manager.pending_review:
            await ws.send_json(manager.pending_review)
        else:
            await ws.send_json({
                "type": "state_sync",
                "nodes": manager.nodes,
                "edges": manager.edges,
                "stage": manager.current_stage,
            })

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "start":
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                manager.reset()
                problem: str = data.get("problem", "mock run")
                manager.pipeline_task = asyncio.create_task(
                    _run_with_error_handling(manager.emit, problem)
                )

            elif msg_type == "review_response":
                handle_review_response(data["stage"], data["data"])

            elif msg_type == "cancel":
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                    manager.reset()

    except WebSocketDisconnect:
        manager.ws = None


async def _run_with_error_handling(emit, problem: str) -> None:
    try:
        await run_mock_pipeline(emit, problem)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Mock pipeline failed")
        await emit({"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
