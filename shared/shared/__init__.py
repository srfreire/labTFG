"""Shared infrastructure — explicit dependency container.

Construct a ``Services`` via ``shared.services.init_services`` at every
entry point and thread it through consumers. There are no module-level
globals here; ``shared.init()`` and ``shared.shutdown()`` no longer exist.
"""

from __future__ import annotations
