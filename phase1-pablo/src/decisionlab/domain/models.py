from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class Paradigm:
    id: str
    name: str
    description: str


@dataclass
class ResearchReport:
    paradigms: list[Paradigm]
    summary: str
    deep_reports: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FormalizationReport:
    formulations: dict[str, str]  # paradigm_slug → markdown content


@dataclass(frozen=True)
class ReasonerReport:
    specs: dict[str, str]  # paradigm_slug → sub-agent text response


@dataclass(frozen=True)
class BuilderReport:
    results: dict[str, str]  # paradigm_slug → sub-agent text response
