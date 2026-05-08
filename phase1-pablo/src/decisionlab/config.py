"""Runtime configuration for agent stages and auxiliary model slots.

Pipeline stages override via ``DECISIONLAB_<STAGE>_{MODEL,MAX_ITERATIONS,MAX_TOKENS}``.

Knowledge-layer / feedback model slots are named by *role* (fast vs. structured),
not by family — swap any model id (Anthropic, OpenAI, Google via OpenRouter)
without renaming code.

Example:
    DECISIONLAB_BUILDER_MODEL=anthropic/claude-haiku-4.5
    DECISIONLAB_BUILDER_MAX_ITERATIONS=10
    DECISIONLAB_FORMALIZER_MODEL=anthropic/claude-sonnet-4.6
    DECISIONLAB_KNOWLEDGE_FAST_MODEL=anthropic/claude-haiku-4.5
    DECISIONLAB_KNOWLEDGE_STRUCTURED_MODEL=anthropic/claude-sonnet-4.6
    DECISIONLAB_FEEDBACK_MODEL=anthropic/claude-haiku-4.5
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    model: str
    max_iterations: int
    max_tokens: int


def _env(stage: str, field: str, default: str | int) -> str | int:
    raw = os.environ.get(f"DECISIONLAB_{stage}_{field}")
    if raw is None or raw == "":
        return default
    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(
                f"DECISIONLAB_{stage}_{field}={raw!r} is not a valid integer"
            ) from exc
    return raw


def _load(
    stage: str, *, model: str, max_iterations: int, max_tokens: int
) -> AgentConfig:
    return AgentConfig(
        model=str(_env(stage, "MODEL", model)),
        max_iterations=int(_env(stage, "MAX_ITERATIONS", max_iterations)),
        max_tokens=int(_env(stage, "MAX_TOKENS", max_tokens)),
    )


def _env_model(slot: str, default: str) -> str:
    raw = os.environ.get(f"DECISIONLAB_{slot}_MODEL")
    return raw if raw else default


@dataclass(frozen=True)
class Settings:
    researcher: AgentConfig
    deep_researcher: AgentConfig
    deep_researcher_summary: AgentConfig
    formalizer: AgentConfig
    reasoner: AgentConfig
    builder: AgentConfig
    # Auxiliary model slots — role-named so the family choice stays in env.
    # ``knowledge_fast_model`` (Haiku) for mechanical extraction / NER /
    # importance scoring / reflections; ``knowledge_structured_model``
    # (Sonnet) for judgment-heavy stages (Researcher, Reasoner) and conflict
    # resolution between memories.
    knowledge_fast_model: str
    knowledge_structured_model: str
    feedback_model: str  # feedback classifier (router re-execution decisions)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            researcher=_load(
                "RESEARCHER",
                model="anthropic/claude-sonnet-4.6",
                max_iterations=14,
                max_tokens=32768,
            ),
            deep_researcher=_load(
                "DEEP_RESEARCHER",
                model="anthropic/claude-sonnet-4.6",
                max_iterations=7,
                max_tokens=32768,
            ),
            deep_researcher_summary=_load(
                "DEEP_RESEARCHER_SUMMARY",
                model="anthropic/claude-haiku-4.5",
                max_iterations=1,
                max_tokens=300,
            ),
            formalizer=_load(
                "FORMALIZER",
                model="anthropic/claude-opus-4.6",
                max_iterations=5,
                max_tokens=32768,
            ),
            reasoner=_load(
                "REASONER",
                model="anthropic/claude-opus-4.6",
                max_iterations=5,
                max_tokens=16384,
            ),
            builder=_load(
                "BUILDER",
                model="anthropic/claude-sonnet-4.6",
                max_iterations=25,
                max_tokens=32768,
            ),
            knowledge_fast_model=_env_model(
                "KNOWLEDGE_FAST", "anthropic/claude-haiku-4.5"
            ),
            knowledge_structured_model=_env_model(
                "KNOWLEDGE_STRUCTURED", "anthropic/claude-sonnet-4.6"
            ),
            feedback_model=_env_model("FEEDBACK", "anthropic/claude-haiku-4.5"),
        )


SETTINGS = Settings.from_env()
