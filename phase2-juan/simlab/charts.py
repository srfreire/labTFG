"""
Chart generation for simulation analysis.

Provides tools for the Analyst agent to create visualizations:
  - Line charts (time series: reward, energy, state variables)
  - Bar charts (action distributions)
  - Heatmaps (Q-tables)

Charts are generated as:
  1. JSON specs → sent to frontend for interactive recharts rendering
  2. matplotlib PNGs → included in LaTeX PDF reports
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING

from simlab.environment import Event
from simlab.loop import Registry
from simlab.utils import get_q_values

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

# ---------------------------------------------------------------------------
# Data extraction from events
# ---------------------------------------------------------------------------


def _get_agents(events: list[Event], agent_ids: list[str] | None) -> list[str]:
    all_agents = sorted(set(e.agent_id for e in events))
    if agent_ids:
        return [a for a in agent_ids if a in all_agents]
    return all_agents


def _filter_step_range(
    events: list[Event], step_range: list[int] | None
) -> list[Event]:
    if not step_range or len(step_range) != 2:
        return events
    start, end = step_range
    return [e for e in events if start <= e.step <= end]


def _extract_reward_over_time(
    events: list[Event], agents: list[str], **_
) -> list[dict]:
    series = []
    for agent_id in agents:
        data = [
            {"x": e.step, "y": e.outcome.get("reward", 0)}
            for e in events
            if e.agent_id == agent_id
        ]
        series.append({"name": agent_id, "data": data})
    return series


def _extract_cumulative_reward(
    events: list[Event], agents: list[str], **_
) -> list[dict]:
    series = []
    for agent_id in agents:
        cumulative = 0
        data = []
        for e in events:
            if e.agent_id != agent_id:
                continue
            cumulative += e.outcome.get("reward", 0)
            data.append({"x": e.step, "y": round(cumulative, 2)})
        series.append({"name": agent_id, "data": data})
    return series


def _extract_action_distribution(
    events: list[Event], agents: list[str], **_
) -> list[dict]:
    series = []
    for agent_id in agents:
        counts: dict[str, int] = defaultdict(int)
        for e in events:
            if e.agent_id == agent_id:
                counts[e.action.name] += 1
        data = [{"x": action, "y": count} for action, count in sorted(counts.items())]
        series.append({"name": agent_id, "data": data})
    return series


def _extract_state_evolution(
    events: list[Event], agents: list[str], state_key: str = "energy", **_
) -> list[dict]:
    series = []
    for agent_id in agents:
        data = []
        for e in events:
            if e.agent_id != agent_id:
                continue
            model_state = e.outcome.get("model_state", {})
            value = model_state.get(state_key)
            if isinstance(value, (int, float)):
                data.append({"x": e.step, "y": round(float(value), 4)})
        series.append({"name": agent_id, "data": data})
    return series


def _extract_q_table(events: list[Event], agents: list[str], **_) -> list[dict]:
    series = []
    for agent_id in agents:
        agent_events = [e for e in events if e.agent_id == agent_id]
        if not agent_events:
            continue
        model_state = agent_events[-1].outcome.get("model_state", {})
        q_values = get_q_values(model_state)
        if q_values:
            data = []
            for k, v in q_values.items():
                if isinstance(v, (int, float)):
                    data.append({"x": str(k), "y": round(float(v), 4)})
                elif isinstance(v, dict):
                    # Nested dict: (state, action) -> value
                    for sub_k, sub_v in v.items():
                        if isinstance(sub_v, (int, float)):
                            data.append(
                                {"x": f"{k}:{sub_k}", "y": round(float(sub_v), 4)}
                            )
            series.append({"name": agent_id, "data": data})
    return series


def _extract_action_scores_evolution(
    events: list[Event], agents: list[str], **_
) -> list[dict]:
    """For models with Q-tables: plot Q-value per action over time from pre_state."""
    series = []
    for agent_id in agents:
        action_data: dict[str, list[dict]] = {}
        for e in events:
            if e.agent_id != agent_id:
                continue
            q = get_q_values(e.pre_state)
            if not isinstance(q, dict):
                continue
            for action_name, val in q.items():
                if isinstance(val, (int, float)):
                    action_data.setdefault(str(action_name), []).append(
                        {"x": e.step, "y": round(float(val), 4)}
                    )
        for action_name in sorted(action_data):
            series.append(
                {"name": f"{agent_id}:{action_name}", "data": action_data[action_name]}
            )
    return series


def _extract_pre_post_state_delta(
    events: list[Event], agents: list[str], state_key: str = "energy", **_
) -> list[dict]:
    """Plot the delta (post - pre) for any scalar state key over time."""
    series = []
    for agent_id in agents:
        data = []
        for e in events:
            if e.agent_id != agent_id:
                continue
            pre_val = e.pre_state.get(state_key)
            post_val = e.outcome.get("model_state", {}).get(state_key)
            if isinstance(pre_val, (int, float)) and isinstance(post_val, (int, float)):
                delta = float(post_val) - float(pre_val)
                data.append({"x": e.step, "y": round(delta, 4)})
        if data:
            series.append({"name": agent_id, "data": data})
    return series


_EXTRACTORS = {
    "reward_over_time": _extract_reward_over_time,
    "cumulative_reward": _extract_cumulative_reward,
    "action_distribution": _extract_action_distribution,
    "state_evolution": _extract_state_evolution,
    "q_table": _extract_q_table,
    "action_scores_evolution": _extract_action_scores_evolution,
    "pre_post_state_delta": _extract_pre_post_state_delta,
}

_AXIS_LABELS = {
    "reward_over_time": ("Paso", "Recompensa"),
    "cumulative_reward": ("Paso", "Recompensa acumulada"),
    "action_distribution": ("Acción", "Cantidad"),
    "state_evolution": None,  # dynamic — uses state_key
    "q_table": ("Estado-Acción", "Q-valor"),
    "action_scores_evolution": ("Paso", "Q-valor"),
    "pre_post_state_delta": None,  # dynamic — uses state_key
}


# ---------------------------------------------------------------------------
# Matplotlib chart generation (for PDF reports)
# ---------------------------------------------------------------------------

# Professional style matching a clean academic look
_MPL_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]


def _generate_chart_image(spec: dict) -> bytes | None:
    """Generate a matplotlib PNG and return the raw bytes (or None on failure)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    from io import BytesIO

    fig, ax = plt.subplots(figsize=(7, 4))
    chart_type = spec["type"]
    series = spec["series"]

    if chart_type == "line":
        for i, s in enumerate(series):
            xs = [d["x"] for d in s["data"]]
            ys = [d["y"] for d in s["data"]]
            ax.plot(
                xs,
                ys,
                label=s["name"],
                color=_MPL_COLORS[i % len(_MPL_COLORS)],
                linewidth=1.4,
            )
        if len(series) > 1:
            ax.legend(fontsize=9, framealpha=0.9)

    elif chart_type == "bar":
        if not series:
            plt.close(fig)
            return None
        import numpy as np

        categories = sorted(set(d["x"] for s in series for d in s["data"]))
        x = np.arange(len(categories))
        width = 0.8 / max(len(series), 1)
        for i, s in enumerate(series):
            values = {d["x"]: d["y"] for d in s["data"]}
            heights = [values.get(c, 0) for c in categories]
            ax.bar(
                x + i * width - 0.4 + width / 2,
                heights,
                width,
                label=s["name"],
                color=_MPL_COLORS[i % len(_MPL_COLORS)],
            )
        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=30, ha="right", fontsize=8)
        if len(series) > 1:
            ax.legend(fontsize=9)

    elif chart_type == "heatmap":
        for i, s in enumerate(series):
            labels = [d["x"] for d in s["data"]]
            vals = [d["y"] for d in s["data"]]
            ax.barh(
                labels,
                vals,
                label=s["name"],
                color=_MPL_COLORS[i % len(_MPL_COLORS)],
                alpha=0.8,
            )
        if len(series) > 1:
            ax.legend(fontsize=9)

    ax.set_title(spec.get("title", ""), fontsize=11, fontweight="bold")
    ax.set_xlabel(spec.get("x_label", ""), fontsize=9)
    ax.set_ylabel(spec.get("y_label", ""), fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

# Must match SIM_AGENT_COLORS in api.py (can't import due to circular dep)
CHART_COLORS = ["#4ade80", "#fbbf24", "#a78bfa", "#f472b6", "#38bdf8", "#fb923c"]

CREATE_CHART_TOOL = {
    "name": "create_chart",
    "description": (
        "Generate a chart visualization from simulation data. "
        "Automatically extracts data from events. "
        "Use line charts for time series, bar charts for distributions, heatmaps for Q-tables."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["line", "bar", "heatmap"],
                "description": "line = time series, bar = distributions, heatmap = Q-tables",
            },
            "metric": {
                "type": "string",
                "enum": [
                    "reward_over_time",
                    "cumulative_reward",
                    "action_distribution",
                    "state_evolution",
                    "q_table",
                    "action_scores_evolution",
                    "pre_post_state_delta",
                ],
                "description": (
                    "reward_over_time: per-step reward; "
                    "cumulative_reward: accumulated reward; "
                    "action_distribution: action counts; "
                    "state_evolution: internal state variable (set state_key); "
                    "q_table: Q-values from last step; "
                    "action_scores_evolution: Q-value per action over time (shows learning); "
                    "pre_post_state_delta: change in a state variable per step (set state_key)"
                ),
            },
            "title": {"type": "string", "description": "Chart title in Spanish"},
            "agent_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Agents to include (omit for all)",
            },
            "state_key": {
                "type": "string",
                "description": "For state_evolution: key from model state (e.g. 'energy', 'drive', 'error'). "
                "Call list_state_keys first to see what's available.",
            },
            "step_range": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[start, end] step filter (optional)",
            },
        },
        "required": ["chart_type", "metric", "title"],
    },
}

LIST_STATE_KEYS_TOOL = {
    "name": "list_state_keys",
    "description": (
        "List available internal state variable keys from the decision models. "
        "Call this before create_chart with metric='state_evolution' to know what variables "
        "can be plotted (e.g. 'energy', 'drive', 'q_values', 'error')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


# ---------------------------------------------------------------------------
# Tool builder
# ---------------------------------------------------------------------------


def build_chart_tools(
    events: list[Event],
    experiment_id: str,
    charts_accumulator: list[dict],
    *,
    storage: StorageService,
    db: DatabaseService,
) -> tuple[list[dict], Registry]:
    """Build chart generation tools for the Analyst.

    Args:
        events: simulation events to extract data from
        experiment_id: experiment UUID — charts are uploaded to S3 under this prefix
        charts_accumulator: mutable list — chart specs are appended here
        storage: object store
        db: database (for artifact registration)
    """
    counter = [len(charts_accumulator)]  # continue numbering

    async def create_chart(params: dict) -> str:
        from shared.artifacts import register_artifact

        chart_type = params["chart_type"]
        metric = params["metric"]
        title = params["title"]
        agent_ids = params.get("agent_ids")
        state_key = params.get("state_key", "energy")
        step_range = params.get("step_range")

        filtered = _filter_step_range(events, step_range)
        agents = _get_agents(filtered, agent_ids)
        if not agents:
            return json.dumps({"error": "No agents found matching the specified IDs"})

        extractor = _EXTRACTORS.get(metric)
        if not extractor:
            return json.dumps({"error": f"Unknown metric: {metric}"})

        series = extractor(filtered, agents, state_key=state_key)

        if not any(s["data"] for s in series):
            # Helpful error: list available state keys if state_evolution failed
            if metric == "state_evolution":
                available = set()
                for e in filtered:
                    ms = e.outcome.get("model_state", {})
                    available.update(
                        k for k, v in ms.items() if isinstance(v, (int, float))
                    )
                return json.dumps(
                    {
                        "error": f"No data for state_key '{state_key}'",
                        "available_keys": sorted(available),
                    }
                )
            return json.dumps({"error": f"No data found for metric '{metric}'"})

        # Assign frontend colors
        for i, s in enumerate(series):
            s["color"] = CHART_COLORS[i % len(CHART_COLORS)]

        counter[0] += 1
        chart_id = f"chart_{counter[0]}"

        labels = _AXIS_LABELS.get(metric, ("", ""))
        if metric == "state_evolution":
            labels = ("Paso", state_key.replace("_", " ").title())
        elif metric == "pre_post_state_delta":
            labels = ("Paso", f"Δ {state_key.replace('_', ' ').title()}")

        spec: dict = {
            "id": chart_id,
            "type": chart_type,
            "title": title,
            "x_label": labels[0],
            "y_label": labels[1],
            "series": series,
        }

        # Generate matplotlib PNG and upload to S3
        png_bytes = _generate_chart_image(spec)
        if png_bytes:
            s3_key = f"experiments/{experiment_id}/charts/{chart_id}.png"
            await storage.put(s3_key, png_bytes, "image/png")
            spec["image_path"] = s3_key

            await register_artifact(
                s3_key,
                "chart",
                len(png_bytes),
                experiment_id=experiment_id,
                content_type="image/png",
                db=db,
            )

        charts_accumulator.append(spec)

        return json.dumps(
            {
                "success": True,
                "chart_id": chart_id,
                "title": title,
                "data_points": sum(len(s["data"]) for s in series),
                "agents_included": [s["name"] for s in series],
            }
        )

    async def list_state_keys(params: dict) -> str:
        # Single pass to find last event per agent
        last_by_agent: dict[str, Event] = {}
        for e in events:
            last_by_agent[e.agent_id] = e
        keys_by_agent: dict[str, dict[str, list[str]]] = {}
        for agent_id, last_event in sorted(last_by_agent.items()):
            state = last_event.outcome.get("model_state", {})
            scalar = [k for k, v in state.items() if isinstance(v, (int, float))]
            complex_ = [k for k, v in state.items() if isinstance(v, (dict, list))]
            keys_by_agent[agent_id] = {
                "scalar_keys": sorted(scalar),
                "complex_keys": sorted(complex_),
            }
        return json.dumps(keys_by_agent)

    schemas = [CREATE_CHART_TOOL, LIST_STATE_KEYS_TOOL]
    registry: Registry = {
        "create_chart": create_chart,
        "list_state_keys": list_state_keys,
    }
    return schemas, registry
