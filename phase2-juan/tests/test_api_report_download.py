from unittest.mock import AsyncMock, MagicMock

import pytest
import simlab.api as api_module
from fastapi import HTTPException
from simlab.api import _build_reporter_message, download_report_pdf


def _set_services(monkeypatch, *, storage=None):
    services = MagicMock()
    services.storage = storage
    monkeypatch.setattr(api_module, "_services", services)


async def test_download_report_pdf_returns_attachment(monkeypatch):
    storage = MagicMock()
    storage.get = AsyncMock(return_value=b"%PDF-1.4 report")
    _set_services(monkeypatch, storage=storage)

    response = await download_report_pdf("experiments/exp-1/analisis_final.pdf")

    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4 report"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="analisis_final.pdf"'
    )
    storage.get.assert_awaited_once_with("experiments/exp-1/analisis_final.pdf")


async def test_download_report_pdf_rejects_non_report_keys(monkeypatch):
    storage = MagicMock()
    storage.get = AsyncMock(return_value=b"not used")
    _set_services(monkeypatch, storage=storage)

    with pytest.raises(HTTPException) as exc:
        await download_report_pdf("../secret.txt")

    assert exc.value.status_code == 400
    storage.get.assert_not_called()


async def test_download_report_pdf_requires_services(monkeypatch):
    monkeypatch.setattr(api_module, "_services", None)

    with pytest.raises(HTTPException) as exc:
        await download_report_pdf("experiments/exp-1/report.pdf")

    assert exc.value.status_code == 503


async def test_download_report_pdf_maps_missing_object_to_404(monkeypatch):
    storage = MagicMock()
    storage.get = AsyncMock(side_effect=FileNotFoundError("missing"))
    _set_services(monkeypatch, storage=storage)

    with pytest.raises(HTTPException) as exc:
        await download_report_pdf("experiments/exp-1/report.pdf")

    assert exc.value.status_code == 404


def test_build_reporter_message_includes_download_metadata():
    msg = _build_reporter_message(
        {
            "pdf_paths": [
                "experiments/exp-1/analisis_final.pdf",
                "experiments/exp-1/comparativa_modelos.pdf",
            ]
        }
    )

    assert msg == {
        "type": "message",
        "from": "orchestrator",
        "text": (
            "El **Reporter** ha generado **2 informes** PDF:\n"
            "- `experiments/exp-1/analisis_final.pdf`\n"
            "- `experiments/exp-1/comparativa_modelos.pdf`"
        ),
        "reports": [
            {
                "key": "experiments/exp-1/analisis_final.pdf",
                "filename": "analisis_final.pdf",
            },
            {
                "key": "experiments/exp-1/comparativa_modelos.pdf",
                "filename": "comparativa_modelos.pdf",
            },
        ],
    }


def test_build_reporter_message_returns_none_without_paths():
    assert _build_reporter_message({}) is None
