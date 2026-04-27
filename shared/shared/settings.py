"""Infrastructure settings — read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields

_BOOL_TRUE = frozenset({"1", "true", "yes", "on"})


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
    QDRANT_URL: str = "http://localhost:6333"
    VOYAGE_API_KEY: str = ""
    ZEROENTROPY_API_KEY: str = ""
    ENABLE_KNOWLEDGE_WRITE: bool = False
    ENABLE_KNOWLEDGE_READ: bool = False
    NLSQL_MAX_S3_FETCH: int = 3
    NLSQL_MODEL: str = "anthropic/claude-haiku-4-5"


def _parse_bool(raw: str) -> bool:
    """Permissive bool parsing — accepts '1', 'true', 'yes', 'on' (case-insensitive)."""
    return raw.strip().lower() in _BOOL_TRUE


def load_settings() -> Settings:
    """Load settings from env vars, falling back to dev defaults."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    overrides: dict[str, object] = {}
    for f in fields(Settings):
        val = os.environ.get(f.name)
        if val is None:
            continue
        if f.type is bool or f.type == "bool":
            overrides[f.name] = _parse_bool(val)
        elif f.type is int or f.type == "int":
            overrides[f.name] = int(val)
        else:
            overrides[f.name] = val
    return Settings(**overrides)
