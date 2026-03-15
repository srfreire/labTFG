import pytest

from decisionlab.tools.tests import RUN_TESTS_SCHEMA, create_run_tests


def test_run_tests_schema_has_required_fields():
    assert RUN_TESTS_SCHEMA["name"] == "run_tests"
    assert "path" in RUN_TESTS_SCHEMA["input_schema"]["properties"]
    assert RUN_TESTS_SCHEMA["input_schema"]["required"] == ["path"]


@pytest.mark.asyncio
async def test_run_tests_passing_file(tmp_path):
    test_file = tmp_path / "test_passing.py"
    test_file.write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    fn = create_run_tests(base_dir=tmp_path, project_root=tmp_path)
    result = await fn({"path": "test_passing.py"})
    assert "passed" in result


@pytest.mark.asyncio
async def test_run_tests_failing_file(tmp_path):
    test_file = tmp_path / "test_failing.py"
    test_file.write_text("def test_bad():\n    assert 1 == 2\n")
    fn = create_run_tests(base_dir=tmp_path, project_root=tmp_path)
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

    test_file = tmp_path / "test_any.py"
    test_file.write_text("def test_ok():\n    pass\n")
    fn = create_run_tests(base_dir=tmp_path, project_root=tmp_path)
    result = await fn({"path": "test_any.py"})
    assert "timed out" in result


@pytest.mark.asyncio
async def test_run_tests_path_traversal(tmp_path):
    fn = create_run_tests(base_dir=tmp_path, project_root=tmp_path)
    with pytest.raises(ValueError, match="escapes base directory"):
        await fn({"path": "../../evil_test.py"})


@pytest.mark.asyncio
async def test_run_tests_missing_param(tmp_path):
    fn = create_run_tests(base_dir=tmp_path, project_root=tmp_path)
    with pytest.raises(ValueError, match="path"):
        await fn({})
