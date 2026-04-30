"""Tests for shared.settings module."""

from shared.settings import Settings, load_settings

_SETTINGS_ENV_VARS = (
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "POSTGRES_DSN",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "QDRANT_URL",
    "VOYAGE_API_KEY",
    "ZEROENTROPY_API_KEY",
)


def _strip_env(monkeypatch) -> None:
    """Remove all settings-related env vars so dataclass defaults take effect."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch):
    """Settings() (no env interference) returns dataclass defaults."""
    _strip_env(monkeypatch)
    s = Settings()
    assert s.MINIO_ENDPOINT == "localhost:9000"
    assert s.MINIO_ACCESS_KEY == "minioadmin"
    assert s.MINIO_SECRET_KEY == "minioadmin"
    assert s.MINIO_BUCKET == "labtfg"
    assert "asyncpg" in s.POSTGRES_DSN
    assert "labtfg" in s.POSTGRES_DSN
    assert s.NEO4J_URI == "bolt://localhost:7687"
    assert s.NEO4J_USER == "neo4j"
    assert s.NEO4J_PASSWORD == "labtfg-neo4j"
    assert s.QDRANT_URL == "http://localhost:6333"
    assert s.VOYAGE_API_KEY == ""
    assert s.ZEROENTROPY_API_KEY == ""


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
        raise AssertionError("Should have raised FrozenInstanceError")
    except AttributeError:
        pass


# ---------------------------------------------------------------------------
# ENABLE_KNOWLEDGE_WRITE — permissive bool parsing
# ---------------------------------------------------------------------------


import pytest  # noqa: E402  — kept beside the section it parametrizes


def test_enable_knowledge_write_default_false():
    s = load_settings()
    assert s.ENABLE_KNOWLEDGE_WRITE is False


@pytest.mark.parametrize(
    "raw", ["1", "true", "TRUE", "True", "yes", "YES", "on", " on "]
)
def test_enable_knowledge_write_truthy_strings(monkeypatch, raw):
    monkeypatch.setenv("ENABLE_KNOWLEDGE_WRITE", raw)
    s = load_settings()
    assert s.ENABLE_KNOWLEDGE_WRITE is True


@pytest.mark.parametrize(
    "raw", ["0", "false", "FALSE", "no", "off", "", "xyz", "None", "2"]
)
def test_enable_knowledge_write_falsy_strings(monkeypatch, raw):
    monkeypatch.setenv("ENABLE_KNOWLEDGE_WRITE", raw)
    s = load_settings()
    assert s.ENABLE_KNOWLEDGE_WRITE is False


def test_enable_knowledge_write_absent_env(monkeypatch):
    monkeypatch.delenv("ENABLE_KNOWLEDGE_WRITE", raising=False)
    s = load_settings()
    assert s.ENABLE_KNOWLEDGE_WRITE is False
