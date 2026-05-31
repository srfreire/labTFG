"""Shared artifact registration helper."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert

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
    """Register or update an artifact in the DB.

    S3 keys are unique, and agent loops may rewrite the same artifact while
    iterating. Treat registration as idempotent metadata upsert instead of
    failing the tool call on duplicate keys.
    """
    run_uuid = uuid.UUID(run_id) if run_id else None
    experiment_uuid = uuid.UUID(experiment_id) if experiment_id else None
    async with db.get_session() as session:
        stmt = insert(Artifact).values(
            id=uuid.uuid4(),
            s3_key=s3_key,
            artifact_type=artifact_type,
            run_id=run_uuid,
            experiment_id=experiment_uuid,
            size_bytes=size_bytes,
            content_type=content_type,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Artifact.s3_key],
            set_={
                "artifact_type": artifact_type,
                "run_id": run_uuid,
                "experiment_id": experiment_uuid,
                "size_bytes": size_bytes,
                "content_type": content_type,
            },
        )
        await session.execute(stmt)
        await session.commit()
