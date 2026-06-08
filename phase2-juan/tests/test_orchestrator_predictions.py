"""Tests for Orchestrator prediction lookup."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from simlab.model_loader import ModelInfo
from simlab.orchestrator import Orchestrator


def _settings():
    return SimpleNamespace(
        ENABLE_CHAT_PERSISTENCE=False,
        ENABLE_KNOWLEDGE_READ=False,
        ENABLE_QUERY_HISTORY=False,
    )


async def test_read_predictions_uses_selected_model_run_id(monkeypatch):
    services = MagicMock()
    services.storage.get_text = AsyncMock(return_value="## Predictions\nchosen run")
    orch = Orchestrator(client=MagicMock(), services=services)
    orch._discovered_models = {
        "homeostatic-regulation/old": ModelInfo(
            id="old-id",
            paradigm="homeostatic-regulation",
            formulation="old",
            class_name="OldModel",
            description="",
            s3_model_key="models/old.py",
            run_id="run-old",
        ),
        "homeostatic-regulation/chosen": ModelInfo(
            id="chosen-id",
            paradigm="homeostatic-regulation",
            formulation="chosen",
            class_name="ChosenModel",
            description="",
            s3_model_key="models/chosen.py",
            run_id="run-chosen",
        ),
    }

    async def fake_loop(**kwargs):
        payload = await kwargs["registry"]["read_predictions"](
            {
                "paradigm_slug": "homeostatic-regulation",
                "model_id": "homeostatic-regulation/chosen",
            }
        )
        data = json.loads(payload)
        assert data["predictions"] == "chosen run"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
        )

    monkeypatch.setattr("simlab.orchestrator.load_settings", _settings)
    with patch("simlab.orchestrator.run_agent_loop", new=fake_loop):
        await orch.chat("lee predicciones")

    services.storage.get_text.assert_awaited_once_with(
        "research/run-chosen/deep/homeostatic-regulation.md"
    )


async def test_read_predictions_rejects_selected_model_without_run_id(monkeypatch):
    services = MagicMock()
    orch = Orchestrator(client=MagicMock(), services=services)
    orch._state["run_id"] = "stale-run"
    orch._discovered_models = {
        "homeostatic-regulation/chosen": ModelInfo(
            id="chosen-id",
            paradigm="homeostatic-regulation",
            formulation="chosen",
            class_name="ChosenModel",
            description="",
            s3_model_key="models/chosen.py",
            run_id=None,
        ),
    }

    async def fake_loop(**kwargs):
        payload = await kwargs["registry"]["read_predictions"](
            {
                "paradigm_slug": "homeostatic-regulation",
                "model_id": "homeostatic-regulation/chosen",
            }
        )
        data = json.loads(payload)
        assert "No run_id found for selected model" in data["error"]
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
        )

    monkeypatch.setattr("simlab.orchestrator.load_settings", _settings)
    with patch("simlab.orchestrator.run_agent_loop", new=fake_loop):
        await orch.chat("lee predicciones")

    services.storage.get_text.assert_not_called()
