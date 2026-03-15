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


@pytest.mark.asyncio
async def test_read_file_returns_content(tmp_path):
    (tmp_path / "hello.txt").write_text("hello world")
    fn = create_read_file(tmp_path)
    result = await fn({"path": "hello.txt"})
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_missing_file(tmp_path):
    fn = create_read_file(tmp_path)
    with pytest.raises(ValueError, match="File not found"):
        await fn({"path": "nonexistent.txt"})


@pytest.mark.asyncio
async def test_read_file_path_traversal(tmp_path):
    fn = create_read_file(tmp_path)
    with pytest.raises(ValueError, match="escapes base directory"):
        await fn({"path": "../../etc/passwd"})


@pytest.mark.asyncio
async def test_read_file_missing_param(tmp_path):
    fn = create_read_file(tmp_path)
    with pytest.raises(ValueError, match="path"):
        await fn({})


@pytest.mark.asyncio
async def test_write_file_creates_file(tmp_path):
    fn = create_write_file(tmp_path)
    result = await fn({"path": "out.txt", "content": "data"})
    assert "4 chars" in result
    assert (tmp_path / "out.txt").read_text() == "data"


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path):
    fn = create_write_file(tmp_path)
    result = await fn({"path": "sub/dir/out.txt", "content": "nested"})
    assert "6 chars" in result
    assert (tmp_path / "sub" / "dir" / "out.txt").read_text() == "nested"


@pytest.mark.asyncio
async def test_write_file_path_traversal(tmp_path):
    fn = create_write_file(tmp_path)
    with pytest.raises(ValueError, match="escapes base directory"):
        await fn({"path": "../../evil.txt", "content": "bad"})


@pytest.mark.asyncio
async def test_write_file_missing_path_param(tmp_path):
    fn = create_write_file(tmp_path)
    with pytest.raises(ValueError, match="path"):
        await fn({"content": "data"})


@pytest.mark.asyncio
async def test_write_file_missing_content_param(tmp_path):
    fn = create_write_file(tmp_path)
    with pytest.raises(ValueError, match="content"):
        await fn({"path": "out.txt"})
