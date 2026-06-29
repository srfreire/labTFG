"""Artifact bundle export for eval runs.

Bundles are meant for external review: they collect generated S3 artifacts,
database state tied to the eval run, a KG snapshot when available, and the
PDF corpus used by PDF-only evals.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from decisionlab.eval.models import PipelineRunResult

if TYPE_CHECKING:
    from decisionlab.eval.corpus import EvalPaperCorpus
    from decisionlab.eval.suite import SuiteResult
    from shared.services import Services

logger = logging.getLogger(__name__)


async def export_suite_artifacts(
    result: SuiteResult,
    *,
    services: Services,
    out_dir: Path,
    corpus: EvalPaperCorpus | None = None,
) -> Path:
    """Export every run artifact in a suite into ``out_dir``."""

    runs = [tr.run for tr in result.topic_results]
    await _export_common(
        runs,
        services=services,
        out_dir=out_dir,
        corpus=corpus,
        manifest_extra={
            "suite": result.suite.name,
            "topics": [tr.topic for tr in result.topic_results],
            "created_at": datetime.now().isoformat(),
        },
    )
    return out_dir


async def export_pipeline_artifacts(
    result: PipelineRunResult,
    *,
    services: Services,
    out_dir: Path,
    corpus: EvalPaperCorpus | None = None,
) -> Path:
    """Export artifacts for one ``run_pipeline`` result."""

    await _export_common(
        [result],
        services=services,
        out_dir=out_dir,
        corpus=corpus,
        manifest_extra={
            "suite": None,
            "topics": [result.topic],
            "created_at": datetime.now().isoformat(),
        },
    )
    return out_dir


async def _export_common(
    runs: Iterable[PipelineRunResult],
    *,
    services: Services,
    out_dir: Path,
    corpus: EvalPaperCorpus | None,
    manifest_extra: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_ids = [r.run_id for r in runs if _is_uuid(r.run_id)]
    manifest: dict[str, Any] = {
        **manifest_extra,
        "run_ids": run_ids,
        "storage_prefixes": [],
        "sections": {},
        "errors": [],
    }

    if corpus is not None:
        try:
            corpus_manifest = corpus.export_to(out_dir / "corpus")
            manifest["sections"]["corpus"] = str(corpus_manifest)
        except Exception as exc:
            _record_error(manifest, "corpus", exc)

    try:
        storage_files = await _export_storage(
            run_ids, services=services, out_dir=out_dir
        )
        manifest["sections"]["storage"] = {
            "file_count": len(storage_files),
            "root": str(out_dir / "storage"),
        }
        manifest["storage_prefixes"] = [
            prefix
            for rid in run_ids
            for prefix in (f"research/{rid}/", f"models/{rid}/")
        ]
    except Exception as exc:
        _record_error(manifest, "storage", exc)

    try:
        db_dir = await _export_database(run_ids, services=services, out_dir=out_dir)
        manifest["sections"]["database"] = str(db_dir)
    except Exception as exc:
        _record_error(manifest, "database", exc)

    try:
        kg_path = await _export_kg_snapshot(services=services, out_dir=out_dir)
        if kg_path is not None:
            manifest["sections"]["kg_snapshot"] = str(kg_path)
    except Exception as exc:
        _record_error(manifest, "kg_snapshot", exc)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )


async def _export_storage(
    run_ids: list[str],
    *,
    services: Services,
    out_dir: Path,
) -> list[Path]:
    if services.storage is None:
        return []
    written: list[Path] = []
    for run_id in run_ids:
        for prefix in (f"research/{run_id}/", f"models/{run_id}/"):
            keys = await services.storage.list(prefix)
            for key in keys:
                data = await services.storage.get(key)
                dest = out_dir / "storage" / Path(*key.split("/"))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                written.append(dest)
    return written


async def _export_database(
    run_ids: list[str],
    *,
    services: Services,
    out_dir: Path,
) -> Path:
    db_dir = out_dir / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    if services.db is None or not run_ids:
        _write_json(db_dir / "runs.json", [])
        _write_json(db_dir / "pipeline_memories.json", [])
        return db_dir

    from shared.models import (
        Artifact,
        Model,
        NodeRunObservation,
        PipelineMemory,
        Run,
        SimulationObservation,
    )

    uuids = [uuid.UUID(rid) for rid in run_ids]
    async with services.db.get_session() as session:
        rows = {
            "runs.json": (
                await session.execute(select(Run).where(Run.id.in_(uuids)))
            ).scalars(),
            "models.json": (
                await session.execute(select(Model).where(Model.run_id.in_(uuids)))
            ).scalars(),
            "artifacts.json": (
                await session.execute(
                    select(Artifact).where(Artifact.run_id.in_(uuids))
                )
            ).scalars(),
            "node_run_observations.json": (
                await session.execute(
                    select(NodeRunObservation).where(
                        NodeRunObservation.run_id.in_(uuids)
                    )
                )
            ).scalars(),
            "pipeline_memories.json": (
                await session.execute(
                    select(PipelineMemory).where(PipelineMemory.run_id.in_(uuids))
                )
            ).scalars(),
            "simulation_observations.json": (
                await session.execute(
                    select(SimulationObservation).where(
                        SimulationObservation.phase1_run_id.in_(uuids)
                    )
                )
            ).scalars(),
        }

        for filename, scalars in rows.items():
            _write_json(
                db_dir / filename, [_model_to_dict(row) for row in scalars.all()]
            )

    return db_dir


async def _export_kg_snapshot(*, services: Services, out_dir: Path) -> Path | None:
    if services.kg is None:
        return None
    from decisionlab.eval import kgadmin

    path = out_dir / f"kg_snapshot_{date.today().isoformat()}.json"
    await kgadmin.snapshot_to_file(path, services)
    return path


def _model_to_dict(obj) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attr in obj.__mapper__.column_attrs:
        column = attr.columns[0]
        out[column.name] = _jsonable(getattr(obj, attr.key))
    return out


def _jsonable(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _record_error(manifest: dict[str, Any], section: str, exc: Exception) -> None:
    logger.warning("Eval artifact export failed for %s: %s", section, exc)
    manifest.setdefault("errors", []).append(
        {"section": section, "error": str(exc), "type": type(exc).__name__}
    )
