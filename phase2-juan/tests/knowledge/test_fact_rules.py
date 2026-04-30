"""P1-002 — tests for pure fact generation helpers."""

from __future__ import annotations

import pytest
from simlab.knowledge import ModelInfo, SimulationContext
from simlab.knowledge.facts import (
    build_all_facts,
    build_episode_facts,
    build_summary_fact,
    build_trajectory_facts,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _model(
    class_name="HomeostaticDriveReductionRL",
    paradigm="homeostatic-regulation",
    formulation="drive-reduction-rl",
    model_id="m-1",
    phase1_run_id="r-1",
):
    return ModelInfo(
        model_id=model_id,
        class_name=class_name,
        paradigm=paradigm,
        formulation=formulation,
        phase1_run_id=phase1_run_id,
    )


def _context(agent_to_model=None, env="grid_10x10", steps=200, seed=42, exp_id="exp-1"):
    return SimulationContext(
        phase2_experiment_id=exp_id,
        environment=env,
        steps=steps,
        seed=seed,
        agent_to_model=agent_to_model or {},
    )


# ---------------------------------------------------------------------------
# Single-model happy path (1 summary + 2 trajectories + mixed episodes)
# ---------------------------------------------------------------------------


def test_single_model_full_pipeline():
    model = _model()
    context = _context(agent_to_model={"agent_0": model, "agent_1": model})
    tracker = {
        "summary": "Both agents explored the grid; agent_1 starved at step 120.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 200,
                "resources_consumed": 5,
                "actions": {"move_east": 80, "move_west": 60, "consume": 5, "wait": 55},
            },
            "agent_1": {
                "steps_survived": 120,
                "resources_consumed": 1,
                "actions": {"move_north": 40, "move_south": 35, "consume": 1},
            },
        },
        "episodes": [
            {
                "agent": "agent_0",
                "type": "foraging_success",
                "step": 30,
                "description": "ate a resource",
            },
            {
                "agent": "agent_0",
                "type": "exploration",
                "steps": [10, 40],
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

    facts, filtered = build_all_facts(tracker, context)

    # 1 summary + 2 trajectories + 1 episode (2 filtered out)
    assert len(facts) == 4
    assert filtered == 2

    summary, traj0, traj1, episode = facts
    assert summary.memory_type == "semantic"
    assert summary.importance == 5
    assert "HomeostaticDriveReductionRL" in summary.text
    assert "homeostatic-regulation/drive-reduction-rl" in summary.text
    assert "grid_10x10" in summary.text
    assert summary.metadata["paradigm"] == "homeostatic-regulation"
    assert summary.metadata["formulation"] == "drive-reduction-rl"
    assert summary.metadata["phase2_experiment_id"] == "exp-1"
    assert summary.metadata["steps"] == 200
    assert summary.metadata["seed"] == 42

    for traj in (traj0, traj1):
        assert traj.memory_type == "semantic"
        assert traj.importance == 6
        assert "agent_" in traj.text
        assert "survived" in traj.text
        assert "top actions" in traj.text
        assert "agent_id" in traj.metadata

    # Trajectory order mirrors trajectories dict iteration
    assert traj0.metadata["agent_id"] == "agent_0"
    assert traj1.metadata["agent_id"] == "agent_1"

    # Top-3 actions verified for agent_0 (4 actions, take top 3 by count)
    assert "move_east(80)" in traj0.text
    assert "move_west(60)" in traj0.text
    assert "wait(55)" in traj0.text
    assert (
        "consume" not in traj0.text.split("top actions:")[1]
    )  # consume had 5, excluded

    # Episode
    assert episode.memory_type == "episodic"
    assert episode.importance == 9  # starvation
    assert "starvation" in episode.text
    assert "agent_1" in episode.text
    assert "step=120" in episode.text
    assert episode.metadata["episode_type"] == "starvation"
    assert episode.metadata["step"] == 120
    assert episode.metadata["agent_id"] == "agent_1"


# ---------------------------------------------------------------------------
# Comparison run — 2 models, 2 agents each
# ---------------------------------------------------------------------------


def test_comparison_run_tags_each_fact_with_correct_model():
    m1 = _model(
        class_name="DriveReductionRL",
        paradigm="homeostatic-regulation",
        formulation="drive-reduction-rl",
        model_id="m-1",
    )
    m2 = _model(
        class_name="PINegativeFeedback",
        paradigm="homeostatic-regulation",
        formulation="pi-negative-feedback",
        model_id="m-2",
    )
    context = _context(
        agent_to_model={
            "agent_0": m1,
            "agent_1": m1,
            "agent_2": m2,
            "agent_3": m2,
        }
    )
    tracker = {
        "summary": "Comparison run between two controllers.",
        "trajectories": {
            "agent_0": {
                "steps_survived": 200,
                "resources_consumed": 4,
                "actions": {"move_east": 50},
            },
            "agent_2": {
                "steps_survived": 180,
                "resources_consumed": 3,
                "actions": {"move_west": 45},
            },
        },
        "episodes": [
            {
                "agent": "agent_0",
                "type": "state_change",
                "step": 90,
                "description": "energy spike",
            },
            {
                "agent": "agent_2",
                "type": "foraging_failure",
                "step": 150,
                "description": "missed resource",
            },
        ],
    }

    facts, filtered = build_all_facts(tracker, context)
    assert filtered == 0
    assert len(facts) == 5  # 1 summary + 2 trajectories + 2 episodes

    summary = facts[0]
    assert "models_compared" in summary.metadata
    assert set(summary.metadata["models_compared"]) == {
        "DriveReductionRL",
        "PINegativeFeedback",
    }

    traj_by_agent = {f.metadata["agent_id"]: f for f in facts[1:3]}
    assert traj_by_agent["agent_0"].metadata["formulation"] == "drive-reduction-rl"
    assert traj_by_agent["agent_2"].metadata["formulation"] == "pi-negative-feedback"

    ep_by_agent = {f.metadata["agent_id"]: f for f in facts[3:]}
    assert ep_by_agent["agent_0"].metadata["model_class_name"] == "DriveReductionRL"
    assert ep_by_agent["agent_2"].metadata["model_class_name"] == "PINegativeFeedback"


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ep_type", ["foraging_success", "exploration", "exploitation"])
def test_routine_episodes_are_filtered(ep_type):
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {"agent": "agent_0", "type": ep_type, "step": 10, "description": "x"}
        ],
    }
    facts, filtered = build_episode_facts(tracker, context)
    assert facts == []
    assert filtered == 1


@pytest.mark.parametrize(
    "ep_type,expected_importance",
    [
        ("starvation", 9),
        ("state_change", 8),
        ("foraging_failure", 7),
        ("weird_behavior", 6),
    ],
)
def test_episode_importance_by_type(ep_type, expected_importance):
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {"agent": "agent_0", "type": ep_type, "step": 5, "description": "x"}
        ],
    }
    facts, filtered = build_episode_facts(tracker, context)
    assert filtered == 0
    assert len(facts) == 1
    assert facts[0].importance == expected_importance


# ---------------------------------------------------------------------------
# Step range
# ---------------------------------------------------------------------------


def test_episode_with_step_range():
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {
                "agent": "agent_0",
                "type": "state_change",
                "steps": [100, 120],
                "description": "gradual depletion",
            }
        ],
    }
    facts, _ = build_episode_facts(tracker, context)
    assert len(facts) == 1
    fact = facts[0]
    assert "steps=100..120" in fact.text
    assert fact.metadata["step_start"] == 100
    assert fact.metadata["step_end"] == 120
    assert "step" not in fact.metadata


# ---------------------------------------------------------------------------
# Unknown agent_id — skip + warn, never crash
# ---------------------------------------------------------------------------


def test_unknown_agent_in_trajectory_is_skipped(caplog):
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {
            "agent_0": {"steps_survived": 10, "resources_consumed": 0, "actions": {}},
            "ghost_agent": {
                "steps_survived": 5,
                "resources_consumed": 0,
                "actions": {},
            },
        },
        "episodes": [],
    }
    with caplog.at_level("WARNING"):
        facts = build_trajectory_facts(tracker, context)
    assert len(facts) == 1
    assert facts[0].metadata["agent_id"] == "agent_0"
    assert any("ghost_agent" in r.message for r in caplog.records)


def test_unknown_agent_in_episode_is_skipped(caplog):
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {"agent": "agent_0", "type": "starvation", "step": 50, "description": "x"},
            {"agent": "ghost", "type": "starvation", "step": 60, "description": "y"},
        ],
    }
    with caplog.at_level("WARNING"):
        facts, filtered = build_episode_facts(tracker, context)
    assert len(facts) == 1
    assert facts[0].metadata["agent_id"] == "agent_0"
    assert filtered == 0
    assert any("ghost" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Empty tracker
# ---------------------------------------------------------------------------


def test_empty_tracker_yields_no_facts():
    context = _context()
    tracker = {"summary": "", "trajectories": {}, "episodes": []}
    facts, filtered = build_all_facts(tracker, context)
    assert facts == []
    assert filtered == 0


def test_missing_keys_are_tolerated():
    context = _context()
    facts, filtered = build_all_facts({}, context)
    assert facts == []
    assert filtered == 0


# ---------------------------------------------------------------------------
# Spanish summary — preserved as raw quote inside English prefix
# ---------------------------------------------------------------------------


def test_spanish_summary_wrapped_in_english_prefix():
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "Los agentes exploraron la cuadrícula durante 200 pasos.",
        "trajectories": {},
        "episodes": [],
    }
    fact = build_summary_fact(tracker, context)
    assert fact is not None
    assert fact.text.startswith("Model HomeostaticDriveReductionRL")
    assert '"Los agentes exploraron' in fact.text


def test_empty_summary_returns_none():
    context = _context(agent_to_model={"agent_0": _model()})
    assert build_summary_fact({"summary": ""}, context) is None
    assert build_summary_fact({"summary": "   "}, context) is None
    assert build_summary_fact({}, context) is None


# ---------------------------------------------------------------------------
# Unknown episode type preserved with importance=6
# ---------------------------------------------------------------------------


def test_unknown_episode_type_preserved_with_default_importance():
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "",
        "trajectories": {},
        "episodes": [
            {
                "agent": "agent_0",
                "type": "sudden_cooperation",
                "step": 77,
                "description": "agents converged",
            }
        ],
    }
    facts, filtered = build_episode_facts(tracker, context)
    assert filtered == 0
    assert len(facts) == 1
    assert facts[0].importance == 6
    assert facts[0].metadata["episode_type"] == "sudden_cooperation"


# ---------------------------------------------------------------------------
# build_all_facts concatenation order
# ---------------------------------------------------------------------------


def test_build_all_facts_order_is_summary_trajectories_episodes():
    model = _model()
    context = _context(agent_to_model={"agent_0": model})
    tracker = {
        "summary": "s",
        "trajectories": {
            "agent_0": {"steps_survived": 1, "resources_consumed": 0, "actions": {}},
        },
        "episodes": [
            {"agent": "agent_0", "type": "starvation", "step": 1, "description": "x"},
        ],
    }
    facts, _ = build_all_facts(tracker, context)
    assert [f.memory_type for f in facts] == ["semantic", "semantic", "episodic"]
    assert facts[0].importance == 5  # summary
    assert facts[1].importance == 6  # trajectory
    assert facts[2].importance == 9  # starvation
