from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from decisionlab.tools.files import validate_path

RUN_TESTS_SCHEMA: dict[str, Any] = {
    "name": "run_tests",
    "description": "Run pytest on a test file. Returns stdout+stderr with test results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the test file"},
        },
        "required": ["path"],
    },
}


def create_run_tests(base_dir: Path, project_root: Path) -> Callable[[dict], Awaitable[str]]:
    async def run_tests(params: dict) -> str:
        if "path" not in params:
            raise ValueError("run_tests requires 'path' parameter")
        resolved = validate_path(base_dir, params["path"])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(base_dir / "builder")
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "pytest",
            str(resolved),
            "-v",
            "--tb=short",
            cwd=str(project_root),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            return stdout.decode()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Error: pytest timed out after 30 seconds"

    return run_tests
