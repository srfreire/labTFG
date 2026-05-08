"""Async helper for the ``simulation_observations`` table.

Phase 2 observations are write-once, fixed-confidence rows: no supersession,
no corroboration, no decay. The helper below is intentionally a single
``create_simulation_observation`` whose signature mirrors the typed columns
on :class:`shared.models.SimulationObservation` so callers stop stuffing
cross-phase identifiers into JSONB.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import SimulationObservation

_DEFAULT_CONFIDENCE = 0.80
_DEFAULT_NAMESPACE = "simulation"
_DEFAULT_SOURCE_STAGE = "tracker"


async def create_simulation_observation(
    session: AsyncSession,
    *,
    id: uuid.UUID | None = None,
    content: str,
    memory_type: str,
    importance: float,
    confidence: float = _DEFAULT_CONFIDENCE,
    namespace: str = _DEFAULT_NAMESPACE,
    source_stage: str = _DEFAULT_SOURCE_STAGE,
    phase2_experiment_id: str | None = None,
    model_class_name: str | None = None,
    paradigm: str | None = None,
    formulation: str | None = None,
    phase1_run_id: uuid.UUID | None = None,
    environment: str | None = None,
    steps: int | None = None,
    seed: int | None = None,
    agent_id: str | None = None,
    episode_type: str | None = None,
    step: int | None = None,
    metadata_: dict[str, Any] | None = None,
) -> SimulationObservation:
    """Create and persist a new ``SimulationObservation`` row.

    All cross-phase identifiers (paradigm, formulation, phase1_run_id, etc.)
    live in their own typed columns; ``metadata_`` carries only what doesn't
    fit in the schema (model_id, models_compared, step ranges).
    """
    observation = SimulationObservation(
        id=id if id is not None else uuid.uuid4(),
        content=content,
        memory_type=memory_type,
        importance=importance,
        confidence=confidence,
        namespace=namespace,
        source_stage=source_stage,
        phase2_experiment_id=phase2_experiment_id,
        model_class_name=model_class_name,
        paradigm=paradigm,
        formulation=formulation,
        phase1_run_id=phase1_run_id,
        environment=environment,
        steps=steps,
        seed=seed,
        agent_id=agent_id,
        episode_type=episode_type,
        step=step,
        metadata_=metadata_,
    )
    session.add(observation)
    await session.flush()
    return observation
