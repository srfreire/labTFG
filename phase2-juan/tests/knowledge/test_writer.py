"""P1-004 — unit tests for TrackerMemoryWriter with mocked infra."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.knowledge import ModelInfo, SimulationContext, TrackerMemoryWriter

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _model(**overrides):
    base = {
        "model_id": "m-1",
        "class_name": "DriveReductionRL",
        "paradigm": "homeostatic-regulation",
        "formulation": "drive-reduction-rl",
        "phase1_run_id": "r-1",
    }
    base.update(overrides)
    return ModelInfo(**base)


def _context(agent_to_model=None, **overrides):
    base = {
        "phase2_experiment_id": "exp-1",
        "environment": "grid_10x10",
        "steps": 200,
        "seed": 42,
        "agent_to_model": agent_to_model or {},
    }
    base.update(overrides)
    return SimulationContext(**base)


def _make_writer(embed_return=None, dense_side_effect=None, sparse_side_effect=None):
    """Construct a writer with AsyncMock services.

    Returns the writer plus a dict of mocks the test can assert against.
    """
    vec = MagicMock()
    vec.upsert_dense = AsyncMock(side_effect=dense_side_effect)
    vec.upsert_sparse = AsyncMock(side_effect=sparse_side_effect)

    emb = MagicMock()
    emb.embed_texts = AsyncMock(return_value=embed_return or [])

    session = MagicMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.get_session = lambda: session

    writer = TrackerMemoryWriter(vector_store=vec, embedding_service=emb, db=db)
    mocks = {"vec": vec, "emb": emb, "db": db, "session": session}
    return writer, mocks


def _tracker_single_model():
    """1 summary + 2 trajectories + 3 episodes (2 filtered, 1 kept)."""
    return {
        "summary": "Both agents foraged; agent_1 starved at step 120.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 200,
                "resources_consumed": 5,
                "actions": {"move_east": 80, "move_west": 60, "consume": 5},
            },
            "agent_1": {
                "steps_survived": 120,
                "resources_consumed": 1,
                "actions": {"move_north": 40, "consume": 1},
            },
        },
        "episodes": [
            {
                "agent": "agent_0",
                "type": "foraging_success",
                "step": 30,
                "description": "ate",
            },
            {
                "agent": "agent_0",
                "type": "exploration",
                "step": 50,
                "description": "scouted",
            },
            {
                "agent": "agent_1",
                "type": "starvation",
                "step": 120,
                "description": "ran out of energy",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 1. Happy path — 1 model, 2 agents
# ---------------------------------------------------------------------------


async def test_happy_path_single_model_two_agents():
    model = _model()
    ctx = _context(agent_to_model={"agent_0": model, "agent_1": model})
    tracker_json = json.dumps(_tracker_single_model())

    # 4 facts expected: 1 summary + 2 trajectories + 1 episode
    writer, m = _make_writer(embed_return=[[0.1] * 5] * 4)

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(tracker_json, ctx)

    assert result.skipped_reason is None
    assert result.summaries_written == 1
    assert result.trajectories_written == 2
    assert result.episodes_written == 1
    assert result.episodes_filtered == 2

    # Batch embed: exactly one call with 4 items.
    m["emb"].embed_texts.assert_awaited_once()
    assert len(m["emb"].embed_texts.await_args.args[0]) == 4

    # Per-fact: 4 create_memory + 4 dense upserts + 4 sparse upserts.
    assert cm.await_count == 4
    assert m["vec"].upsert_dense.await_count == 4
    assert m["vec"].upsert_sparse.await_count == 4

    # Single commit at the end.
    m["session"].commit.assert_awaited_once()

    # UUID shared between Postgres and Qdrant upsert calls for every fact.
    pg_ids = [call.kwargs["id"] for call in cm.await_args_list]
    dense_ids = [call.args[1] for call in m["vec"].upsert_dense.await_args_list]
    sparse_ids = [call.args[1] for call in m["vec"].upsert_sparse.await_args_list]
    # create_memory receives uuid.UUID, upserts receive str(uuid) — compare as strings.
    assert [str(x) for x in pg_ids] == dense_ids == sparse_ids


# ---------------------------------------------------------------------------
# 2. Comparison run — 2 models, each with 2 agents
# ---------------------------------------------------------------------------


async def test_comparison_run_tags_correct_paradigm_per_fact():
    m1 = _model(model_id="m-1", class_name="A", formulation="f-a")
    m2 = _model(model_id="m-2", class_name="B", formulation="f-b")
    ctx = _context(
        agent_to_model={
            "agent_0": m1,
            "agent_1": m1,
            "agent_2": m2,
            "agent_3": m2,
        }
    )
    tracker = {
        "summary": "Comparison between A and B.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 50,
                "resources_consumed": 1,
                "actions": {"x": 1},
            },
            "agent_2": {
                "steps_survived": 40,
                "resources_consumed": 2,
                "actions": {"y": 1},
            },
        },
        "episodes": [],
    }
    # 3 facts: 1 summary + 2 trajectories
    writer, _m = _make_writer(embed_return=[[0.1]] * 3)

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(json.dumps(tracker), ctx)

    assert result.summaries_written == 1
    assert result.trajectories_written == 2
    assert result.episodes_written == 0

    # Grab metadata_ kwargs passed to create_memory in order.
    metas = [call.kwargs["metadata_"] for call in cm.await_args_list]
    summary_meta, traj0_meta, traj1_meta = metas

    # Summary references BOTH class names via models_compared.
    assert set(summary_meta["models_compared"]) == {"A", "B"}

    # Trajectories carry the paradigm/formulation of their respective models.
    assert traj0_meta["agent_id"] == "agent_0"
    assert traj0_meta["formulation"] == "f-a"
    assert traj1_meta["agent_id"] == "agent_2"
    assert traj1_meta["formulation"] == "f-b"


# ---------------------------------------------------------------------------
# 3. Invalid JSON
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_input", ["not json", "", "[1, 2, 3]"])
async def test_invalid_json_short_circuits(bad_input):
    writer, m = _make_writer()
    ctx = _context(agent_to_model={"agent_0": _model()})

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(bad_input, ctx)

    assert result.skipped_reason == "invalid_json"
    assert (
        result.summaries_written,
        result.trajectories_written,
        result.episodes_written,
    ) == (0, 0, 0)
    m["emb"].embed_texts.assert_not_awaited()
    m["vec"].upsert_dense.assert_not_awaited()
    m["vec"].upsert_sparse.assert_not_awaited()
    cm.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. Empty tracker
# ---------------------------------------------------------------------------


async def test_empty_tracker_returns_no_relevant_content():
    writer, m = _make_writer()
    ctx = _context(agent_to_model={"agent_0": _model()})
    tracker = {"summary": "", "trajectories": {}, "episodes": []}

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(json.dumps(tracker), ctx)

    assert result.skipped_reason == "no_relevant_content"
    m["emb"].embed_texts.assert_not_awaited()
    cm.assert_not_awaited()


async def test_all_routine_episodes_returns_no_relevant_content():
    """A tracker with only filtered episodes still reports filtered count."""
    writer, _m = _make_writer()
    ctx = _context(agent_to_model={"agent_0": _model()})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {
                "agent": "agent_0",
                "type": "foraging_success",
                "step": 1,
                "description": "x",
            },
            {"agent": "agent_0", "type": "exploration", "step": 2, "description": "y"},
        ],
    }
    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()):
        result = await writer.write(json.dumps(tracker), ctx)

    assert result.skipped_reason == "no_relevant_content"
    assert result.episodes_filtered == 2


# ---------------------------------------------------------------------------
# 5. Qdrant dense fails on 2nd fact — others keep going
# ---------------------------------------------------------------------------


async def test_qdrant_dense_failure_does_not_abort_batch():
    model = _model()
    ctx = _context(agent_to_model={"agent_0": model, "agent_1": model})
    tracker_json = json.dumps(_tracker_single_model())  # 4 facts

    # Second dense upsert raises, the other three succeed.
    call_count = {"n": 0}

    async def flaky_dense(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("qdrant hiccup")

    writer, m = _make_writer(
        embed_return=[[0.1] * 5] * 4,
        dense_side_effect=flaky_dense,
    )

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(tracker_json, ctx)

    # Writer did not abort — result reflects all 4 facts as written (PG rows kept).
    assert result.skipped_reason is None
    assert (
        result.summaries_written + result.trajectories_written + result.episodes_written
        == 4
    )

    # All 4 create_memory + 4 dense attempts + 4 sparse upserts executed.
    assert cm.await_count == 4
    assert m["vec"].upsert_dense.await_count == 4
    assert m["vec"].upsert_sparse.await_count == 4

    # Single commit still happens.
    m["session"].commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# 6. Voyage failure — captured, zero counters
# ---------------------------------------------------------------------------


async def test_voyage_failure_returns_error_skipped_reason():
    model = _model()
    ctx = _context(agent_to_model={"agent_0": model, "agent_1": model})
    tracker_json = json.dumps(_tracker_single_model())

    writer, m = _make_writer()
    m["emb"].embed_texts.side_effect = RuntimeError("voyage exploded")

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        result = await writer.write(tracker_json, ctx)

    assert result.skipped_reason is not None
    assert result.skipped_reason.startswith("error:")
    assert "voyage exploded" in result.skipped_reason
    assert (
        result.summaries_written,
        result.trajectories_written,
        result.episodes_written,
    ) == (0, 0, 0)

    cm.assert_not_awaited()
    m["vec"].upsert_dense.assert_not_awaited()
    m["session"].commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. Unknown agent_id in episode — skipped, rest proceeds
# ---------------------------------------------------------------------------


async def test_unknown_agent_id_in_episode_is_skipped_not_written(caplog):
    model = _model()
    ctx = _context(agent_to_model={"agent_0": model})  # only agent_0 known
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {"agent": "agent_0", "type": "starvation", "step": 10, "description": "a"},
            {
                "agent": "ghost_agent",
                "type": "starvation",
                "step": 20,
                "description": "b",
            },
        ],
    }
    # Only 1 fact survives (ghost skipped pre-embedding).
    writer, m = _make_writer(embed_return=[[0.1]])

    with patch("simlab.knowledge.writer.create_memory", new=AsyncMock()) as cm:
        with caplog.at_level("WARNING"):
            result = await writer.write(json.dumps(tracker), ctx)

    assert result.episodes_written == 1
    assert result.episodes_filtered == 0  # ghost wasn't a filtered type
    assert any("ghost_agent" in r.message for r in caplog.records)

    cm.assert_awaited_once()
    m["vec"].upsert_dense.assert_awaited_once()


# ---------------------------------------------------------------------------
# Sanity: sparse upsert is skipped when tokenizer emits empty vector
# ---------------------------------------------------------------------------


async def test_empty_sparse_vector_skips_sparse_upsert():
    """If tokenize_to_sparse returns ([], []), we must not call upsert_sparse."""
    model = _model()
    ctx = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "A",
        "trajectories": {},
        "episodes": [],
    }
    writer, m = _make_writer(embed_return=[[0.1]])

    with (
        patch(
            "simlab.knowledge.writer._load_tokenizer",
            return_value=lambda _text: ([], []),
        ),
        patch("simlab.knowledge.writer.create_memory", new=AsyncMock()),
    ):
        result = await writer.write(json.dumps(tracker), ctx)

    assert result.summaries_written == 1
    m["vec"].upsert_dense.assert_awaited_once()
    m["vec"].upsert_sparse.assert_not_awaited()
