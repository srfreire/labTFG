"""Skip denis tests when phase2-juan environment is unavailable.

The denis integration tests depend on `simlab.environment` from phase2-juan,
which is intentionally out-of-scope for this project's primary CI pipeline.
Collect-time skip prevents ImportError from breaking the test session.
"""

from __future__ import annotations

import importlib

import pytest

collect_ignore: list[str] = []

_REQUIRED_SYMBOLS = (
    "ActionRule",
    "Agent",
    "ConsumeEffect",
    "Environment",
    "ModelAdapter",
    "MoveEffect",
    "NoopEffect",
    "Position",
    "ResourceRule",
    "homeostatic_perception_mapper",
)


def _has_phase2_environment() -> bool:
    try:
        env = importlib.import_module("simlab.environment")
    except Exception:
        return False
    return all(hasattr(env, name) for name in _REQUIRED_SYMBOLS)


if not _has_phase2_environment():
    collect_ignore.append("test_environment_integration.py")


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Mark remaining denis tests as integration so they can be opted out."""
    for item in items:
        if "/denis/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
