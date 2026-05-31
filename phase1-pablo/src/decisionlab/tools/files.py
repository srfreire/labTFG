"""Tools for reading and writing files via StorageService."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from decisionlab.tools.reports import sanitize_markdown_artifact
from shared.artifacts import register_artifact

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

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
    if path.startswith("builder/") and "/test_" in path:
        return "test"
    if path.endswith("_validation.json"):
        return "reasoner_spec"
    return "unknown"


def create_read_file(
    s3_prefix: str,
    *,
    storage: StorageService,
    fallback_prefixes: tuple[str, ...] = (),
) -> Callable[[dict], Awaitable[str]]:
    def is_missing_object(exc: Exception) -> bool:
        if isinstance(exc, FileNotFoundError):
            return True
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            return code in {"404", "NoSuchKey", "NotFound"}
        return False

    async def read_file(params: dict) -> str:
        if "path" not in params:
            raise ValueError("read_file requires 'path' parameter")
        path = params["path"]
        # Path traversal guard
        if ".." in path or path.startswith("/"):
            raise ValueError(f"Invalid path: {path}")
        prefixes = (s3_prefix, *fallback_prefixes)
        first_missing: Exception | None = None
        for prefix in prefixes:
            key = f"{prefix}/{path}"
            try:
                return await storage.get_text(key)
            except Exception as exc:
                if not is_missing_object(exc):
                    raise
                if first_missing is None:
                    first_missing = exc
                continue
        if first_missing is not None:
            raise first_missing
        raise FileNotFoundError(path)

    return read_file


def create_write_file(
    s3_prefix: str,
    *,
    storage: StorageService,
    db: DatabaseService,
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
        if path.endswith(".md"):
            content = sanitize_markdown_artifact(content)
        key = f"{s3_prefix}/{path}"
        await storage.put_text(key, content)
        if run_id:
            await register_artifact(
                key,
                _infer_artifact_type(path),
                len(content.encode()),
                run_id=run_id,
                db=db,
            )
        return f"Written {len(content)} chars to {path}"

    return write_file
