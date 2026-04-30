"""Tool for running pytest on builder-generated test files via StorageService."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import shared

RUN_TESTS_SCHEMA: dict[str, Any] = {
    "name": "run_tests",
    "description": "Run pytest on a test file. Returns stdout+stderr with test results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the test file (e.g. builder/test_foo.py)",
            },
        },
        "required": ["path"],
    },
}


def create_run_tests(
    s3_prefix: str,
    project_root: Path,
) -> Callable[[dict], Awaitable[str]]:
    async def run_tests(params: dict) -> str:
        if "path" not in params:
            raise ValueError("run_tests requires 'path' parameter")
        path = params["path"]
        if ".." in path or path.startswith("/"):
            raise ValueError(f"Invalid path: {path}")

        # Download builder/ files from S3 to a temp directory for pytest
        builder_prefix = f"{s3_prefix}/builder/"
        keys = await shared.storage.list(builder_prefix)

        tmp = tempfile.mkdtemp()
        try:
            # Download all builder files so imports between them work
            for key in keys:
                filename = key[len(builder_prefix) :]
                if not filename:
                    continue
                data = await shared.storage.get(key)
                dest = Path(tmp) / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)

            # The test file to run
            test_filename = path
            if test_filename.startswith("builder/"):
                test_filename = test_filename[len("builder/") :]
            test_file = Path(tmp) / test_filename
            if not test_file.exists():
                return f"Error: test file '{path}' not found in S3"

            env = os.environ.copy()
            env["PYTHONPATH"] = tmp
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "pytest",
                str(test_file),
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
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return "Error: pytest timed out after 30 seconds"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return run_tests
