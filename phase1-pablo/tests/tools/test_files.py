from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.tools.files import (
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    create_read_file,
    create_write_file,
)


def test_read_file_schema_has_required_fields():
    assert READ_FILE_SCHEMA["name"] == "read_file"
    assert "path" in READ_FILE_SCHEMA["input_schema"]["properties"]
    assert READ_FILE_SCHEMA["input_schema"]["required"] == ["path"]


def test_write_file_schema_has_required_fields():
    assert WRITE_FILE_SCHEMA["name"] == "write_file"
    assert "path" in WRITE_FILE_SCHEMA["input_schema"]["properties"]
    assert "content" in WRITE_FILE_SCHEMA["input_schema"]["properties"]
    assert WRITE_FILE_SCHEMA["input_schema"]["required"] == ["path", "content"]


@pytest.fixture
def s3_store():
    """Shared mock S3 store dict for tests."""
    return {}


@pytest.fixture
def mock_storage(s3_store):
    """Build a mock StorageService backed by an in-memory dict."""

    async def fake_get_text(key):
        if key not in s3_store:
            raise FileNotFoundError(f"File not found: {key}")
        return s3_store[key]

    async def fake_put_text(key, content):
        s3_store[key] = content

    mock = MagicMock()
    mock.get_text = AsyncMock(side_effect=fake_get_text)
    mock.put_text = AsyncMock(side_effect=fake_put_text)
    return mock


@pytest.fixture
def mock_db():
    """Build a mock DatabaseService for write_file (artifact registration)."""
    mock = MagicMock()
    mock.execute = AsyncMock()
    mock.fetchrow = AsyncMock()
    mock.fetch = AsyncMock(return_value=[])
    return mock


@pytest.mark.asyncio
async def test_read_file_returns_content(s3_store, mock_storage):
    s3_store["my-prefix/hello.txt"] = "hello world"
    fn = create_read_file("my-prefix", storage=mock_storage)
    result = await fn({"path": "hello.txt"})
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_missing_file(mock_storage):
    fn = create_read_file("my-prefix", storage=mock_storage)
    with pytest.raises(FileNotFoundError):
        await fn({"path": "nonexistent.txt"})


@pytest.mark.asyncio
async def test_read_file_uses_fallback_prefix_after_primary_miss(
    s3_store, mock_storage
):
    s3_store["fallback-prefix/reasoner/model.json"] = '{"ok": true}'
    fn = create_read_file(
        "primary-prefix",
        storage=mock_storage,
        fallback_prefixes=("fallback-prefix",),
    )

    result = await fn({"path": "reasoner/model.json"})

    assert result == '{"ok": true}'
    assert mock_storage.get_text.await_args_list[0].args == (
        "primary-prefix/reasoner/model.json",
    )
    assert mock_storage.get_text.await_args_list[1].args == (
        "fallback-prefix/reasoner/model.json",
    )


@pytest.mark.asyncio
async def test_read_file_path_traversal(mock_storage):
    fn = create_read_file("my-prefix", storage=mock_storage)
    with pytest.raises(ValueError, match="Invalid path"):
        await fn({"path": "../../etc/passwd"})


@pytest.mark.asyncio
async def test_read_file_missing_param(mock_storage):
    fn = create_read_file("my-prefix", storage=mock_storage)
    with pytest.raises(ValueError, match="path"):
        await fn({})


@pytest.mark.asyncio
async def test_write_file_creates_file(s3_store, mock_storage, mock_db):
    fn = create_write_file("my-prefix", storage=mock_storage, db=mock_db)
    result = await fn({"path": "out.txt", "content": "data"})
    assert "4 chars" in result
    assert s3_store["my-prefix/out.txt"] == "data"


@pytest.mark.asyncio
async def test_write_file_creates_nested_path(s3_store, mock_storage, mock_db):
    fn = create_write_file("my-prefix", storage=mock_storage, db=mock_db)
    result = await fn({"path": "sub/dir/out.txt", "content": "nested"})
    assert "6 chars" in result
    assert s3_store["my-prefix/sub/dir/out.txt"] == "nested"


@pytest.mark.asyncio
async def test_write_file_path_traversal(mock_storage, mock_db):
    fn = create_write_file("my-prefix", storage=mock_storage, db=mock_db)
    with pytest.raises(ValueError, match="Invalid path"):
        await fn({"path": "../../evil.txt", "content": "bad"})


@pytest.mark.asyncio
async def test_write_file_missing_path_param(mock_storage, mock_db):
    fn = create_write_file("my-prefix", storage=mock_storage, db=mock_db)
    with pytest.raises(ValueError, match="path"):
        await fn({"content": "data"})


@pytest.mark.asyncio
async def test_write_file_missing_content_param(mock_storage, mock_db):
    fn = create_write_file("my-prefix", storage=mock_storage, db=mock_db)
    with pytest.raises(ValueError, match="content"):
        await fn({"path": "out.txt"})
