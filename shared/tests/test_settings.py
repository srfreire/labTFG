"""Tests for shared.settings module."""
import os

from shared.settings import Settings, load_settings


def test_defaults():
    """load_settings returns dev defaults when no env vars are set."""
    s = load_settings()
    assert s.MINIO_ENDPOINT == "localhost:9000"
    assert s.MINIO_ACCESS_KEY == "minioadmin"
    assert s.MINIO_SECRET_KEY == "minioadmin"
    assert s.MINIO_BUCKET == "labtfg"
    assert "asyncpg" in s.POSTGRES_DSN
    assert "labtfg" in s.POSTGRES_DSN
    assert s.NEO4J_URI == "bolt://localhost:7687"
    assert s.NEO4J_USER == "neo4j"
    assert s.NEO4J_PASSWORD == "labtfg"
    assert s.QDRANT_URL == "http://localhost:6333"
    assert s.VOYAGE_API_KEY == ""


def test_env_override(monkeypatch):
    """load_settings picks up env var overrides."""
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+asyncpg://u:p@db:5432/test")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    s = load_settings()
    assert s.MINIO_ENDPOINT == "minio:9000"
    assert s.POSTGRES_DSN == "postgresql+asyncpg://u:p@db:5432/test"
    assert s.NEO4J_URI == "bolt://neo4j:7687"
    assert s.QDRANT_URL == "http://qdrant:6333"
    # Non-overridden fields keep defaults
    assert s.MINIO_BUCKET == "labtfg"


def test_frozen():
    """Settings dataclass is immutable."""
    s = load_settings()
    try:
        s.MINIO_BUCKET = "other"  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
