"""Shared artifact registration helper."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from shared.models import Artifact

if TYPE_CHECKING:
    from shared.database import DatabaseService


async def register_artifact(
    s3_key: str,
    artifact_type: str,
    size_bytes: int,
    content_type: str = "text/plain",
    run_id: str | None = None,
    experiment_id: str | None = None,
    *,
    db: DatabaseService,
) -> None:
    """Register an artifact in the DB. Accepts string UUIDs for convenience."""
    async with db.get_session() as session:
        session.add(
            Artifact(
                id=uuid.uuid4(),
                s3_key=s3_key,
                artifact_type=artifact_type,
                run_id=uuid.UUID(run_id) if run_id else None,
                experiment_id=uuid.UUID(experiment_id) if experiment_id else None,
                size_bytes=size_bytes,
                content_type=content_type,
            )
        )
        await session.commit()
