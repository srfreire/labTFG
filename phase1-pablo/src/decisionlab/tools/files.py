from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

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
    "description": "Write content to a file at the given relative path, creating parent directories as needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
}


def validate_path(base_dir: Path, path: str) -> Path:
    resolved = (base_dir / path).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise ValueError(f"Path escapes base directory: {path}")
    return resolved


def create_read_file(base_dir: Path) -> Callable[[dict], Awaitable[str]]:
    async def read_file(params: dict) -> str:
        if "path" not in params:
            raise ValueError("read_file requires 'path' parameter")
        resolved = validate_path(base_dir, params["path"])
        if not resolved.exists():
            raise ValueError(f"File not found: {params['path']}")
        return resolved.read_text()

    return read_file


def create_write_file(base_dir: Path) -> Callable[[dict], Awaitable[str]]:
    async def write_file(params: dict) -> str:
        if "path" not in params:
            raise ValueError("write_file requires 'path' parameter")
        if "content" not in params:
            raise ValueError("write_file requires 'content' parameter")
        resolved = validate_path(base_dir, params["path"])
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(params["content"])
        return f"Written {len(params['content'])} chars to {params['path']}"

    return write_file
