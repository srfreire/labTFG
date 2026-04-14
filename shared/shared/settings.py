"""Infrastructure settings — read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "labtfg"
    POSTGRES_DSN: str = "postgresql+asyncpg://labtfg:labtfg@localhost:5432/labtfg"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "labtfg-neo4j"


def load_settings() -> Settings:
    """Load settings from env vars, falling back to dev defaults."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    fields = {f.name for f in Settings.__dataclass_fields__.values()}
    overrides = {}
    for name in fields:
        val = os.environ.get(name)
        if val is not None:
            overrides[name] = val
    return Settings(**overrides)
