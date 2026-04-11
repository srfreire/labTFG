"""
Dynamic loader for Phase 1 Builder decision models.

Phase 1 generates *_model.py files that contain decision model classes.
This module discovers models from Postgres and loads them on-demand from S3.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model metadata
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    """Metadata about a discovered decision model."""
    formulation_id: str     # e.g. "homeostatic-regulation_drive_reduction_rl"
    class_name: str         # e.g. "DriveReductionRLModel"
    description: str        # from the module docstring
    s3_model_key: str       # S3 key for the model source file
    run_id: str | None = None  # UUID of the Phase 1 run that produced this model


def _has_decision_model_interface(cls: type) -> bool:
    """Check if a class implements decide(), update(), and get_state()."""
    return (
        callable(getattr(cls, "decide", None))
        and callable(getattr(cls, "update", None))
        and callable(getattr(cls, "get_state", None))
    )


# ---------------------------------------------------------------------------
# Discovery -- query Postgres for registered models
# ---------------------------------------------------------------------------

async def discover_models() -> dict[str, ModelInfo]:
    """Discover models from the Postgres models table."""
    import shared
    from shared.models import Model as DBModel
    from sqlalchemy import select

    models: dict[str, ModelInfo] = {}
    async with shared.db.get_session() as session:
        result = await session.execute(select(DBModel))
        rows = result.scalars().all()
        for row in rows:
            models[row.formulation_id] = ModelInfo(
                formulation_id=row.formulation_id,
                class_name=row.class_name,
                description=row.description or "",
                s3_model_key=row.s3_model_key,
                run_id=str(row.run_id) if row.run_id else None,
            )
    return models


# ---------------------------------------------------------------------------
# Instantiation -- download from S3, load via importlib
# ---------------------------------------------------------------------------

async def load_model(model_info: ModelInfo, *, seed: int | None = None, **kwargs) -> object:
    """Download a model from S3 and instantiate it.

    The model source is written to a temp directory and loaded as a module.
    If seed is provided, the module's `random` attribute is replaced with
    a newly-seeded Random instance for reproducibility.
    """
    import shared

    model_bytes = await shared.storage.get(model_info.s3_model_key)
    tmp_dir = tempfile.mkdtemp(prefix="model_")
    tmp_path = Path(tmp_dir) / f"{model_info.formulation_id}_model.py"
    tmp_path.write_bytes(model_bytes)

    module_name = f"_builder_{model_info.formulation_id}_{id(object())}"
    spec = importlib.util.spec_from_file_location(module_name, tmp_path)
    if spec is None or spec.loader is None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise ValueError(f"Cannot load module from {model_info.s3_model_key}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    if seed is not None and hasattr(mod, "random"):
        mod.random = random.Random(seed)

    model_class: type | None = None
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == module_name and _has_decision_model_interface(obj):
            model_class = obj
            break

    del sys.modules[module_name]

    # Don't clean up tmp_dir yet -- the class object references the file
    # Store for later cleanup
    if not hasattr(load_model, '_tmp_dirs'):
        load_model._tmp_dirs = []
    load_model._tmp_dirs.append(tmp_dir)

    if model_class is None:
        raise ValueError(f"No decision model class found in {model_info.s3_model_key}")

    try:
        return model_class(**kwargs)
    except TypeError as e:
        raise ValueError(f"Failed to instantiate {model_info.formulation_id}: {e}") from e


def cleanup_temp_models() -> None:
    """Clean up temp dirs created by load_model."""
    for d in getattr(load_model, '_tmp_dirs', []):
        shutil.rmtree(d, ignore_errors=True)
    load_model._tmp_dirs = []
