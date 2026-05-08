"""Two-pass canonicalize: when a Paradigm candidate cosine-matches
between τ_loose (0.78) and τ_direct (0.85), expand the candidate's
neighbours via EXTENDS|BELONGS_TO and re-test against ancestors. The
verifier sees the candidate vs the ancestor, not vs the loose neighbour.

Concrete failure mode being fixed: q-learning candidate cosine-matches
policy-gradient at 0.82 (between τ_loose 0.78 and τ_direct 0.85). Old
behaviour: skip — no merge happens, q-learning becomes its own node.
New behaviour: expand policy-gradient's parents → reinforcement-learning
sits at 0.91 cosine to q-learning → merge into reinforcement-learning."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_ancestor_expansion_merges_into_parent(monkeypatch):
    from decisionlab import canonicalize as c_mod
    from decisionlab.canonicalize import _MergeVerification
    from decisionlab.knowledge.models import ExtractionResult, NodeSpec

    # Each text gets a 3-d unit vector keyed by its substring; cosines (with
    # the calibrated Paradigm τ_direct=0.78, τ_loose=0.70):
    # q-learning vs policy-gradient = 0.74 (gray zone [0.70, 0.78))
    # q-learning vs reinforcement-learning = 0.91 (above τ_direct)
    def _vec(text: str):
        if "Q-learning" in text or "q-learning" in text:
            return [1.0, 0.0, 0.0]
        if "Policy Gradient" in text or "policy-gradient" in text:
            return [0.74, 0.6726, 0.0]  # cosine 0.74 with q-learning
        if "Reinforcement Learning" in text or "reinforcement-learning" in text:
            return [0.91, 0.4146, 0.0]  # cosine 0.91 with q-learning
        return [0.0, 0.0, 1.0]

    fake_emb = MagicMock()
    fake_emb.embed_texts = AsyncMock(side_effect=lambda texts: [_vec(t) for t in texts])

    # KG: only policy-gradient is directly in the existing nodes — RL is
    # reachable ONLY via ancestor expansion. This is the contract Pass 2
    # is designed to handle.
    fake_kg = MagicMock()
    fake_kg.unique_key_for = MagicMock(return_value="slug")
    fake_kg.query = AsyncMock(
        return_value=[
            {
                "slug": "policy-gradient",
                "name": "Policy Gradient",
                "description": "Direct policy optimisation",
                "_key": "policy-gradient",
            },
        ]
    )
    # Pass-2 ancestor expansion calls _fetch_ancestors which uses
    # kg.execute_query — return RL as the single ancestor of PG.
    fake_kg.execute_query = AsyncMock(
        return_value=[
            {
                "slug": "reinforcement-learning",
                "name": "Reinforcement Learning",
                "description": "Value-based action selection",
            }
        ]
    )

    async def fake_verify(*, label, candidate_text, existing_text, similarity, client):
        # Approve when verifying against the parent (RL), reject otherwise.
        approved = "reinforcement-learning" in existing_text or "Reinforcement" in existing_text
        return _MergeVerification(merge=approved, reason="ok")

    monkeypatch.setattr(c_mod, "_verify_merge", fake_verify)

    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "q-learning",
                    "name": "Q-learning",
                    "description": "Off-policy TD control",
                },
                natural_key="slug",
            )
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="r-test",
    )

    out = await c_mod.canonicalize(
        extraction,
        kg=fake_kg,
        embedding_service=fake_emb,
        client=object(),
    )

    surviving_slugs = {n.properties.get("slug") for n in out.nodes}
    assert "q-learning" not in surviving_slugs, (
        "q-learning should have been merged into reinforcement-learning via "
        "ancestor expansion"
    )
