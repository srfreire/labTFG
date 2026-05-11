"""Chat history serializer + bulk writer (sim-recall Phase 2).

``serialize_message`` is a pure function turning one Anthropic message
(as it lives in ``Orchestrator._messages``) into a list of
``chat_messages`` row dicts. ``persist_messages`` bulk-inserts those
rows in a single round-trip and degrades silently on DB failure.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import ChatMessage

logger = logging.getLogger(__name__)


def serialize_message(
    msg: dict[str, Any],
    *,
    session_id: uuid.UUID,
    experiment_id: uuid.UUID | None,
    tool_use_names: dict[str, str] | None = None,
) -> list[dict]:
    """Convert one Orchestrator message into 0+ chat_messages row dicts.

    Mapping (matches Phase 2 spec R3):

    - ``{"role": "user", "content": str}`` → 1 row, role ``user``.
    - ``{"role": "user", "content": [tool_result blocks]}`` → 1 row per
      block, role ``tool_result``, content is the JSON-serialized block
      content. ``tool_name`` is resolved from ``tool_use_names`` (a
      ``tool_use_id → name`` map). When unknown, ``tool_name`` is None.
    - ``{"role": "assistant", "content": [blocks]}`` →
      - ``text`` blocks (non-empty) → role ``assistant``.
      - ``tool_use`` blocks → role ``tool_use``, content is
        ``{"name": ..., "input": ...}`` JSON, ``tool_name`` = block name.

    Returns an empty list when the message contributes no rows (e.g.
    an assistant message with only empty text blocks).
    """
    role = msg.get("role")
    content = msg.get("content")
    names = tool_use_names or {}

    if role == "user":
        return _serialize_user(
            content, session_id=session_id, experiment_id=experiment_id, names=names
        )
    if role == "assistant":
        return _serialize_assistant(
            content, session_id=session_id, experiment_id=experiment_id
        )
    return []


def _serialize_user(
    content: Any,
    *,
    session_id: uuid.UUID,
    experiment_id: uuid.UUID | None,
    names: dict[str, str],
) -> list[dict]:
    if isinstance(content, str):
        if not content.strip():
            return []
        return [
            _row(
                session_id=session_id,
                experiment_id=experiment_id,
                role="user",
                content=content,
            )
        ]

    if not isinstance(content, list):
        return []

    rows: list[dict] = []
    for block in content:
        block_type = _block_field(block, "type")
        if block_type != "tool_result":
            continue
        block_content = _block_field(block, "content")
        tool_use_id = _block_field(block, "tool_use_id")
        tool_name = names.get(tool_use_id) if isinstance(tool_use_id, str) else None
        rows.append(
            _row(
                session_id=session_id,
                experiment_id=experiment_id,
                role="tool_result",
                content=_json_dumps(block_content),
                tool_name=tool_name,
            )
        )
    return rows


def _serialize_assistant(
    content: Any,
    *,
    session_id: uuid.UUID,
    experiment_id: uuid.UUID | None,
) -> list[dict]:
    if not isinstance(content, list):
        return []

    rows: list[dict] = []
    for block in content:
        block_type = _block_field(block, "type")
        if block_type == "text":
            text = _block_field(block, "text") or ""
            if not text.strip():
                continue
            rows.append(
                _row(
                    session_id=session_id,
                    experiment_id=experiment_id,
                    role="assistant",
                    content=text,
                )
            )
        elif block_type == "tool_use":
            name = _block_field(block, "name")
            input_ = _block_field(block, "input")
            rows.append(
                _row(
                    session_id=session_id,
                    experiment_id=experiment_id,
                    role="tool_use",
                    content=_json_dumps({"name": name, "input": input_}),
                    tool_name=name if isinstance(name, str) else None,
                )
            )
    return rows


def _row(
    *,
    session_id: uuid.UUID,
    experiment_id: uuid.UUID | None,
    role: str,
    content: str,
    tool_name: str | None = None,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "session_id": session_id,
        "experiment_id": experiment_id,
        "role": role,
        "content": content,
        "tool_name": tool_name,
    }


def _block_field(block: Any, name: str) -> Any:
    """Read ``block.name`` whether ``block`` is a dict or an SDK block object."""
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


async def persist_messages(session: AsyncSession, rows: list[dict]) -> None:
    """Bulk-insert ``rows`` into ``chat_messages``. Logs and swallows errors.

    No-op when ``rows`` is empty. Never raises — chat persistence must not
    interrupt the conversation.
    """
    if not rows:
        return
    try:
        await session.execute(insert(ChatMessage), rows)
        await session.commit()
    except Exception:
        logger.warning("persist_messages: bulk insert failed", exc_info=True)
