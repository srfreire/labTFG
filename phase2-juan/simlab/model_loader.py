"""Dynamic loader for Phase 1 Builder decision models."""
from __future__ import annotations

import importlib.util
import inspect
import logging
import random
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    formulation_id: str
    class_name: str
    description: str
    path: Path
    model_class: type


def _has_decision_model_interface(cls: type) -> bool:
    return (
        callable(getattr(cls, "decide", None))
        and callable(getattr(cls, "update", None))
        and callable(getattr(cls, "get_state", None))
    )


def discover_models(builder_dir: Path) -> dict[str, ModelInfo]:
    """Scan builder_dir for *_model.py files and return discovered models."""
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


def load_model(model_info: ModelInfo, *, seed: int | None = None, **kwargs) -> object:
    """Instantiate a discovered model with optional parameter overrides.

    If *seed* is provided, the model file is loaded into a **fresh** private
    module and its ``random`` attribute is replaced with a newly-seeded
    ``random.Random`` instance.  This ensures two models created with the same
    seed produce identical decision sequences even when called interleaved.
    """
    if seed is not None:
        # Load the file into a unique, throwaway module so the instance gets
        # its own isolated RNG that won't be disturbed by any other caller.
        unique_name = f"_builder_{model_info.path.stem}_{id(object())}"
        spec = importlib.util.spec_from_file_location(unique_name, model_info.path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot reload {model_info.path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = mod
        spec.loader.exec_module(mod)
        if hasattr(mod, "random"):
            mod.random = random.Random(seed)
        # Find the class in the freshly-loaded module.
        model_class: type | None = None
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if obj.__module__ == unique_name and _has_decision_model_interface(obj):
                model_class = obj
                break
        if model_class is None:
            raise ValueError(f"No decision model class found in {model_info.path}")
    else:
        model_class = model_info.model_class

    try:
        return model_class(**kwargs)
    except TypeError as e:
        raise ValueError(f"Failed to instantiate {model_info.class_name}: {e}") from e
