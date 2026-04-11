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

import shared
from shared.models import Run, Model, Artifact
from sqlalchemy import select


SAMPLE_RUN_DIR = Path(__file__).resolve().parent.parent / "phase1-pablo" / "examples" / "sample-run"
SAMPLE_RUN_MARKER = "sample-run-migration"


async def main():
    await shared.init()
    try:
        # Check if already migrated
        async with shared.db.get_session() as session:
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
        async with shared.db.get_session() as session:
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
            await shared.storage.put_text(key, report_path.read_text())
            await _register_artifact(key, "report", run_id, report_path.stat().st_size)
            uploaded += 1

        # deep/*.md
        deep_dir = SAMPLE_RUN_DIR / "deep"
        if deep_dir.exists():
            for f in sorted(deep_dir.glob("*.md")):
                key = f"research/{run_id}/deep/{f.name}"
                await shared.storage.put_text(key, f.read_text())
                await _register_artifact(key, "deep_report", run_id, f.stat().st_size)
                uploaded += 1

        # formulations/*.md
        form_dir = SAMPLE_RUN_DIR / "formulations"
        if form_dir.exists():
            for f in sorted(form_dir.glob("*.md")):
                key = f"research/{run_id}/formulations/{f.name}"
                await shared.storage.put_text(key, f.read_text())
                await _register_artifact(key, "formulation", run_id, f.stat().st_size)
                uploaded += 1

        # reasoner/*.json
        reasoner_dir = SAMPLE_RUN_DIR / "reasoner"
        if reasoner_dir.exists():
            for f in sorted(reasoner_dir.glob("*.json")):
                key = f"models/{run_id}/reasoner/{f.name}"
                await shared.storage.put_text(key, f.read_text())
                await _register_artifact(key, "reasoner_spec", run_id, f.stat().st_size)
                uploaded += 1

        # builder/*_model.py and test_*.py
        builder_dir = SAMPLE_RUN_DIR / "builder"
        if builder_dir.exists():
            for f in sorted(builder_dir.glob("*_model.py")):
                fid = f.stem.removesuffix("_model")
                model_key = f"models/{run_id}/builder/{f.name}"
                await shared.storage.put(model_key, f.read_bytes(), "text/x-python")
                await _register_artifact(model_key, "model", run_id, f.stat().st_size, "text/x-python")

                # Try to extract class name and description
                content = f.read_text()
                class_match = re.search(r"class\s+(\w+)", content)
                class_name = class_match.group(1) if class_match else fid
                paradigm = fid.split("_", 1)[0] if "_" in fid else None
                # Get module docstring
                doc_match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
                description = doc_match.group(1).strip() if doc_match else None

                test_key = None
                test_file = builder_dir / f"test_{fid}.py"
                if test_file.exists():
                    test_key = f"models/{run_id}/builder/test_{fid}.py"
                    await shared.storage.put(test_key, test_file.read_bytes(), "text/x-python")
                    await _register_artifact(test_key, "test", run_id, test_file.stat().st_size, "text/x-python")
                    uploaded += 1

                async with shared.db.get_session() as session:
                    db_model = Model(
                        formulation_id=fid,
                        class_name=class_name,
                        paradigm=paradigm,
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
            await shared.storage.put_text(key, env_spec.read_text())
            await _register_artifact(key, "report", run_id, env_spec.stat().st_size, "application/json")
            uploaded += 1

        # pipeline_state.json
        ps = SAMPLE_RUN_DIR / "pipeline_state.json"
        if ps.exists():
            key = f"research/{run_id}/pipeline_state.json"
            await shared.storage.put_text(key, ps.read_text())
            uploaded += 1

        print(f"Done! Uploaded {uploaded} files to MinIO, registered models in Postgres.")
    finally:
        await shared.shutdown()


async def _register_artifact(s3_key, artifact_type, run_id, size_bytes, content_type="text/plain"):
    async with shared.db.get_session() as session:
        artifact = Artifact(
            id=uuid.uuid4(),
            s3_key=s3_key,
            artifact_type=artifact_type,
            run_id=uuid.UUID(run_id),
            size_bytes=size_bytes,
            content_type=content_type,
        )
        session.add(artifact)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
