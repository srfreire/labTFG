"""Shared test configuration — loads .env for integration tests."""

import os
from pathlib import Path

from dotenv import load_dotenv

from shared.settings import derive_test_postgres_dsn

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

if "LABTFG_TEST_POSTGRES_DSN" in os.environ:
    os.environ["POSTGRES_DSN"] = os.environ["LABTFG_TEST_POSTGRES_DSN"]
elif os.environ.get("LABTFG_ALLOW_DESTRUCTIVE_TEST_DB") != "1":
    os.environ["POSTGRES_DSN"] = derive_test_postgres_dsn(
        os.environ.get(
            "POSTGRES_DSN",
            "postgresql+asyncpg://labtfg:labtfg@localhost:5432/labtfg",
        )
    )
