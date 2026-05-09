"""Migrate sample-run data from filesystem to MinIO + Postgres.

Usage:
    python scripts/migrate_sample_run.py

Reads env vars for MinIO/Postgres endpoints. Idempotent — safe to run multiple times.
"""

import asyncio
import re
import sys
import uuid
from pathlib import Path

# Add repo root to path for shared package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from sqlalchemy import select

from shared.artifacts import register_artifact as _register_artifact
from shared.models import Model, Run
from shared.services import init_services, shutdown_services

SAMPLE_RUN_DIR = (
    Path(__file__).resolve().parent.parent / "phase1-pablo" / "examples" / "sample-run"
)
SAMPLE_RUN_MARKER = "sample-run-migration"


async def main():
    services = await init_services()
    try:
        # Check if already migrated
        async with services.db.get_session() as session:
            result = await session.execute(
                select(Run).where(Run.problem_description == SAMPLE_RUN_MARKER)
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"Sample run already migrated (run_id={existing.id}). Skipping.")
                return

        if not SAMPLE_RUN_DIR.exists():
            print(f"Sample run directory not found: {SAMPLE_RUN_DIR}")
            return

        run_id = str(uuid.uuid4())
        print(f"Migrating sample-run with run_id={run_id}")

        # Create Run record
        async with services.db.get_session() as session:
            db_run = Run(
                id=uuid.UUID(run_id),
                problem_description=SAMPLE_RUN_MARKER,
                status="done",
                s3_prefix=f"research/{run_id}",
            )
            session.add(db_run)
            await session.commit()

        # Upload all files
        uploaded = 0

        # report.md
        report_path = SAMPLE_RUN_DIR / "report.md"
        if report_path.exists():
            key = f"research/{run_id}/report.md"
            await services.storage.put_text(key, report_path.read_text())
            await _register_artifact(
                key,
                "report",
                report_path.stat().st_size,
                run_id=run_id,
                db=services.db,
            )
            uploaded += 1

        # deep/*.md
        deep_dir = SAMPLE_RUN_DIR / "deep"
        if deep_dir.exists():
            for f in sorted(deep_dir.glob("*.md")):
                key = f"research/{run_id}/deep/{f.name}"
                await services.storage.put_text(key, f.read_text())
                await _register_artifact(
                    key,
                    "deep_report",
                    f.stat().st_size,
                    run_id=run_id,
                    db=services.db,
                )
                uploaded += 1

        # formulations/*.md
        form_dir = SAMPLE_RUN_DIR / "formulations"
        if form_dir.exists():
            for f in sorted(form_dir.glob("*.md")):
                key = f"research/{run_id}/formulations/{f.name}"
                await services.storage.put_text(key, f.read_text())
                await _register_artifact(
                    key,
                    "formulation",
                    f.stat().st_size,
                    run_id=run_id,
                    db=services.db,
                )
                uploaded += 1

        # reasoner/*.json
        reasoner_dir = SAMPLE_RUN_DIR / "reasoner"
        if reasoner_dir.exists():
            for f in sorted(reasoner_dir.glob("*.json")):
                key = f"models/{run_id}/reasoner/{f.name}"
                await services.storage.put_text(key, f.read_text())
                await _register_artifact(
                    key,
                    "reasoner_spec",
                    f.stat().st_size,
                    run_id=run_id,
                    db=services.db,
                )
                uploaded += 1

        # builder/*_model.py and test_*.py
        builder_dir = SAMPLE_RUN_DIR / "builder"
        if builder_dir.exists():
            for f in sorted(builder_dir.glob("*_model.py")):
                fid = f.stem.removesuffix("_model")
                content = f.read_text()
                content_bytes = content.encode()
                model_key = f"models/{run_id}/builder/{f.name}"
                await services.storage.put(model_key, content_bytes, "text/x-python")
                await _register_artifact(
                    model_key,
                    "model",
                    len(content_bytes),
                    run_id=run_id,
                    content_type="text/x-python",
                    db=services.db,
                )
                class_match = re.search(r"class\s+(\w+)", content)
                class_name = class_match.group(1) if class_match else fid
                paradigm = fid.split("_", 1)[0] if "_" in fid else fid
                formulation = fid.split("_", 1)[1] if "_" in fid else fid
                # Get module docstring
                doc_match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
                description = doc_match.group(1).strip() if doc_match else None

                test_key = None
                test_file = builder_dir / f"test_{fid}.py"
                if test_file.exists():
                    test_key = f"models/{run_id}/builder/test_{fid}.py"
                    await services.storage.put(
                        test_key, test_file.read_bytes(), "text/x-python"
                    )
                    await _register_artifact(
                        test_key,
                        "test",
                        test_file.stat().st_size,
                        run_id=run_id,
                        content_type="text/x-python",
                        db=services.db,
                    )
                    uploaded += 1

                async with services.db.get_session() as session:
                    db_model = Model(
                        class_name=class_name,
                        paradigm=paradigm,
                        formulation=formulation,
                        description=description,
                        run_id=uuid.UUID(run_id),
                        s3_model_key=model_key,
                        s3_test_key=test_key,
                    )
                    session.add(db_model)
                    await session.commit()
                uploaded += 1

        # env_spec.json
        env_spec = SAMPLE_RUN_DIR / "env_spec.json"
        if env_spec.exists():
            key = f"research/{run_id}/env_spec.json"
            await services.storage.put_text(key, env_spec.read_text())
            await _register_artifact(
                key,
                "report",
                env_spec.stat().st_size,
                run_id=run_id,
                content_type="application/json",
                db=services.db,
            )
            uploaded += 1

        # pipeline_state.json
        ps = SAMPLE_RUN_DIR / "pipeline_state.json"
        if ps.exists():
            key = f"research/{run_id}/pipeline_state.json"
            await services.storage.put_text(key, ps.read_text())
            uploaded += 1

        print(
            f"Done! Uploaded {uploaded} files to MinIO, registered models in Postgres."
        )
    finally:
        await shutdown_services(services)


if __name__ == "__main__":
    asyncio.run(main())
