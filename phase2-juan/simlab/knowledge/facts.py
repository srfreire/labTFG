"""Pure helpers that convert Tracker JSON into FactSpec lists.

No I/O, no async, no LLM calls. The writer (P1-003) calls these helpers to
obtain the list of facts to embed and persist.

See docs/specs/sim-memory/phase-1-core-writer.md (R4) for the authoritative
rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from simlab.knowledge.writer import ModelInfo, SimulationContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactSpec:
    """A single candidate memory: natural-language text + scoring + metadata."""

    text: str
    importance: float
    memory_type: str  # "semantic" | "episodic"
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


_FILTERED_EPISODE_TYPES: frozenset[str] = frozenset(
    {"foraging_success", "exploration", "exploitation"}
)

_EPISODE_IMPORTANCE: dict[str, float] = {
    "starvation": 9,
    "state_change": 8,
    "foraging_failure": 7,
}
_DEFAULT_EPISODE_IMPORTANCE: float = 6

_SUMMARY_IMPORTANCE: float = 5
_TRAJECTORY_IMPORTANCE: float = 6


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def _base_metadata(context: SimulationContext, model_info: ModelInfo) -> dict[str, Any]:
    """Metadata fields that every fact emitted for this (context, model) shares."""
    return {
        "phase2_experiment_id": context.phase2_experiment_id,
        "model_id": model_info.model_id,
        "model_class_name": model_info.class_name,
        "paradigm": model_info.paradigm,
        "formulation": model_info.formulation,
        "phase1_run_id": model_info.phase1_run_id,
        "environment": context.environment,
        "steps": context.steps,
        "seed": context.seed,
    }


def _distinct_models(context: SimulationContext) -> list[ModelInfo]:
    """Unique ModelInfo values referenced by agents, preserving first-seen order."""
    seen_ids: set[str] = set()
    out: list[ModelInfo] = []
    for info in context.agent_to_model.values():
        if info.model_id in seen_ids:
            continue
        seen_ids.add(info.model_id)
        out.append(info)
    return out


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def build_summary_fact(tracker: dict, context: SimulationContext) -> FactSpec | None:
    """Produce one summary fact (or None if there is no non-empty summary)."""
    summary_text = str(tracker.get("summary", "")).strip()
    if not summary_text:
        return None

    models = _distinct_models(context)
    if not models:
        logger.warning(
            "build_summary_fact: no agent_to_model entries — skipping summary"
        )
        return None

    representative = models[0]
    metadata = _base_metadata(context, representative)

    if len(models) > 1:
        metadata["models_compared"] = [m.class_name for m in models]

    text = (
        f"Model {representative.class_name} "
        f"({representative.paradigm}/{representative.formulation}) "
        f'in {context.environment}: "{summary_text}"'
    )

    return FactSpec(
        text=text,
        importance=_SUMMARY_IMPORTANCE,
        memory_type="semantic",
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Trajectories
# ---------------------------------------------------------------------------


def _format_top_actions(actions: dict[str, int], n: int = 3) -> str:
    if not actions:
        return "none"
    top = sorted(actions.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return ", ".join(f"{name}({count})" for name, count in top)


def build_trajectory_facts(tracker: dict, context: SimulationContext) -> list[FactSpec]:
    """One fact per agent in `trajectories`, skipping agents without ModelInfo."""
    trajectories = tracker.get("trajectories", {}) or {}
    facts: list[FactSpec] = []

    for agent_id, traj in trajectories.items():
        model_info = context.agent_to_model.get(agent_id)
        if model_info is None:
            logger.warning(
                "build_trajectory_facts: no ModelInfo for agent_id=%r — skipping",
                agent_id,
            )
            continue

        steps_survived = traj.get("steps_survived", 0)
        resources = traj.get("resources_consumed", 0)
        actions = traj.get("actions", {}) or {}
        top_actions = _format_top_actions(actions)

        text = (
            f"Agent {agent_id} using {model_info.class_name} "
            f"in {context.environment} survived {steps_survived} steps, "
            f"consumed {resources} resources; top actions: {top_actions}"
        )

        metadata = _base_metadata(context, model_info)
        metadata["agent_id"] = agent_id

        facts.append(
            FactSpec(
                text=text,
                importance=_TRAJECTORY_IMPORTANCE,
                memory_type="semantic",
                metadata=metadata,
            )
        )

    return facts


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


def _episode_step_fragment(episode: dict) -> tuple[str, dict[str, Any]]:
    """Return ("step=N" | "steps=N..M", metadata_extras)."""
    if "step" in episode and episode["step"] is not None:
        step = episode["step"]
        return f"step={step}", {"step": step}
    if (
        "steps" in episode
        and isinstance(episode["steps"], list)
        and len(episode["steps"]) == 2
    ):
        start, end = episode["steps"]
        return f"steps={start}..{end}", {"step_start": start, "step_end": end}
    return "step=?", {}


def build_episode_facts(
    tracker: dict, context: SimulationContext
) -> tuple[list[FactSpec], int]:
    """One fact per relevant episode; returns (facts, filtered_count)."""
    episodes = tracker.get("episodes", []) or []
    facts: list[FactSpec] = []
    filtered = 0

    for episode in episodes:
        ep_type = str(episode.get("type", "")).strip()

        if ep_type in _FILTERED_EPISODE_TYPES:
            filtered += 1
            continue

        agent_id = episode.get("agent")
        model_info = context.agent_to_model.get(agent_id) if agent_id else None
        if model_info is None:
            logger.warning(
                "build_episode_facts: no ModelInfo for agent_id=%r (episode type=%r) — skipping",
                agent_id,
                ep_type,
            )
            continue

        step_fragment, step_meta = _episode_step_fragment(episode)
        description = str(episode.get("description", "")).strip()
        importance = _EPISODE_IMPORTANCE.get(ep_type, _DEFAULT_EPISODE_IMPORTANCE)

        text = (
            f"Model {model_info.class_name} "
            f"({model_info.paradigm}/{model_info.formulation}) "
            f"in {context.environment}: {description} "
            f"[type={ep_type}, agent={agent_id}, {step_fragment}]"
        )

        metadata = _base_metadata(context, model_info)
        metadata["agent_id"] = agent_id
        metadata["episode_type"] = ep_type
        metadata.update(step_meta)

        facts.append(
            FactSpec(
                text=text,
                importance=importance,
                memory_type="episodic",
                metadata=metadata,
            )
        )

    return facts, filtered


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_all_facts(
    tracker: dict, context: SimulationContext
) -> tuple[list[FactSpec], int]:
    """Build the full list of facts: [summary?, *trajectories, *episodes].

    Returns `(facts, episodes_filtered_count)`. Never raises.
    """
    facts: list[FactSpec] = []

    summary = build_summary_fact(tracker, context)
    if summary is not None:
        facts.append(summary)

    facts.extend(build_trajectory_facts(tracker, context))

    episodes, filtered = build_episode_facts(tracker, context)
    facts.extend(episodes)

    return facts, filtered
