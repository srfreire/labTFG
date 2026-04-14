"""Typed, hierarchical ID registry for the T-P-F naming scheme."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IdRegistry:
    """Owns all programmatic IDs (topic → paradigm → formulation).

    Paradigms and formulations live in separate dicts with explicit
    structure — no flat-dict encoding conventions.
    """

    topic_id: str = "T01"
    _paradigms: dict[str, str] = field(default_factory=dict)       # slug → "P01"
    _formulations: dict[str, dict[str, str]] = field(default_factory=dict)  # slug → {name → "F01"}

    # -- assignment (idempotent) ---------------------------------------------

    def add_paradigm(self, slug: str) -> str:
        """Register a paradigm slug → ``T01-P01``. Idempotent."""
        if slug not in self._paradigms:
            self._paradigms[slug] = f"P{len(self._paradigms) + 1:02d}"
        return f"{self.topic_id}-{self._paradigms[slug]}"

    def add_formulation(self, slug: str, name: str) -> str:
        """Register a formulation → ``T01-P01-F01``. Idempotent."""
        pid = self._paradigms.get(slug)
        if pid is None:
            raise ValueError(
                f"Paradigm '{slug}' not in registry. "
                "Call add_paradigm first."
            )
        fmap = self._formulations.setdefault(slug, {})
        if name not in fmap:
            fmap[name] = f"F{len(fmap) + 1:02d}"
        return f"{self.topic_id}-{pid}-{fmap[name]}"

    # -- lookups -------------------------------------------------------------

    def paradigm_id(self, slug: str) -> str | None:
        """Full paradigm ID for a slug, or ``None``."""
        pid = self._paradigms.get(slug)
        return f"{self.topic_id}-{pid}" if pid else None

    def formulation_id(self, slug: str, name: str) -> str | None:
        """Full formulation ID, or ``None``."""
        pid = self._paradigms.get(slug)
        fid = self._formulations.get(slug, {}).get(name)
        if pid and fid:
            return f"{self.topic_id}-{pid}-{fid}"
        return None

    def slug_for_id(self, registry_id: str) -> str | None:
        """Reverse lookup: full ID → paradigm slug (or ``None``)."""
        for slug, pid in self._paradigms.items():
            if registry_id == f"{self.topic_id}-{pid}":
                return slug
            for _, fid in self._formulations.get(slug, {}).items():
                if registry_id == f"{self.topic_id}-{pid}-{fid}":
                    return slug
        return None

    # -- structured output ---------------------------------------------------

    def tree(self) -> dict[str, dict]:
        """Hierarchy for tree map rendering.

        Returns ``{slug: {"id": "T01-P01", "formulations": {name: "T01-P01-F01"}}}``,
        sorted by paradigm ID then formulation ID.
        """
        result: dict[str, dict] = {}
        for slug, pid in sorted(self._paradigms.items(), key=lambda x: x[1]):
            full_pid = f"{self.topic_id}-{pid}"
            fmap = self._formulations.get(slug, {})
            formulations = {
                name: f"{full_pid}-{fid}"
                for name, fid in sorted(fmap.items(), key=lambda x: x[1])
            }
            result[slug] = {"id": full_pid, "formulations": formulations}
        return result

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "paradigms": dict(self._paradigms),
            "formulations": {
                slug: dict(fmap)
                for slug, fmap in self._formulations.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> IdRegistry:
        return cls(
            topic_id=data.get("topic_id", "T01"),
            _paradigms=data.get("paradigms", {}),
            _formulations={
                slug: dict(fmap)
                for slug, fmap in data.get("formulations", {}).items()
            },
        )
