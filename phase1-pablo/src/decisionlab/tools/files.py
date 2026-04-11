"""Tools for reading and writing files via StorageService."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import shared
from shared.artifacts import register_artifact

logger = logging.getLogger(__name__)

READ_FILE_SCHEMA: dict[str, Any] = {
    "name": "read_file",
    "description": "Read the contents of a file at the given relative path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA: dict[str, Any] = {
    "name": "write_file",
    "description": "Write content to a file at the given relative path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
}


def _infer_artifact_type(path: str) -> str:
    if path.startswith("formulations/") and path.endswith(".md"):
        return "formulation"
    if path.startswith("reasoner/") and path.endswith(".json"):
        return "reasoner_spec"
    if path.startswith("builder/") and path.endswith("_model.py"):
        return "model"
    if path.startswith("builder/test_"):
        return "test"
    if path.endswith("_validation.json"):
        return "reasoner_spec"
    return "unknown"


def create_read_file(s3_prefix: str) -> Callable[[dict], Awaitable[str]]:
    async def read_file(params: dict) -> str:
        if "path" not in params:
            raise ValueError("read_file requires 'path' parameter")
        path = params["path"]
        # Path traversal guard
        if ".." in path or path.startswith("/"):
            raise ValueError(f"Invalid path: {path}")
        key = f"{s3_prefix}/{path}"
        return await shared.storage.get_text(key)

    return read_file


def create_write_file(
    s3_prefix: str,
    run_id: str | None = None,
) -> Callable[[dict], Awaitable[str]]:
    async def write_file(params: dict) -> str:
        if "path" not in params:
            raise ValueError("write_file requires 'path' parameter")
        if "content" not in params:
            raise ValueError("write_file requires 'content' parameter")
        path = params["path"]
        content = params["content"]
        if ".." in path or path.startswith("/"):
            raise ValueError(f"Invalid path: {path}")
        key = f"{s3_prefix}/{path}"
        await shared.storage.put_text(key, content)
        if run_id:
            await register_artifact(
                key, _infer_artifact_type(path), len(content.encode()), run_id=run_id,
            )
        return f"Written {len(content)} chars to {path}"

    return write_file
