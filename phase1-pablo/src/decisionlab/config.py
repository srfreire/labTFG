"""Runtime configuration for agent stages.

Defaults match the previously hardcoded values in each agent. Override any
knob via env var using the pattern ``DECISIONLAB_<STAGE>_{MODEL,MAX_ITERATIONS,MAX_TOKENS}``.

Example:
    DECISIONLAB_BUILDER_MODEL=claude-haiku-4-5
    DECISIONLAB_BUILDER_MAX_ITERATIONS=10
    DECISIONLAB_FORMALIZER_MODEL=claude-sonnet-4-6
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


def _load(stage: str, *, model: str, max_iterations: int, max_tokens: int) -> AgentConfig:
    return AgentConfig(
        model=str(_env(stage, "MODEL", model)),
        max_iterations=int(_env(stage, "MAX_ITERATIONS", max_iterations)),
        max_tokens=int(_env(stage, "MAX_TOKENS", max_tokens)),
    )


@dataclass(frozen=True)
class Settings:
    researcher: AgentConfig
    deep_researcher: AgentConfig
    deep_researcher_summary: AgentConfig
    formalizer: AgentConfig
    reasoner: AgentConfig
    builder: AgentConfig

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            researcher=_load(
                "RESEARCHER",
                model="claude-sonnet-4-6",
                max_iterations=10,
                max_tokens=4096,
            ),
            deep_researcher=_load(
                "DEEP_RESEARCHER",
                model="claude-sonnet-4-6",
                max_iterations=7,
                max_tokens=16384,
            ),
            deep_researcher_summary=_load(
                "DEEP_RESEARCHER_SUMMARY",
                model="claude-haiku-4-5",
                max_iterations=1,
                max_tokens=300,
            ),
            formalizer=_load(
                "FORMALIZER",
                model="claude-opus-4-6",
                max_iterations=5,
                max_tokens=16384,
            ),
            reasoner=_load(
                "REASONER",
                model="claude-opus-4-6",
                max_iterations=5,
                max_tokens=16384,
            ),
            builder=_load(
                "BUILDER",
                model="claude-sonnet-4-6",
                max_iterations=25,
                max_tokens=16384,
            ),
        )


SETTINGS = Settings.from_env()
