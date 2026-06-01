"""Shared test guardrails.

Integration tests in this package create/drop all ORM tables. Route them to a
dedicated sibling test database by default so a local demo database survives a
full pytest run.
"""

from __future__ import annotations

import os

from shared.settings import derive_test_postgres_dsn

if "LABTFG_TEST_POSTGRES_DSN" in os.environ:
    os.environ["POSTGRES_DSN"] = os.environ["LABTFG_TEST_POSTGRES_DSN"]
elif os.environ.get("LABTFG_ALLOW_DESTRUCTIVE_TEST_DB") != "1":
    os.environ["POSTGRES_DSN"] = derive_test_postgres_dsn(
        os.environ.get(
            "POSTGRES_DSN",
            "postgresql+asyncpg://labtfg:labtfg@localhost:5432/labtfg",
        )
    )
