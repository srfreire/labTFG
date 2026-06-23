"""Tests for model discovery and loading with UUID/slug schema."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.model_loader import (
    ModelInfo,
    cleanup_temp_models,
    discover_models,
    load_model,
)

# ---------------------------------------------------------------------------
# Fixtures — fake DB rows matching the new Model schema
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _make_db_row(
    *,
    paradigm: str = "homeostatic-regulation",
    formulation: str = "drive-reduction-rl",
    class_name: str = "DriveReductionRLModel",
    description: str | None = "A drive reduction RL model",
    run_id: uuid.UUID | None | object = _SENTINEL,
    s3_model_key: str = "models/abc/builder/homeostatic-regulation/drive-reduction-rl_model.py",
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.paradigm = paradigm
    row.formulation = formulation
    row.class_name = class_name
    row.description = description
    row.run_id = uuid.uuid4() if run_id is _SENTINEL else run_id
    row.s3_model_key = s3_model_key
    return row


def _mock_session_with_rows(rows: list) -> tuple[AsyncMock, MagicMock]:
    """Return (mock_session, mock_db) wired to return *rows* from a SELECT."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.get_session.return_value = mock_session
    return mock_session, mock_db


# ---------------------------------------------------------------------------
# discover_models tests
# ---------------------------------------------------------------------------


async def test_discover_returns_dict_keyed_by_paradigm_formulation():
    row = _make_db_row(
        paradigm="homeostatic-regulation", formulation="drive-reduction-rl"
    )
    _, mock_db = _mock_session_with_rows([row])

    models = await discover_models(db=mock_db)

    assert "homeostatic-regulation/drive-reduction-rl" in models
    info = models["homeostatic-regulation/drive-reduction-rl"]
    assert info.paradigm == "homeostatic-regulation"
    assert info.formulation == "drive-reduction-rl"
    assert info.class_name == "DriveReductionRLModel"


async def test_discover_models_multiple_runs():
    run1, run2 = uuid.uuid4(), uuid.uuid4()
    row1 = _make_db_row(paradigm="p1", formulation="f1", run_id=run1, class_name="M1")
    row2 = _make_db_row(paradigm="p2", formulation="f2", run_id=run2, class_name="M2")
    _, mock_db = _mock_session_with_rows([row1, row2])

    models = await discover_models(db=mock_db)

    assert len(models) == 2
    assert "p1/f1" in models
    assert "p2/f2" in models
    assert models["p1/f1"].run_id == str(run1)
    assert models["p2/f2"].run_id == str(run2)


async def test_discover_models_empty_table():
    _, mock_db = _mock_session_with_rows([])

    models = await discover_models(db=mock_db)

    assert models == {}


async def test_discover_models_null_description():
    row = _make_db_row(description=None)
    _, mock_db = _mock_session_with_rows([row])

    models = await discover_models(db=mock_db)

    info = next(iter(models.values()))
    assert info.description == ""


async def test_discover_models_null_run_id():
    row = _make_db_row(run_id=None)
    _, mock_db = _mock_session_with_rows([row])

    models = await discover_models(db=mock_db)

    info = next(iter(models.values()))
    assert info.run_id is None


async def test_discover_models_duplicate_key_keeps_last_row():
    older_run, newer_run = uuid.uuid4(), uuid.uuid4()
    older = _make_db_row(
        paradigm="same",
        formulation="model",
        run_id=older_run,
        class_name="OlderModel",
    )
    newer = _make_db_row(
        paradigm="same",
        formulation="model",
        run_id=newer_run,
        class_name="NewerModel",
    )
    _, mock_db = _mock_session_with_rows([older, newer])

    models = await discover_models(db=mock_db)

    assert list(models) == ["same/model"]
    assert models["same/model"].class_name == "NewerModel"
    assert models["same/model"].run_id == str(newer_run)


# ---------------------------------------------------------------------------
# ModelInfo tests
# ---------------------------------------------------------------------------


def test_model_info_has_required_fields():
    info = ModelInfo(
        id="abc-123",
        paradigm="homeostatic-regulation",
        formulation="drive-reduction-rl",
        class_name="DriveReductionRLModel",
        description="A model",
        s3_model_key="models/run1/builder/homeostatic-regulation/drive-reduction-rl_model.py",
        run_id="run-uuid",
    )
    assert info.id == "abc-123"
    assert info.paradigm == "homeostatic-regulation"
    assert info.formulation == "drive-reduction-rl"
    assert info.class_name == "DriveReductionRLModel"
    assert info.run_id == "run-uuid"


def test_model_info_run_id_defaults_to_none():
    info = ModelInfo(
        id="abc",
        paradigm="p",
        formulation="f",
        class_name="C",
        description="",
        s3_model_key="k",
    )
    assert info.run_id is None


# ---------------------------------------------------------------------------
# load_model tests
# ---------------------------------------------------------------------------


def _make_model_info(**overrides) -> ModelInfo:
    """Build a ModelInfo with sensible defaults, overridable per-test."""
    defaults = dict(
        id="uuid-0",
        paradigm="test-paradigm",
        formulation="fake-model",
        class_name="FakeModel",
        description="test",
        s3_model_key="models/run/builder/test-paradigm/fake-model_model.py",
    )
    return ModelInfo(**(defaults | overrides))


MODEL_SOURCE = '''\
"""A simple test model."""
import random

class FakeModel:
    def __init__(self, **kwargs):
        self.state = {"energy": random.uniform(0, 100)}

    def decide(self, perception):
        class Action:
            name = random.choice(["stay", "move_up", "move_down"])
            params = {}
        return Action()

    def update(self, action, reward, new_perception):
        pass

    def get_state(self):
        return self.state
'''


MODEL_SOURCE_WITH_INTERNAL_RNG = '''\
"""A model that keeps its own RNG."""
import random

class InternalRngModel:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.state = {"energy": self.rng.uniform(0, 100)}

    def decide(self, perception):
        class Action:
            name = self.rng.choice(["stay", "move_up", "move_down"])
            params = {}
        return Action()

    def update(self, action, reward, new_perception):
        pass

    def get_state(self):
        return self.state
'''


async def test_load_model_returns_decision_model():
    info = _make_model_info()

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=MODEL_SOURCE.encode())
    model = await load_model(info, storage=mock_storage)

    assert hasattr(model, "decide")
    assert hasattr(model, "update")
    assert hasattr(model, "get_state")
    state = model.get_state()
    assert "energy" in state
    assert isinstance(state["energy"], float)


async def test_load_model_uses_registered_class_name_when_multiple_classes_match():
    source = """\
class AlphaModel:
    def decide(self, p):
        pass
    def update(self, a, r, p):
        pass
    def get_state(self):
        return {"name": "alpha"}

class TargetModel:
    def decide(self, p):
        pass
    def update(self, a, r, p):
        pass
    def get_state(self):
        return {"name": "target"}
"""
    info = _make_model_info(class_name="TargetModel")

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=source.encode())
    model = await load_model(info, storage=mock_storage)

    assert model.get_state() == {"name": "target"}


async def test_load_model_with_seed():
    info = _make_model_info()
    perception = {
        "x": 0,
        "y": 0,
        "grid_width": 8,
        "grid_height": 8,
        "step": 0,
        "resources": {},
        "last_action_result": {},
    }

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=MODEL_SOURCE.encode())
    m1 = await load_model(info, storage=mock_storage, seed=42)
    m2 = await load_model(info, storage=mock_storage, seed=42)

    # Same seed → same random state → same initial energy and same decide() output
    assert m1.get_state() == m2.get_state()
    a1 = m1.decide(perception)
    a2 = m2.decide(perception)
    assert a1.name == a2.name


async def test_load_model_with_seed_supports_models_that_create_internal_rng():
    info = _make_model_info(class_name="InternalRngModel")
    perception = {
        "x": 0,
        "y": 0,
        "grid_width": 8,
        "grid_height": 8,
        "step": 0,
        "resources": {},
        "last_action_result": {},
    }

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=MODEL_SOURCE_WITH_INTERNAL_RNG.encode())
    m1 = await load_model(info, storage=mock_storage, seed=42)
    m2 = await load_model(info, storage=mock_storage, seed=42)

    assert m1.get_state() == m2.get_state()
    assert m1.decide(perception).name == m2.decide(perception).name


async def test_load_model_no_model_class_raises():
    bad_source = "x = 42\n"
    info = _make_model_info(paradigm="bad", formulation="noclass", class_name="Nothing")

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=bad_source.encode())
    with pytest.raises(ValueError, match="No decision model class"):
        await load_model(info, storage=mock_storage)


async def test_load_model_bad_kwargs_raises():
    source_no_kwargs = """\
class StrictModel:
    def __init__(self):
        pass
    def decide(self, p):
        pass
    def update(self, a, r, p):
        pass
    def get_state(self):
        return {}
"""
    info = _make_model_info(
        paradigm="strict", formulation="no-kwargs", class_name="StrictModel"
    )

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=source_no_kwargs.encode())
    with pytest.raises(ValueError, match="Failed to instantiate"):
        await load_model(info, storage=mock_storage, nonexistent_param=999)


async def test_load_model_temp_dir_is_cleaned_after_instantiation(tmp_path):
    cleanup_temp_models()
    info = _make_model_info()
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=MODEL_SOURCE.encode())
    temp_dir = tmp_path / "model_tmp"
    temp_dir.mkdir()

    with patch("simlab.model_loader.tempfile.mkdtemp", return_value=str(temp_dir)):
        model = await load_model(info, storage=mock_storage)

    assert hasattr(model, "decide")
    assert not temp_dir.exists()
