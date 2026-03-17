"""
Dynamic loader for Phase 1 Builder decision models.

Phase 1 generates *_model.py files that contain decision model classes.
This module discovers those files, checks they implement the DecisionModel interface,
and provides a way to instantiate them with isolated RNG seeds.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import random
import sys
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
    path: Path              # path to the *_model.py file
    model_class: type       # the actual class


def _has_decision_model_interface(cls: type) -> bool:
    """Check if a class implements decide(), update(), and get_state()."""
    return (
        callable(getattr(cls, "decide", None))
        and callable(getattr(cls, "update", None))
        and callable(getattr(cls, "get_state", None))
    )


# ---------------------------------------------------------------------------
# Discovery — scan a directory for model files
# ---------------------------------------------------------------------------

def discover_models(builder_dir: Path) -> dict[str, ModelInfo]:
    """Scan builder_dir for *_model.py files and return discovered models.

    Each file is loaded as a module, and the first class implementing
    the DecisionModel interface is registered.
    """
    models: dict[str, ModelInfo] = {}

    for path in sorted(builder_dir.glob("*_model.py")):
        formulation_id = path.stem.removesuffix("_model")
        module_name = f"_builder_{path.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)

            # Find the first class that implements the DecisionModel interface
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if obj.__module__ == module_name and _has_decision_model_interface(obj):
                    models[formulation_id] = ModelInfo(
                        formulation_id=formulation_id,
                        class_name=name,
                        description=(mod.__doc__ or "").strip(),
                        path=path,
                        model_class=obj,
                    )
                    break
        except Exception:
            logger.warning("Failed to load model from %s", path, exc_info=True)

    return models


# ---------------------------------------------------------------------------
# Instantiation — create a model instance with an isolated RNG
# ---------------------------------------------------------------------------

def load_model(model_info: ModelInfo, *, seed: int | None = None, **kwargs) -> object:
    """Instantiate a discovered model.

    If seed is provided, the model file is loaded into a fresh private module
    and its `random` attribute is replaced with a newly-seeded Random instance.
    This ensures two models with the same seed produce identical decisions
    even when called interleaved for reproducibility.
    """
    if seed is not None:
        # Load into an isolated module so the RNG is not shared
        unique_name = f"_builder_{model_info.path.stem}_{id(object())}"
        spec = importlib.util.spec_from_file_location(unique_name, model_info.path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot reload {model_info.path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = mod
        spec.loader.exec_module(mod)

        # Replace the module's RNG with a seeded one
        if hasattr(mod, "random"):
            mod.random = random.Random(seed)

        # Find the class in the fresh module
        model_class: type | None = None
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if obj.__module__ == unique_name and _has_decision_model_interface(obj):
                model_class = obj
                break
        del sys.modules[unique_name]

        if model_class is None:
            raise ValueError(f"No decision model class found in {model_info.path}")
    else:
        model_class = model_info.model_class

    try:
        return model_class(**kwargs)
    except TypeError as e:
        raise ValueError(f"Failed to instantiate {model_info.class_name}: {e}") from e
