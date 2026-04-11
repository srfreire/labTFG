"""Shared artifact registration helper."""
from __future__ import annotations

import uuid

import shared
from shared.models import Artifact


async def register_artifact(
    s3_key: str,
    artifact_type: str,
    size_bytes: int,
    content_type: str = "text/plain",
    run_id: str | None = None,
    experiment_id: str | None = None,
) -> None:
    """Register an artifact in the DB. Accepts string UUIDs for convenience."""
    async with shared.db.get_session() as session:
        session.add(Artifact(
            id=uuid.uuid4(),
            s3_key=s3_key,
            artifact_type=artifact_type,
            run_id=uuid.UUID(run_id) if run_id else None,
            experiment_id=uuid.UUID(experiment_id) if experiment_id else None,
            size_bytes=size_bytes,
            content_type=content_type,
        ))
        await session.commit()
