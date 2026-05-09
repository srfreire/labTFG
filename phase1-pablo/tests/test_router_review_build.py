"""Tests for Router._review_build (P4-002 + P5-003 + P5-004)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.router import PipelineState, Router, Stage
from shared.services import Services

TEST_RUN_ID = "00000000-0000-4000-8000-000000000001"


def _make_state(tmp_path: Path) -> PipelineState:
    return PipelineState(
        stage=Stage.REVIEW_BUILD,
        problem="test problem",
        reports_dir=tmp_path,
        run_id=TEST_RUN_ID,
        approved_paradigms=["homeostatic"],
        selected_formulations={"homeostatic": ["pi-controller", "dual-process"]},
        approved_specs={"homeostatic": ["pi-controller", "dual-process"]},
        build_results={"pi-controller": "Model OK", "dual-process": "Model OK"},
    )


def _mock_db_session():
    """Return (mock_db, mock_session) usable as a Services.db drop-in."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    mock_db = MagicMock()

    @asynccontextmanager
    async def fake_get_session():
        yield mock_session

    mock_db.get_session = fake_get_session
    return mock_db, mock_session


def _make_router(state: PipelineState, *, db=None, storage=None) -> Router:
    client = AsyncMock()
    search = MagicMock()
    services = Services(
        db=db if db is not None else MagicMock(),
        storage=storage if storage is not None else MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )
    with patch.object(Router, "_init_memory_agent", return_value=None):
        return Router(
            client=client,
            state=state,
            search=search,
            project_root=state.reports_dir.parent,
            services=services,
        )


class TestReviewBuildReasonerReruns:
    @pytest.mark.asyncio
    async def test_reasoner_rerun_triggers_cascade(self, tmp_path):
        """When review_build returns reasoner_reruns, Reasoner and Builder run."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [], ["homeostatic"]
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_storage = MagicMock()
        mock_storage.delete = AsyncMock()
        mock_storage.get_text = AsyncMock(
            return_value="class PIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
        ):
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst

            await router._review_build()

        # Reasoner was called for the paradigm
        mock_reasoner_inst.run.assert_called_once_with(
            {"homeostatic": ["pi-controller", "dual-process"]}
        )
        # Builder was called with dict-based approved_specs
        mock_builder_inst.run.assert_called_once_with(
            {"homeostatic": ["pi-controller", "dual-process"]}
        )
        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_no_reasoner_reruns_proceeds_normally(self, tmp_path):
        """Without reasoner_reruns, proceeds to DONE and registers models."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller", "dual-process"], [], []

        mock_db, mock_session = _mock_db_session()
        # execute() returns a result with scalar_one_or_none() = None (no existing row)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(
            return_value="class PIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )
        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_rejections_rerun_builder_only(self, tmp_path):
        """Regular rejections re-run only the Builder (not Reasoner)."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [("pi-controller", "homeostatic", "fix tests")], []
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(
            return_value="class PIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
        ):
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst

            await router._review_build()

        # Builder was called with dict-based approved_specs for the rejection
        mock_builder_inst.run.assert_called_with({"homeostatic": ["pi-controller"]})
        # Reasoner was NOT called
        mock_reasoner_inst.run.assert_not_called()
        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_stale_validation_files_cleaned_after_rerun(self, tmp_path):
        """Validation files at nested paths are deleted after Reasoner→Builder rerun."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [], ["homeostatic"]
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_storage = MagicMock()
        mock_storage.delete = AsyncMock()
        mock_storage.get_text = AsyncMock(
            return_value="class PIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
        ):
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst

            await router._review_build()

        # Validation cleanup uses nested paths
        delete_calls = mock_storage.delete.call_args_list
        expected_paths = {
            f"models/{TEST_RUN_ID}/builder/homeostatic/pi-controller_validation.json",
            f"models/{TEST_RUN_ID}/builder/homeostatic/dual-process_validation.json",
        }
        actual_paths = {c.args[0] for c in delete_calls}
        assert actual_paths == expected_paths
        assert state.stage == Stage.DONE


class TestModelRegistration:
    """P5-004: Model registration at approval in _review_build."""

    @pytest.mark.asyncio
    async def test_approved_models_are_registered(self, tmp_path):
        """Approved builds insert Model rows in Postgres."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller", "dual-process"], [], []

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        added_models = []
        original_add = mock_session.add

        def track_add(obj):
            added_models.append(obj)
            original_add(obj)

        mock_session.add = track_add

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(
            side_effect=lambda key: (
                "class PIControllerModel:\n    pass\n"
                if "pi-controller" in key
                else "class DualProcessModel:\n    pass\n"
            )
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert state.stage == Stage.DONE
        assert len(added_models) == 2

        from shared.models import Model

        for m in added_models:
            assert isinstance(m, Model)
            assert m.paradigm == "homeostatic"
            assert m.formulation in ("pi-controller", "dual-process")
            assert m.s3_model_key.startswith(
                f"models/{TEST_RUN_ID}/builder/homeostatic/"
            )
            assert m.s3_test_key.startswith(
                f"models/{TEST_RUN_ID}/builder/homeostatic/"
            )

        # Phase E: class_name is now derived from the formulation slug,
        # not extracted from the source file. So the regex-friendly source
        # body has been swapped for a deterministic slug -> class mapping.
        class_names = {m.class_name for m in added_models}
        assert class_names == {"PiControllerModel", "DualProcessModel"}

    @pytest.mark.asyncio
    async def test_class_name_derived_from_slug(self, tmp_path):
        """Phase E: class_name is derived from the formulation slug, not from
        the source file. The Builder is instructed to use exactly that
        identifier so the registry row stays aligned with the spec_id."""
        state = _make_state(tmp_path)
        state.approved_specs = {"homeostatic": ["homeostatic-pi"]}
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["homeostatic-pi"], [], []

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        added_models = []
        mock_session.add = lambda obj: added_models.append(obj)

        mock_storage = MagicMock()
        # Source body deliberately disagrees with the slug — the
        # registry must still use the derived name.
        mock_storage.get_text = AsyncMock(
            return_value='class WildlyDifferentName:\n    """drift"""\n'
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert len(added_models) == 1
        assert added_models[0].class_name == "HomeostaticPiModel"

    @pytest.mark.asyncio
    async def test_missing_model_file_skips_registration(self, tmp_path):
        """Missing model file in S3 logs warning and skips without crashing."""
        state = _make_state(tmp_path)
        state.approved_specs = {"homeostatic": ["pi-controller"]}
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller"], [], []

        mock_db, mock_session = _mock_db_session()
        mock_session.execute = AsyncMock()

        added_models = []
        mock_session.add = lambda obj: added_models.append(obj)

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(side_effect=FileNotFoundError("not found"))
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert state.stage == Stage.DONE
        assert len(added_models) == 0  # No model registered

    @pytest.mark.asyncio
    async def test_rerun_updates_existing_model_row(self, tmp_path):
        """Re-run of a previously approved model updates the existing row."""
        state = _make_state(tmp_path)
        state.approved_specs = {"homeostatic": ["pi-controller"]}
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller"], [], []

        # Simulate an existing Model row
        existing_model = MagicMock()
        existing_model.class_name = "OldClassName"
        existing_model.s3_model_key = "old/path.py"
        existing_model.s3_test_key = "old/test.py"

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_model
        mock_session.execute = AsyncMock(return_value=mock_result)

        added_models = []
        mock_session.add = lambda obj: added_models.append(obj)

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(
            return_value="class NewPIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert state.stage == Stage.DONE
        # No new rows added — existing was updated
        assert len(added_models) == 0
        # Phase E: derived from slug, not from source.
        assert existing_model.class_name == "PiControllerModel"
        assert "pi-controller_model.py" in existing_model.s3_model_key
        assert "test_pi-controller.py" in existing_model.s3_test_key

    @pytest.mark.asyncio
    async def test_s3_keys_use_slug_paths(self, tmp_path):
        """Model.s3_model_key and s3_test_key use correct slug-based paths."""
        state = _make_state(tmp_path)
        state.approved_specs = {"homeostatic": ["pi-controller"]}
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller"], [], []

        mock_db, mock_session = _mock_db_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        added_models = []
        mock_session.add = lambda obj: added_models.append(obj)

        mock_storage = MagicMock()
        mock_storage.get_text = AsyncMock(
            return_value="class PIControllerModel:\n    pass\n"
        )
        router._services = type(router._services)(
            db=mock_db,
            storage=mock_storage,
            kg=None,
            vectors=None,
            embeddings=None,
        )

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert len(added_models) == 1
        m = added_models[0]
        assert (
            m.s3_model_key
            == f"models/{TEST_RUN_ID}/builder/homeostatic/pi-controller_model.py"
        )
        assert (
            m.s3_test_key
            == f"models/{TEST_RUN_ID}/builder/homeostatic/test_pi-controller.py"
        )
