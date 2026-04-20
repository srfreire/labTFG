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
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "examples" / "sample-run"

app = FastAPI(title="DecisionLab Mock")


# Synthetic knowledge-graph snapshot state — grows as the mock pipeline runs
_kg_state: dict = {"run_id": None, "new_count": 0}

# Pre-canned graph — a bigger backbone the "Memory Agent" reveals chunk by chunk
_SYNTHETIC_KG: dict = {
    "nodes": [
        # New-run candidates — surfaced incrementally as memory_agent ticks
        {
            "id": "p_delta_rule", "label": "Paradigm", "display": "Delta Rule",
            "properties": {
                "slug": "delta-rule",
                "name": "Delta Rule",
                "summary": "Associative learning rule where value updates proportional to prediction error.",
                "year": 1972,
                "citations": 12843,
                "created_at": "2025-11-04T09:12:44Z",
            },
        },
        {
            "id": "v_prediction_error", "label": "Variable", "display": "prediction_error",
            "properties": {
                "name": "prediction_error",
                "symbol": "δ",
                "units": "reward-units",
                "description": "Difference between received and expected reward.",
            },
        },
        {
            "id": "a_rescorla", "label": "Author", "display": "Rescorla",
            "properties": {
                "name": "Rescorla",
                "full_name": "Robert A. Rescorla",
                "affiliation": "University of Pennsylvania",
                "h_index": 72,
            },
        },
        {
            "id": "a_wagner", "label": "Author", "display": "Wagner",
            "properties": {
                "name": "Wagner",
                "full_name": "Allan R. Wagner",
                "affiliation": "Yale University",
                "h_index": 58,
            },
        },
        {
            "id": "eq_delta", "label": "Equation", "display": "dV = alpha (lambda - V)",
            "properties": {
                "latex": "\\Delta V = \\alpha (\\lambda - V)",
                "plain": "dV = alpha (lambda - V)",
                "description": "Incremental value update by scaled prediction error.",
            },
        },
        {
            "id": "f_delta_1", "label": "Formulation", "display": "DeltaRule-v1",
            "properties": {
                "id": "DeltaRule-v1",
                "variant": "canonical",
                "stochastic": False,
                "discrete_time": True,
            },
        },
        # Existing backbone
        {
            "id": "p_td", "label": "Paradigm", "display": "TD Learning",
            "properties": {
                "slug": "td-learning",
                "name": "TD Learning",
                "summary": "Temporal-difference learning — bootstraps value updates from successor estimates.",
                "year": 1988,
                "citations": 24910,
            },
        },
        {
            "id": "p_q", "label": "Paradigm", "display": "Q-Learning",
            "properties": {
                "slug": "q-learning",
                "name": "Q-Learning",
                "summary": "Off-policy TD control that learns state-action values.",
                "year": 1989,
                "citations": 31205,
            },
        },
        {
            "id": "v_reward", "label": "Variable", "display": "reward",
            "properties": {
                "name": "reward",
                "symbol": "r",
                "units": "arbitrary",
                "description": "Scalar signal from the environment.",
            },
        },
        {
            "id": "v_value", "label": "Variable", "display": "value",
            "properties": {
                "name": "value",
                "symbol": "V(s)",
                "units": "expected discounted reward",
                "description": "Estimated return from a given state.",
            },
        },
        {
            "id": "a_sutton", "label": "Author", "display": "Sutton",
            "properties": {
                "name": "Sutton",
                "full_name": "Richard S. Sutton",
                "affiliation": "University of Alberta / DeepMind",
                "h_index": 89,
            },
        },
        {
            "id": "eq_td", "label": "Equation", "display": "V <- V + alpha * delta",
            "properties": {
                "latex": "V \\leftarrow V + \\alpha \\delta",
                "plain": "V <- V + alpha * delta",
                "description": "One-step TD update rule.",
            },
        },
        {
            "id": "b_striatum", "label": "BrainRegion", "display": "Striatum",
            "properties": {
                "name": "Striatum",
                "anatomy": "basal ganglia",
                "function": "reward prediction & action selection",
            },
        },
    ],
    "relations": [
        {"id": "r1", "source": "p_delta_rule", "target": "v_prediction_error", "type": "USES_EQUATION", "properties": {"note": "central variable"}},
        {"id": "r2", "source": "a_rescorla", "target": "p_delta_rule", "type": "AUTHORED", "properties": {"year": 1972}},
        {"id": "r3", "source": "a_wagner", "target": "p_delta_rule", "type": "AUTHORED", "properties": {"year": 1972}},
        {"id": "r4", "source": "p_delta_rule", "target": "eq_delta", "type": "USES_EQUATION", "properties": {}},
        {"id": "r5", "source": "f_delta_1", "target": "p_delta_rule", "type": "DERIVES_FROM", "properties": {"confidence": 0.92}},
        {"id": "r6", "source": "p_td", "target": "p_delta_rule", "type": "EXTENDS", "properties": {"generalisation": "temporal credit"}},
        {"id": "r7", "source": "p_q", "target": "p_td", "type": "EXTENDS", "properties": {"control": "off-policy"}},
        {"id": "r8", "source": "a_sutton", "target": "p_td", "type": "AUTHORED", "properties": {"year": 1988}},
        {"id": "r9", "source": "p_td", "target": "v_value", "type": "USES_EQUATION", "properties": {}},
        {"id": "r10", "source": "v_reward", "target": "b_striatum", "type": "MODULATES", "properties": {"pathway": "dopaminergic"}},
        {"id": "r11", "source": "p_td", "target": "eq_td", "type": "USES_EQUATION", "properties": {}},
    ],
}

# Node IDs that the memory agent "reveals" in order, one chunk per stage.
_NEW_NODE_SEQUENCE: list[list[str]] = [
    ["p_delta_rule", "a_rescorla", "a_wagner"],   # RESEARCH
    ["v_prediction_error", "eq_delta"],            # FORMALIZE
    ["f_delta_1"],                                  # REASON
    [],                                             # BUILD — no new nodes, strengthens existing
]

# Relations tagged to current run (same length as _NEW_NODE_SEQUENCE).
_NEW_REL_SEQUENCE: list[list[str]] = [
    ["r2", "r3"],
    ["r1", "r4"],
    ["r5"],
    [],
]


@app.get("/api/kg/snapshot")
async def kg_snapshot() -> dict:
    """Return a synthetic snapshot of the KG.

    The number of ``new`` nodes/edges (tagged with the current ``run_id``) grows
    as the mock pipeline ticks off stages — so the frontend delta view can
    visualise memory-agent population.
    """
    run_id = _kg_state.get("run_id")
    revealed_nodes: set[str] = set()
    revealed_rels: set[str] = set()
    if run_id is not None:
        for chunk in _NEW_NODE_SEQUENCE[: _kg_state["new_count"]]:
            revealed_nodes.update(chunk)
        for chunk in _NEW_REL_SEQUENCE[: _kg_state["new_count"]]:
            revealed_rels.update(chunk)

    nodes = [
        {
            **n,
            "run_ids": [run_id] if n["id"] in revealed_nodes else [],
            "properties": n.get("properties", {}),
        }
        for n in _SYNTHETIC_KG["nodes"]
    ]
    relations = [
        {
            **r,
            "run_id": run_id if r["id"] in revealed_rels else None,
            "properties": r.get("properties", {}),
        }
        for r in _SYNTHETIC_KG["relations"]
    ]
    return {"nodes": nodes, "relations": relations}

# ---------------------------------------------------------------------------
# Realistic search data
# ---------------------------------------------------------------------------

BROAD_SEARCHES = [
    {
        "query": "food intake decision-making paradigms psychology neuroscience",
        "results": [
            "Homeostatic and hedonic signals interact in the regulation of food intake — Lutter & Nestler (2009), J. Nutrition",
            "Decision-making models for food intake: integrating homeostatic, reward, and cognitive factors — Rangel (2013), Curr. Opin. Neurobiology",
            "The psychology of food choice: from behavioral economics to computational neuroscience — Berkman et al. (2017), Appetite",
        ],
    },
    {
        "query": "computational models eating behavior reward homeostasis",
        "results": [
            "A reinforcement learning theory for homeostatic regulation — Keramati & Gutkin (2011), NeurIPS",
            "Incentive salience and the transition to compulsive eating — Berridge (2009), Physiology & Behavior",
            "Allostatic model of food reward and energy regulation — Schulkin (2003), Cambridge University Press",
        ],
    },
    {
        "query": "food choice theories cognitive control gut-brain axis review",
        "results": [
            "Executive control of eating: the role of prefrontal cortex — Hare et al. (2009), Science",
            "Gut-brain axis: gut feelings, bacterial signaling, and appetite — Mayer et al. (2015), J. Neuroscience",
            "Associative learning and conditioned food preferences — Petrovich (2013), Annals NY Acad. Sci.",
        ],
    },
]

DEEP_SEARCH_DATA: dict[str, list[dict]] = {
    "homeostatic-regulation": [
        {"query": "homeostatic regulation food intake set point theory Claude Bernard Cannon",
         "results": ["Cannon WB (1932) The Wisdom of the Body — homeostasis defined", "Keramati & Gutkin (2011) Homeostatic RL — NeurIPS"]},
        {"query": "PI controller biological homeostasis glucose insulin model",
         "results": ["npj Digital Medicine (2020) Homeostasis as PI control", "Drengstig et al. (2012) Homeostatic controller motifs"]},
        {"query": "drive reduction theory feeding behavior mathematical formulation",
         "results": ["Yin H (2025) Linking homeostasis to RL — ScienceDirect", "Gross et al. (2024) Functional approach to homeostasis — Biology Direct"]},
    ],
    "hedonic-reward-based-regulation-of-food-intake": [
        {"query": "hedonic reward food intake dopamine pathway model",
         "results": ["Berridge KC (2007) The debate over dopamine's role in reward", "Small DM (2009) Individual differences in neurophysiology of reward"]},
        {"query": "pleasure-based eating palatability mathematical model dual process",
         "results": ["Finlayson et al. (2007) Dual-process model of food reward", "Cabanac M (1971) Physiological role of pleasure — Science"]},
    ],
    "incentive-salience-theory": [
        {"query": "incentive salience theory Berridge wanting vs liking dopamine",
         "results": ["Berridge KC (2012) From prediction error to incentive salience", "Robinson & Berridge (1993) Neural basis of drug craving"]},
        {"query": "incentive salience computational model TD learning",
         "results": ["Zhang et al. (2009) Neural model of incentive sensitization", "McClure et al. (2003) Temporal prediction errors in RL"]},
    ],
    "associative-learning-and-conditioned-appetite": [
        {"query": "associative learning conditioned appetite Pavlovian food cue",
         "results": ["Petrovich GD (2013) Forebrain networks and conditioned feeding", "Holland PC (2004) Relations between Pavlovian and instrumental learning"]},
        {"query": "Rescorla-Wagner model food conditioning mathematical formulation",
         "results": ["Rescorla RA & Wagner AR (1972) Classical conditioning theory", "Dayan & Berridge (2009) Expected and unexpected good feelings"]},
    ],
    "cognitive-executive-control-of-eating-behavior": [
        {"query": "executive control eating behavior prefrontal cortex inhibition",
         "results": ["Hare et al. (2009) Self-control in decision-making — Science", "Rangel et al. (2008) Framework for studying value-based choices"]},
        {"query": "drift diffusion model food choice inhibitory control",
         "results": ["Krajbich et al. (2010) DDM of simple food choice", "Sullivan et al. (2015) Dietary self-control and the vmPFC"]},
    ],
    "gut-brain-axis-signaling-in-food-intake-regulation": [
        {"query": "gut-brain axis signaling food intake GLP-1 ghrelin hormones",
         "results": ["Mayer EA (2011) Gut feelings — Nature Rev. Neuroscience", "Holst JJ (2007) GLP-1 physiology — Physiological Reviews"]},
        {"query": "microbiome gut-brain communication eating behavior computational",
         "results": ["Cryan & Dinan (2012) Mind-altering microorganisms — Nature Rev. Neuroscience", "Fetissov & Déchelotte (2011) Autoantibodies and appetite"]},
    ],
    "allostatic-opponent-process-model-of-food-intake": [
        {"query": "allostatic opponent process model food intake Schulkin Koob",
         "results": ["Schulkin J (2003) Allostasis — Cambridge Press", "Koob & Le Moal (2001) Drug addiction, dysregulation of reward"]},
        {"query": "opponent process theory eating reward adaptation Solomon",
         "results": ["Solomon RL (1980) The opponent-process theory of motivation", "Sterling P (2012) Allostasis: a model of predictive regulation"]},
    ],
}

FORMALIZE_SEARCH_DATA: dict[str, list[dict]] = {
    "homeostatic-regulation": [
        {"query": "homeostatic control theory ODE PI controller formulation biology",
         "results": ["Drengstig et al. (2012) Basic set of homeostatic controller motifs", "npj Digital Medicine (2020) PI model of glucose homeostasis"]},
        {"query": "reinforcement learning homeostatic drive reduction MDP Keramati",
         "results": ["Keramati & Gutkin (2011) RL theory for homeostatic regulation — NeurIPS", "Yin (2025) Homeostasis–RL integration"]},
    ],
    "hedonic-reward-based-regulation-of-food-intake": [
        {"query": "hedonic dual process model food reward mathematical formalization",
         "results": ["Finlayson et al. (2007) Measuring food reward", "Berridge & Robinson (2016) Liking, wanting, and incentive salience"]},
    ],
    "incentive-salience-theory": [
        {"query": "incentive salience wanting computational model TD learning reward",
         "results": ["Berridge (2012) From prediction error to incentive salience", "Zhang et al. (2009) Neural model incentive sensitization"]},
    ],
    "associative-learning-and-conditioned-appetite": [
        {"query": "Rescorla-Wagner model mathematical formulation conditioning appetitive",
         "results": ["Rescorla & Wagner (1972) Classical conditioning variations", "Sutton & Barto (2018) RL: An Introduction — eligibility traces"]},
    ],
    "cognitive-executive-control-of-eating-behavior": [
        {"query": "drift diffusion model food choice mathematical formulation inhibitory",
         "results": ["Krajbich et al. (2010) Visual fixations and food value DDM", "Ratcliff & McKoon (2008) Diffusion decision model"]},
    ],
    "gut-brain-axis-signaling-in-food-intake-regulation": [
        {"query": "gut-brain axis ODE model neuroendocrine signaling food intake",
         "results": ["Mayer (2011) Gut feelings — interoceptive signals model", "Holst (2007) GLP-1 receptor dynamics"]},
    ],
    "allostatic-opponent-process-model-of-food-intake": [
        {"query": "allostatic load opponent process mathematical model Koob Sterling",
         "results": ["Koob & Le Moal (2001) Drug addiction reward dysregulation", "Sterling (2012) Allostasis predictive regulation model"]},
    ],
}

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

from decisionlab.parsing import parse_formulation_headers


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
        test_stem = "test_" + mf.stem.replace("_model", "")
        test_file = builder_dir / f"{test_stem}.py"
        results.append((mf, test_file if test_file.exists() else None))
    return results


def _read_file_full(path: Path) -> str:
    """Read full file content (no truncation)."""
    try:
        return path.read_text()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Connection manager (mirrors server.py)
# ---------------------------------------------------------------------------


# In-memory record of past runs so the mock can exercise the replay feature
# without a database or S3. One entry per run_id.
_run_records: dict[str, dict] = {}
_run_events: dict[str, list[dict]] = {}


# Node kinds that contribute to the replay stats bar (nodes / running / done /
# errors / time / tokens / cost). Static nodes (output, file, search) are
# artefacts, not billable work — exclude them.
_STATS_KINDS = {"agent", "sub_agent", "tool"}


def _synthetic_stats_for_kind(kind: str) -> tuple[int, float]:
    """Rough token/cost sample for the mock. Agents burn the most (multi-turn
    reasoning), sub-agents and tools much less. Cost uses a rough midpoint
    between Claude Sonnet input ($3/MTok) and output ($15/MTok) pricing."""
    if kind == "agent":
        tokens = random.randint(5000, 12000)
    elif kind == "sub_agent":
        tokens = random.randint(2000, 6000)
    else:  # tool
        tokens = random.randint(200, 1500)
    return tokens, tokens * 8e-6


def _seed_past_run() -> None:
    """Populate one completed run at module load so the landing page has
    something in its Past Runs list on a fresh mock boot."""
    run_id = "seed-survival-001"
    started_at = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat().replace("+00:00", "Z")

    base_ts = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp() * 1000)
    t_start = base_ts
    t_tool = base_ts + 2_400
    t_done = base_ts + 4_800

    raw: list[dict] = [
        {"type": "run_start", "run_id": run_id},
        {"type": "stage_change", "stage": "research", "status": "running"},
        {
            "type": "node_add",
            "node": {
                "id": "researcher",
                "kind": "agent",
                "label": "Researcher",
                "status": "running",
                "metadata": {"startedAt": t_start},
            },
        },
        {
            "type": "node_add",
            "node": {
                "id": "ws-1",
                "kind": "tool",
                "label": "web_search",
                "parent_id": "researcher",
                "status": "done",
                "meta": {
                    "toolType": "web_search",
                    "query": "optimal foraging under uncertainty",
                },
                "metadata": {
                    "startedAt": t_tool,
                    "endedAt": t_tool + 800,
                    "tokens": 940,
                    "cost": 940 * 8e-6,
                },
            },
        },
        {
            "type": "edge_add",
            "edge": {
                "source": "researcher",
                "target": "ws-1",
                "edge_kind": "spawn",
            },
        },
        {
            "type": "node_add",
            "node": {
                "id": "para-foraging",
                "kind": "output",
                "label": "foraging.md",
                "parent_id": "researcher",
                "status": "done",
                "meta": {
                    "stage": "research",
                    "path": "foraging.md",
                    "content": (
                        "# Optimal Foraging Theory\n\n"
                        "Agents choose patches to maximize long-run energy "
                        "intake net of travel and handling costs.\n"
                    ),
                },
            },
        },
        {
            "type": "edge_add",
            "edge": {
                "source": "researcher",
                "target": "para-foraging",
                "edge_kind": "write",
            },
        },
        {
            "type": "node_update",
            "id": "researcher",
            "status": "done",
            "metadata": {
                "endedAt": t_done,
                "tokens": 7_850,
                "cost": 7_850 * 8e-6,
            },
        },
        {"type": "stage_change", "stage": "research", "status": "done"},
        {"type": "pipeline_done"},
    ]

    events = [
        {"seq": i, "ts": base_ts + i * 200, **ev}
        for i, ev in enumerate(raw, start=1)
    ]
    _run_events[run_id] = events
    _run_records[run_id] = {
        "run_id": run_id,
        "problem": "Survival decision-making under uncertainty",
        "status": "done",
        "started_at": started_at,
        "artifact_count": 1,
    }


_seed_past_run()


def _is_spawn_for(msg: dict, buffered_node_add: dict) -> bool:
    """True if `msg` is a spawn edge_add targeting the buffered node_add.
    Missing `edge_kind` is treated as spawn (matches the frontend's legacy
    parent_id derivation)."""
    if msg.get("type") != "edge_add":
        return False
    edge = msg.get("edge")
    if not isinstance(edge, dict):
        return False
    if edge.get("edge_kind") not in (None, "spawn"):
        return False
    return edge.get("target") == (buffered_node_add.get("node") or {}).get("id")


class MockConnectionManager:
    def __init__(self) -> None:
        self.ws: WebSocket | None = None
        self.pipeline_task: asyncio.Task | None = None
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.current_stage: str | None = None
        self.pending_review: dict | None = None
        self._emit_lock = asyncio.Lock()
        self._seq: int = 0
        self._run_id: str | None = None
        # Hold one node_add while we wait to see whether the next event is a
        # spawn edge to the same node. If so, we fold parent_id onto the
        # node_add payload and drop the redundant edge.
        self._pending_node_add: dict | None = None

    async def connect(self, ws: WebSocket) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        await ws.accept()
        self.ws = ws

    def _record_event(self, msg: dict) -> None:
        if self._run_id is None:
            return
        self._seq += 1
        stamped = {"seq": self._seq, "ts": int(time.time() * 1000), **msg}
        _run_events.setdefault(self._run_id, []).append(stamped)

    async def emit(self, msg: dict) -> None:
        """Thread-safe emit — serializes concurrent sends from parallel tasks."""
        async with self._emit_lock:
            # Fold a following spawn edge into the previous node_add's
            # parent_id so the frontend never needs late-edge parent_id
            # derivation. See `_pending_node_add` docstring.
            if self._pending_node_add is not None:
                buffered = self._pending_node_add
                if _is_spawn_for(msg, buffered):
                    buffered["node"].setdefault(
                        "parent_id", msg["edge"]["source"]
                    )
                    self._pending_node_add = None
                    await self._emit_raw(buffered)
                    return  # spawn edge absorbed into parent_id
                self._pending_node_add = None
                await self._emit_raw(buffered)

            if msg.get("type") == "node_add":
                node = msg.get("node") or {}
                if not node.get("parent_id"):
                    self._pending_node_add = msg
                    return

            await self._emit_raw(msg)

    async def _flush_pending_node_add_locked(self) -> None:
        """Flush any buffered node_add. Caller must hold `_emit_lock`."""
        if self._pending_node_add is not None:
            buffered = self._pending_node_add
            self._pending_node_add = None
            await self._emit_raw(buffered)

    async def _emit_raw(self, msg: dict) -> None:
        """Apply bookkeeping, persist, send. Caller must hold `_emit_lock`."""
        msg_type = msg.get("type")

        # Start a new run log on run_start
        if msg_type == "run_start":
            run_id = msg.get("run_id")
            if run_id:
                self._run_id = run_id
                self._seq = 0
                _run_events[run_id] = []
                _run_records[run_id] = {
                    "run_id": run_id,
                    "problem": _current_problem.get("value", "mock run"),
                    "status": "running",
                    "started_at": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "artifact_count": None,
                }

        if msg_type == "node_add":
            node = msg["node"]
            # Stamp startedAt on billable nodes so the replay StatsBar
            # (nodes / running / done / time / tokens / cost) can compute
            # wall time. Sits on `metadata` (the field agrex reads),
            # parallel to the existing labTFG `meta` field.
            if node.get("kind") in _STATS_KINDS:
                md = dict(node.get("metadata") or {})
                md.setdefault("startedAt", int(time.time() * 1000))
                node["metadata"] = md
            self.nodes.append(node)
        elif msg_type == "edge_add":
            self.edges.append(msg["edge"])
        elif msg_type == "node_update":
            for n in self.nodes:
                if n["id"] == msg["id"]:
                    n["status"] = msg["status"]
                    # When a billable node completes, enrich the outgoing
                    # update with endedAt + synthetic tokens/cost and
                    # mirror them onto our in-memory node so state_sync
                    # keeps replays consistent. agrex's store.updateNode
                    # merges the incoming `metadata` with the existing
                    # one, so we don't need to include previous fields.
                    kind = n.get("kind")
                    if msg.get("status") == "done" and kind in _STATS_KINDS:
                        tokens, cost = _synthetic_stats_for_kind(kind)
                        md = dict(msg.get("metadata") or {})
                        md.setdefault("endedAt", int(time.time() * 1000))
                        md.setdefault("tokens", tokens)
                        md.setdefault("cost", cost)
                        msg["metadata"] = md
                        merged = dict(n.get("metadata") or {})
                        merged.update(md)
                        n["metadata"] = merged
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
            if self._run_id and self._run_id in _run_records:
                rec = _run_records[self._run_id]
                rec["status"] = "done"
                # Count "output" nodes as the mock's artifact-count proxy
                rec["artifact_count"] = sum(
                    1 for n in self.nodes if n.get("kind") == "output"
                )

        self._record_event(msg)

        if self.ws is not None:
            try:
                await self.ws.send_json(msg)
            except Exception:
                pass

    async def cancel_and_mark(self) -> None:
        if self._run_id and self._run_id in _run_records:
            _run_records[self._run_id]["status"] = "cancelled"

    async def handle_review_response(self, data: dict) -> None:
        """Emit a review_decision event (so replays reconstruct approvals),
        then dispatch to the mock's own review handler."""
        stage = data["stage"]
        payload = data["data"]
        approved = payload.get("approved") if isinstance(payload, dict) else None
        await self.emit(
            {
                "type": "review_decision",
                "stage": stage,
                "approved": approved if approved is not None else payload,
            }
        )
        handle_review_response(stage, payload)

    def reset(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.current_stage = None
        self.pending_review = None


# Captured across a run so `run_start` can record the problem into _run_records.
_current_problem: dict[str, str] = {}
manager = MockConnectionManager()


# ---------------------------------------------------------------------------
# Parallel sub-task helpers
# ---------------------------------------------------------------------------


async def _emit_retrieve_knowledge(
    emit,
    *,
    node_id: str,
    source_id: str,
    query: str,
    namespace: str,
    results_hint: list[str] | None = None,
) -> None:
    """Emit a single retrieve_knowledge tool call: node_add → (delay) → node_update.

    Mirrors the shape of the real pipeline's retrieve_knowledge tool event so
    the agent graph shows the KG retrieval step alongside read/write/search.
    """
    await emit({"type": "node_add", "node": {
        "id": node_id, "kind": "tool", "label": query[:42] + ("..." if len(query) > 42 else ""),
        "status": "running",
        "meta": {
            "toolType": "retrieve_knowledge",
            "args": {"query": query, "namespace": namespace, "top_k": 5},
            "results": results_hint or [],
        },
    }})
    await emit({"type": "edge_add", "edge": {
        "source": source_id, "target": node_id, "edge_kind": "spawn",
    }})
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await emit({"type": "node_update", "id": node_id, "status": "done"})


async def _research_deep(emit, slug: str, jitter: float) -> None:
    """Simulate one Deep Researcher sub-agent (runs concurrently with others)."""
    await asyncio.sleep(jitter)

    deep_id = f"deep_{slug}"
    await emit({"type": "node_add", "node": {
        "id": deep_id, "kind": "sub_agent", "label": "Deep Researcher",
        "status": "running", "meta": {"paradigm": slug},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": "researcher", "target": deep_id, "edge_kind": "spawn",
    }})

    # retrieve_knowledge: check the KG before running paper/web searches
    await _emit_retrieve_knowledge(
        emit,
        node_id=f"kg_deep_{slug}",
        source_id=deep_id,
        query=f"{slug.replace('-', ' ')} postulates and primary locus",
        namespace="paradigm",
        results_hint=[f"Prior deep report on {slug} (run_id older)"],
    )

    # 2-3 web searches per paradigm (in parallel within this sub-agent)
    searches = DEEP_SEARCH_DATA.get(slug, [
        {"query": f"{slug.replace('-', ' ')} decision-making theory",
         "results": ["General reference found"]},
    ])

    search_ids = []
    for i, search in enumerate(searches):
        search_id = f"search_deep_{slug}_{i}"
        search_ids.append(search_id)
        await asyncio.sleep(random.uniform(0.3, 0.6))
        await emit({"type": "node_add", "node": {
            "id": search_id, "kind": "search",
            "label": search["query"][:42] + "...",
            "status": "running",
            "meta": {"query": search["query"], "results": search["results"]},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": deep_id, "target": search_id, "edge_kind": "spawn",
        }})

    # Complete searches after a realistic delay
    await asyncio.sleep(random.uniform(1.0, 2.0))
    for sid in search_ids:
        await emit({"type": "node_update", "id": sid, "status": "done"})

    # write_file tool → output
    write_id = f"write_deep_{slug}"
    await asyncio.sleep(random.uniform(0.5, 1.0))
    await emit({"type": "node_add", "node": {
        "id": write_id, "kind": "tool", "label": f"{slug}.md",
        "status": "running",
        "meta": {"toolType": "write_file", "args": {"path": f"deep/{slug}.md"}},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": deep_id, "target": write_id, "edge_kind": "spawn",
    }})

    deep_path = SAMPLE_DIR / "deep" / f"{slug}.md"
    content = _read_file_full(deep_path)
    file_id = f"file_deep_{slug}"

    await asyncio.sleep(random.uniform(0.5, 0.8))
    await emit({"type": "node_update", "id": write_id, "status": "done"})
    await emit({"type": "node_update", "id": deep_id, "status": "done"})
    await emit({"type": "node_add", "node": {
        "id": file_id, "kind": "output", "label": f"{slug}.md",
        "status": "done",
        "meta": {"path": f"deep/{slug}.md", "content": content, "stage": "research"},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": write_id, "target": file_id, "edge_kind": "write",
    }})


async def _formalize_paradigm(emit, slug: str, jitter: float) -> None:
    """Simulate one Formalizer agent (full agent, not sub-agent).

    Spawned from the research output artifact it reads, so the graph grows
    outward uniformly from each paradigm's branch.
    """
    await asyncio.sleep(jitter)

    agent_id = f"formalize_{slug}"
    await emit({"type": "node_add", "node": {
        "id": agent_id, "kind": "agent", "label": "Formalizer",
        "status": "running", "meta": {"paradigm": slug},
    }})
    # Invisible layout edge — positions agent near the artifact, not rendered
    await emit({"type": "edge_add", "edge": {
        "source": f"file_deep_{slug}", "target": agent_id, "edge_kind": "layout",
    }})

    # retrieve_knowledge: look up prior formulations for this paradigm
    await _emit_retrieve_knowledge(
        emit,
        node_id=f"kg_form_{slug}",
        source_id=agent_id,
        query=f"{slug.replace('-', ' ')} mathematical formulation patterns",
        namespace="formulation",
        results_hint=[f"Known equations for {slug} from prior runs"],
    )

    # read_file tool (reads the research file)
    read_id = f"read_research_{slug}"
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await emit({"type": "node_add", "node": {
        "id": read_id, "kind": "tool", "label": f"{slug}.md",
        "status": "running",
        "meta": {"toolType": "read_file", "args": {"path": f"deep/{slug}.md"}},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": agent_id, "target": read_id, "edge_kind": "spawn",
    }})
    await asyncio.sleep(random.uniform(0.3, 0.5))
    await emit({"type": "node_update", "id": read_id, "status": "done"})
    await emit({"type": "edge_add", "edge": {
        "source": read_id, "target": f"file_deep_{slug}", "edge_kind": "read",
    }})

    # web searches for mathematical formulations (launched in parallel)
    searches = FORMALIZE_SEARCH_DATA.get(slug, [
        {"query": f"{slug.replace('-', ' ')} mathematical formulation",
         "results": ["Reference found"]},
    ])

    search_ids = []
    for i, search in enumerate(searches):
        search_id = f"search_form_{slug}_{i}"
        search_ids.append(search_id)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await emit({"type": "node_add", "node": {
            "id": search_id, "kind": "search",
            "label": search["query"][:42] + "...",
            "status": "running",
            "meta": {"query": search["query"], "results": search["results"]},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": agent_id, "target": search_id, "edge_kind": "spawn",
        }})

    await asyncio.sleep(random.uniform(0.8, 1.5))
    for sid in search_ids:
        await emit({"type": "node_update", "id": sid, "status": "done"})

    # write formulation output
    write_id = f"write_form_{slug}"
    await asyncio.sleep(random.uniform(0.5, 1.0))
    await emit({"type": "node_add", "node": {
        "id": write_id, "kind": "tool", "label": f"{slug}.md",
        "status": "running",
        "meta": {"toolType": "write_file", "args": {"path": f"formulations/{slug}.md"}},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": agent_id, "target": write_id, "edge_kind": "spawn",
    }})

    form_path = SAMPLE_DIR / "formulations" / f"{slug}.md"
    content = _read_file_full(form_path)
    file_id = f"file_form_{slug}"

    await asyncio.sleep(random.uniform(0.5, 0.8))
    await emit({"type": "node_update", "id": write_id, "status": "done"})
    await emit({"type": "node_update", "id": agent_id, "status": "done"})
    await emit({"type": "node_add", "node": {
        "id": file_id, "kind": "output", "label": f"{slug}.md",
        "status": "done",
        "meta": {"path": f"formulations/{slug}.md", "content": content, "stage": "formalize"},
    }})
    await emit({"type": "edge_add", "edge": {
        "source": write_id, "target": file_id, "edge_kind": "write",
    }})


# ---------------------------------------------------------------------------
# Mock pipeline
# ---------------------------------------------------------------------------


async def run_mock_pipeline(emit, problem: str) -> None:  # noqa: ARG001
    """Replay sample data as realistic pipeline events with parallel tool calls.

    Key differences from the real pipeline that this mock reproduces:
      - Research: 3 broad web searches in parallel, then 7 Deep Researchers in parallel
      - Formalize: 7 Formalizer sub-agents in parallel
      - Reason: sequential (one spec at a time), reads formulation + env_spec
      - Build: sequential with test-fix loop (write model, write test, run tests)
    """
    import uuid

    run_id = str(uuid.uuid4())
    _kg_state["run_id"] = run_id
    _kg_state["new_count"] = 0
    await emit({"type": "run_start", "run_id": run_id})
    await emit({"type": "agents", "agents": [
        {"name": "memory_agent", "color": "#22d3ee"},
    ]})

    async def tick_memory() -> None:
        """Simulate the memory agent chunk-processing one stage's output."""
        await emit({"type": "agent_status", "agent": "memory_agent", "status": "working"})
        await asyncio.sleep(0.8)
        _kg_state["new_count"] += 1
        await emit({"type": "agent_status", "agent": "memory_agent", "status": "done"})

    all_slugs = _paradigm_slugs_from_dir("deep")
    if not all_slugs:
        await emit({"type": "error", "message": "No sample data found in examples/sample-run/deep/"})
        return

    # ══════════════════════════════════════════════════════════════════════
    #  RESEARCH
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "research", "status": "running"})
    await emit({"type": "node_add", "node": {
        "id": "researcher", "kind": "agent", "label": "Researcher",
        "status": "running", "meta": {},
    }})

    # retrieve_knowledge: check for prior paradigm exploration on this problem
    await _emit_retrieve_knowledge(
        emit,
        node_id="kg_researcher",
        source_id="researcher",
        query="decision-making paradigms for this problem domain",
        namespace="paradigm",
        results_hint=["Prior paradigm survey results"],
    )

    # Phase 1: 3 broad web searches (launched in quick succession)
    broad_ids = []
    for i, search_data in enumerate(BROAD_SEARCHES):
        search_id = f"search_broad_{i}"
        broad_ids.append(search_id)
        await asyncio.sleep(0.3)
        await emit({"type": "node_add", "node": {
            "id": search_id, "kind": "search",
            "label": search_data["query"][:45] + "...",
            "status": "running",
            "meta": {"query": search_data["query"], "results": search_data["results"]},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": "researcher", "target": search_id, "edge_kind": "spawn",
        }})

    # Searches complete
    await asyncio.sleep(1.5)
    for sid in broad_ids:
        await emit({"type": "node_update", "id": sid, "status": "done"})

    # Phase 2: Launch ALL Deep Researchers in parallel
    await asyncio.sleep(0.5)
    tasks = [
        _research_deep(emit, slug, jitter=random.uniform(0.0, 1.5))
        for slug in all_slugs
    ]
    await asyncio.gather(*tasks)

    await emit({"type": "node_update", "id": "researcher", "status": "done"})
    await emit({"type": "stage_change", "stage": "research", "status": "done"})
    asyncio.create_task(tick_memory())

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW_RESEARCH
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "review_research", "status": "running"})

    paradigms_data: list[dict] = []
    for slug in all_slugs:
        md_path = SAMPLE_DIR / "deep" / f"{slug}.md"
        content = _read_file_full(md_path)
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
        approved_slugs = all_slugs
    await emit({"type": "stage_change", "stage": "review_research", "status": "done"})

    # ══════════════════════════════════════════════════════════════════════
    #  FORMALIZE — one full Formalizer agent per paradigm, in parallel
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "formalize", "status": "running"})

    # Each Formalizer is a full agent spawned from its research artifact
    tasks = [
        _formalize_paradigm(emit, slug, jitter=random.uniform(0.0, 1.5))
        for slug in approved_slugs
    ]
    await asyncio.gather(*tasks)

    await emit({"type": "stage_change", "stage": "formalize", "status": "done"})
    asyncio.create_task(tick_memory())

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW_FORMALIZE
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "review_formalize", "status": "running"})

    formalize_data: list[dict] = []
    for slug in approved_slugs:
        md_path = SAMPLE_DIR / "formulations" / f"{slug}.md"
        if not md_path.exists():
            continue
        text = md_path.read_text()
        headers = parse_formulation_headers(text)
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
    await emit({"type": "stage_change", "stage": "review_formalize", "status": "done"})

    # ══════════════════════════════════════════════════════════════════════
    #  GET_ENV_SPEC
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "get_env_spec", "status": "running"})

    env_spec_path = SAMPLE_DIR / "env_spec.json"
    env_spec_content = _read_file_full(env_spec_path)

    response = await wait_for_review("get_env_spec", emit, {
        "message": "Please provide the environment specification (env_spec.json).",
        "default_content": env_spec_content,
    })
    await emit({"type": "stage_change", "stage": "get_env_spec", "status": "done"})

    # ══════════════════════════════════════════════════════════════════════
    #  REASON — sequential, one spec at a time
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "reason", "status": "running"})

    # Reasoner agent — positioned near the first formalize output via layout edge
    await emit({"type": "node_add", "node": {
        "id": "reasoner", "kind": "agent", "label": "Reasoner",
        "status": "running", "meta": {},
    }})
    first_form_id = f"file_form_{approved_slugs[0]}" if approved_slugs else None
    if first_form_id:
        await emit({"type": "edge_add", "edge": {
            "source": first_form_id, "target": "reasoner", "edge_kind": "layout",
        }})

    # retrieve_knowledge: look up validated parameter ranges and env-mapping patterns
    await _emit_retrieve_knowledge(
        emit,
        node_id="kg_reasoner",
        source_id="reasoner",
        query="validated parameter ranges and env_mapping patterns",
        namespace="formulation",
        results_hint=["Past parameter defaults and mapping strategies"],
    )

    all_spec_files: list[Path] = []
    all_reason_file_ids: list[str] = []

    for slug in approved_slugs:
        spec_files = _reasoner_files_for_paradigm(slug)
        all_spec_files.extend(spec_files)

        for sf in spec_files:
            spec_id = sf.stem

            # read_file: formulation
            read_form_id = f"read_form_{spec_id}"
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await emit({"type": "node_add", "node": {
                "id": read_form_id, "kind": "tool", "label": f"{slug}.md",
                "status": "running",
                "meta": {"toolType": "read_file", "args": {"path": f"formulations/{slug}.md"}},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": "reasoner", "target": read_form_id, "edge_kind": "spawn",
            }})
            await asyncio.sleep(random.uniform(0.2, 0.4))
            await emit({"type": "node_update", "id": read_form_id, "status": "done"})
            await emit({"type": "edge_add", "edge": {
                "source": read_form_id, "target": f"file_form_{slug}", "edge_kind": "read",
            }})

            # read_file: env_spec
            read_env_id = f"read_env_{spec_id}"
            await asyncio.sleep(random.uniform(0.15, 0.3))
            await emit({"type": "node_add", "node": {
                "id": read_env_id, "kind": "tool", "label": "env_spec.json",
                "status": "running",
                "meta": {"toolType": "read_file", "args": {"path": "env_spec.json"}},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": "reasoner", "target": read_env_id, "edge_kind": "spawn",
            }})
            await asyncio.sleep(random.uniform(0.15, 0.3))
            await emit({"type": "node_update", "id": read_env_id, "status": "done"})

            # write_file: spec JSON
            write_id = f"write_reason_{spec_id}"
            await asyncio.sleep(random.uniform(0.4, 0.8))
            await emit({"type": "node_add", "node": {
                "id": write_id, "kind": "tool", "label": f"{spec_id}.json",
                "status": "running",
                "meta": {"toolType": "write_file", "args": {"path": f"reasoner/{spec_id}.json"}},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": "reasoner", "target": write_id, "edge_kind": "spawn",
            }})

            content = _read_file_full(sf)
            file_id = f"file_reason_{spec_id}"

            await asyncio.sleep(random.uniform(0.3, 0.6))
            await emit({"type": "node_update", "id": write_id, "status": "done"})
            await emit({"type": "node_add", "node": {
                "id": file_id, "kind": "output", "label": f"{spec_id}.json",
                "status": "done",
                "meta": {"path": f"reasoner/{spec_id}.json", "content": content, "stage": "reason"},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": write_id, "target": file_id, "edge_kind": "write",
            }})
            all_reason_file_ids.append(file_id)

    await emit({"type": "node_update", "id": "reasoner", "status": "done"})
    await emit({"type": "stage_change", "stage": "reason", "status": "done"})
    asyncio.create_task(tick_memory())

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW_REASON
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "review_reason", "status": "running"})

    specs_data: list[dict] = []
    for sf in all_spec_files:
        try:
            data = json.loads(sf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        spec_id = data.get("formulation_id", sf.stem)
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
                "name": data.get("name", sf.stem),
                "description": data.get("description", ""),
                "variables": data.get("variables", []),
                "env_mapping": data.get("env_mapping", {}),
                "full_spec": data,
            })

    response = await wait_for_review("review_reason", emit, {"specs": specs_data})
    await emit({"type": "stage_change", "stage": "review_reason", "status": "done"})

    # ══════════════════════════════════════════════════════════════════════
    #  BUILD — sequential with test-fix loop
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "build", "status": "running"})

    builder_pairs: list[tuple[Path, Path | None]] = []
    for slug in approved_slugs:
        builder_pairs.extend(_builder_files_for_paradigm(slug))

    all_build_file_ids: list[str] = []

    for model_file, test_file in builder_pairs:
        model_id = model_file.stem
        builder_id = f"builder_{model_id}"

        # Find the matching reasoner artifact to spawn FROM
        matching_reason = [
            fid for fid in all_reason_file_ids
            if model_id.split("_model")[0] in fid
        ]
        source_id = (
            matching_reason[0] if matching_reason
            else (all_reason_file_ids[0] if all_reason_file_ids else "reasoner")
        )

        # Builder agent — positioned near its reasoner artifact via layout edge
        await asyncio.sleep(random.uniform(0.4, 0.7))
        await emit({"type": "node_add", "node": {
            "id": builder_id, "kind": "agent", "label": "Builder",
            "status": "running", "meta": {"model": model_id},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": source_id, "target": builder_id, "edge_kind": "layout",
        }})

        # retrieve_knowledge: look up working code patterns for this formulation
        await _emit_retrieve_knowledge(
            emit,
            node_id=f"kg_build_{model_id}",
            source_id=builder_id,
            query=f"Python model patterns for {model_id.split('_model')[0]}",
            namespace="model",
            results_hint=["Working model code from past runs"],
        )

        # read_file: reasoner spec
        read_id = f"read_spec_{model_id}"
        await asyncio.sleep(random.uniform(0.3, 0.5))
        await emit({"type": "node_add", "node": {
            "id": read_id, "kind": "tool",
            "label": f"{model_id.split('_model')[0]}.json",
            "status": "running",
            "meta": {"toolType": "read_file", "args": {"path": f"reasoner/{model_id}.json"}},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": builder_id, "target": read_id, "edge_kind": "spawn",
        }})
        await asyncio.sleep(random.uniform(0.2, 0.4))
        await emit({"type": "node_update", "id": read_id, "status": "done"})
        await emit({"type": "edge_add", "edge": {
            "source": read_id, "target": source_id, "edge_kind": "read",
        }})

        # write_file: model code
        write_model_id = f"write_model_{model_id}"
        await asyncio.sleep(random.uniform(0.8, 1.5))
        await emit({"type": "node_add", "node": {
            "id": write_model_id, "kind": "tool", "label": model_file.name,
            "status": "running",
            "meta": {"toolType": "write_file", "args": {"path": f"builder/{model_file.name}"}},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": builder_id, "target": write_model_id, "edge_kind": "spawn",
        }})

        code = _read_file_full(model_file)
        file_id = f"file_model_{model_id}"

        await asyncio.sleep(random.uniform(0.5, 0.8))
        await emit({"type": "node_update", "id": write_model_id, "status": "done"})
        await emit({"type": "node_add", "node": {
            "id": file_id, "kind": "output", "label": model_file.name,
            "status": "done",
            "meta": {"path": f"builder/{model_file.name}", "content": code, "stage": "build"},
        }})
        await emit({"type": "edge_add", "edge": {
            "source": write_model_id, "target": file_id, "edge_kind": "write",
        }})
        all_build_file_ids.append(file_id)

        # Test-fix loop
        if test_file:
            # write_file: test file
            write_test_id = f"write_test_{model_id}"
            await asyncio.sleep(random.uniform(0.4, 0.7))
            await emit({"type": "node_add", "node": {
                "id": write_test_id, "kind": "tool", "label": test_file.name,
                "status": "running",
                "meta": {"toolType": "write_file", "args": {"path": f"builder/{test_file.name}"}},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": builder_id, "target": write_test_id, "edge_kind": "spawn",
            }})

            test_code = _read_file_full(test_file)
            test_artifact_id = f"file_test_{model_id}"

            await asyncio.sleep(random.uniform(0.4, 0.6))
            await emit({"type": "node_update", "id": write_test_id, "status": "done"})
            await emit({"type": "node_add", "node": {
                "id": test_artifact_id, "kind": "file", "label": test_file.name,
                "status": "done",
                "meta": {"path": f"builder/{test_file.name}", "content": test_code},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": write_test_id, "target": test_artifact_id, "edge_kind": "write",
            }})

            # run_tests tool
            run_test_id = f"run_tests_{model_id}"
            await asyncio.sleep(random.uniform(0.3, 0.5))
            await emit({"type": "node_add", "node": {
                "id": run_test_id, "kind": "tool",
                "label": f"pytest {test_file.name}",
                "status": "running",
                "meta": {"toolType": "run_tests", "args": {"path": f"builder/{test_file.name}"}},
            }})
            await emit({"type": "edge_add", "edge": {
                "source": builder_id, "target": run_test_id, "edge_kind": "spawn",
            }})
            await emit({"type": "edge_add", "edge": {
                "source": run_test_id, "target": test_artifact_id, "edge_kind": "read",
            }})

            # Tests pass
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await emit({"type": "node_update", "id": run_test_id, "status": "done"})

        await emit({"type": "node_update", "id": builder_id, "status": "done"})

    await emit({"type": "stage_change", "stage": "build", "status": "done"})
    asyncio.create_task(tick_memory())

    # ══════════════════════════════════════════════════════════════════════
    #  REVIEW_BUILD
    # ══════════════════════════════════════════════════════════════════════
    await emit({"type": "stage_change", "stage": "review_build", "status": "running"})

    models_data: list[dict] = []

    # Check for validation reports (invalid builds)
    builder_dir = SAMPLE_DIR / "builder"
    if builder_dir.is_dir():
        for vfile in sorted(builder_dir.glob("*_validation.json")):
            try:
                data = json.loads(vfile.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("status") == "invalid":
                models_data.append({
                    "slug": data.get("formulation_id", vfile.stem),
                    "paradigm": data.get("paradigm", "unknown"),
                    "status": "invalid",
                    "problems": data.get("problems", []),
                    "code": "",
                    "test_results": "",
                    "passed": False,
                })

    for model_file, test_file in builder_pairs:
        code = _read_file_full(model_file)
        test_results = _read_file_full(test_file) if test_file else ""
        lower = (code + test_results).lower()
        has_issues = any(w in lower for w in ("error", "fail", "traceback", "exception"))
        models_data.append({
            "slug": model_file.stem,
            "code": code,
            "test_results": test_results,
            "passed": not has_issues,
        })

    response = await wait_for_review("review_build", emit, {"models": models_data})
    await emit({"type": "stage_change", "stage": "review_build", "status": "done"})
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
                _current_problem["value"] = problem
                manager.pipeline_task = asyncio.create_task(
                    _run_with_error_handling(manager.emit, problem)
                )

            elif msg_type == "review_response":
                await manager.handle_review_response(data)

            elif msg_type == "router_prompt":
                logger.info("Router prompt received: %s", data.get("message", ""))

            elif msg_type == "cancel":
                if manager.pipeline_task and not manager.pipeline_task.done():
                    manager.pipeline_task.cancel()
                    await manager.cancel_and_mark()
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
# Replay REST endpoints (mock-only, in-memory)
# ---------------------------------------------------------------------------


@app.get("/api/runs")
async def list_runs() -> list[dict]:
    """Return terminal runs newest-first."""
    terminal = [
        r for r in _run_records.values()
        if r["status"] in ("done", "cancelled", "failed")
    ]
    terminal.sort(key=lambda r: r["started_at"], reverse=True)
    return terminal


@app.get("/api/runs/{run_id}/events")
async def get_run_events(run_id: str):
    """Stream the recorded event stream for a run (NDJSON)."""
    rec = _run_records.get(run_id)
    if rec and rec["status"] == "running":
        raise HTTPException(status_code=409, detail="Run still in progress")
    events = _run_events.get(run_id)
    if not events:
        raise HTTPException(status_code=404, detail="Event log not found")
    body = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)
    return PlainTextResponse(body, media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
