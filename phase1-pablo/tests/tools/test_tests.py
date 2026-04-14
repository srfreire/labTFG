import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from decisionlab.tools.tests import RUN_TESTS_SCHEMA, create_run_tests


def test_run_tests_schema_has_required_fields():
    assert RUN_TESTS_SCHEMA["name"] == "run_tests"
    assert "path" in RUN_TESTS_SCHEMA["input_schema"]["properties"]
    assert RUN_TESTS_SCHEMA["input_schema"]["required"] == ["path"]


def _make_s3_mock(files: dict[str, str]):
    """Build a mock storage object from a dict of {relative_path: content}."""
    prefix = "models/run-1"
    store: dict[str, bytes] = {}
    keys: list[str] = []
    for rel, content in files.items():
        key = f"{prefix}/builder/{rel}"
        store[key] = content.encode()
        keys.append(key)

    mock = MagicMock()

    async def fake_list(pfx):
        return [k for k in keys if k.startswith(pfx)]

    async def fake_get(key):
        if key not in store:
            raise FileNotFoundError(key)
        return store[key]

    mock.list = AsyncMock(side_effect=fake_list)
    mock.get = AsyncMock(side_effect=fake_get)
    return mock


@pytest.mark.asyncio
async def test_run_tests_passing_file(tmp_path):
    test_content = "def test_ok():\n    assert 1 + 1 == 2\n"
    mock = _make_s3_mock({"test_passing.py": test_content})

    with patch("shared.storage", mock):
        fn = create_run_tests(s3_prefix="models/run-1", project_root=tmp_path)
        result = await fn({"path": "test_passing.py"})
    assert "passed" in result


@pytest.mark.asyncio
async def test_run_tests_failing_file(tmp_path):
    test_content = "def test_bad():\n    assert 1 == 2\n"
    mock = _make_s3_mock({"test_failing.py": test_content})

    with patch("shared.storage", mock):
        fn = create_run_tests(s3_prefix="models/run-1", project_root=tmp_path)
        result = await fn({"path": "test_failing.py"})
    assert "FAILED" in result or "AssertionError" in result


@pytest.mark.asyncio
async def test_run_tests_timeout(tmp_path, monkeypatch):
    import asyncio

    async def fake_wait_for(coro, **_kw):
        # Cancel the coroutine to avoid "was never awaited" warning
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    test_content = "def test_ok():\n    pass\n"
    mock = _make_s3_mock({"test_any.py": test_content})

    with patch("shared.storage", mock):
        fn = create_run_tests(s3_prefix="models/run-1", project_root=tmp_path)
        result = await fn({"path": "test_any.py"})
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_tests_path_traversal(tmp_path):
    fn = create_run_tests(s3_prefix="models/run-1", project_root=tmp_path)
    with pytest.raises(ValueError, match="Invalid path"):
        await fn({"path": "../../evil_test.py"})


@pytest.mark.asyncio
async def test_run_tests_missing_param(tmp_path):
    fn = create_run_tests(s3_prefix="models/run-1", project_root=tmp_path)
    with pytest.raises(ValueError, match="path"):
        await fn({})
