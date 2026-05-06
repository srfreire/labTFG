"""FeedbackPort — abstraction over how the pipeline asks for human input.

The Router has five review touch points (research, formalize, env_spec, reason,
build). Historically it branched on ``self._web_mode`` and inline-imported
either ``decisionlab.feedback`` (questionary CLI) or ``decisionlab.web_feedback``
(WebSocket). This module collapses that into a single ``FeedbackPort``
protocol with three implementations:

- ``CLIFeedback`` — wraps the questionary functions in ``feedback``.
- ``WebFeedback`` — wraps the WS functions in ``web_feedback``, capturing the
  ``emit`` callback at construction.
- ``AutoApproveFeedback`` — non-interactive: approves every discovered slug,
  returns no rejections or reruns. Used by the eval harness.

The ``CLIFeedback`` and ``WebFeedback`` adapters route through the underlying
modules with attribute access (``module.func(...)``) rather than ``from
module import func`` so existing tests that ``patch('decisionlab.feedback.
review_research', ...)`` continue to work.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]

# Type aliases for return shapes — match the existing feedback.py / web_feedback.py
# signatures exactly so swapping the port doesn't change call sites.
ReviewResearchResult = tuple[list[str], "str | None"]
ReviewFormalizeResult = dict[str, list[int]]
ReviewReasonResult = tuple[list[str], list[tuple[str, str, str]], list[str]]
ReviewBuildResult = tuple[list[str], list[tuple[str, str, str]], list[str]]


class FeedbackPort(Protocol):
    """How the Router asks for human input at each review stage."""

    async def review_research(
        self,
        reports_dir: Path,
        *,
        run_id: str,
    ) -> ReviewResearchResult: ...

    async def review_formalize(
        self,
        reports_dir: Path,
        paradigm_slugs: list[str],
        *,
        run_id: str,
    ) -> ReviewFormalizeResult: ...

    async def get_env_spec(self) -> Path: ...

    async def review_reason(self, reports_dir: Path) -> ReviewReasonResult: ...

    async def review_build(
        self,
        reports_dir: Path,
        build_results: dict[str, str],
    ) -> ReviewBuildResult: ...

    async def confirm_canonicalize_merge(
        self,
        *,
        candidate: str,
        target: str,
        similarity: float,
        definition: str,
    ) -> bool:
        """Approve or reject merging *candidate* into the existing *target*.

        Called by the Canonicalizer (Phase D) when cosine similarity ≥ τ
        and the LLM verifier said merge=true. Implementations:

          - ``AutoApproveFeedback`` (eval harness): returns ``True`` when
            similarity is at or above the threshold. Default τ surfaces
            here for symmetry with the canonicalizer's own threshold.
          - ``CLIFeedback``: questionary-prompts the user with the two
            entities, similarity score, and the existing definition.
          - ``WebFeedback``: emits a ``confirm_canonicalize_merge`` event
            to the WS client and awaits the response.

        Returning ``False`` keeps the candidate as a fresh KG node.
        """
        ...


# ---------------------------------------------------------------------------
# CLIFeedback — questionary prompts
# ---------------------------------------------------------------------------


class CLIFeedback:
    """Interactive feedback via questionary prompts. Default for ``decisionlab run``."""

    async def review_research(
        self,
        reports_dir: Path,
        *,
        run_id: str,
    ) -> ReviewResearchResult:
        from decisionlab import feedback

        return await feedback.review_research(reports_dir)

    async def review_formalize(
        self,
        reports_dir: Path,
        paradigm_slugs: list[str],
        *,
        run_id: str,
    ) -> ReviewFormalizeResult:
        from decisionlab import feedback

        return await feedback.review_formalize(
            reports_dir, paradigm_slugs, run_id=run_id
        )

    async def get_env_spec(self) -> Path:
        from decisionlab import feedback

        return await feedback.get_env_spec()

    async def review_reason(self, reports_dir: Path) -> ReviewReasonResult:
        from decisionlab import feedback

        return await feedback.review_reason(reports_dir)

    async def review_build(
        self,
        reports_dir: Path,
        build_results: dict[str, str],
    ) -> ReviewBuildResult:
        from decisionlab import feedback

        return await feedback.review_build(reports_dir, build_results)

    async def confirm_canonicalize_merge(
        self,
        *,
        candidate: str,
        target: str,
        similarity: float,
        definition: str,
    ) -> bool:
        # Lazy import keeps decisionlab.feedback (questionary) optional.
        try:
            from decisionlab import feedback
        except ImportError:
            logger.warning(
                "CLIFeedback: questionary unavailable — auto-approving merge"
            )
            return True
        confirm = getattr(feedback, "confirm_canonicalize_merge", None)
        if confirm is None:
            return True
        return await confirm(
            candidate=candidate,
            target=target,
            similarity=similarity,
            definition=definition,
        )


# ---------------------------------------------------------------------------
# WebFeedback — WebSocket prompts via emit
# ---------------------------------------------------------------------------


class WebFeedback:
    """WebSocket-based feedback. Wraps the existing ``web_feedback`` module."""

    def __init__(self, emit: EmitFn) -> None:
        self._emit = emit

    async def review_research(
        self,
        reports_dir: Path,
        *,
        run_id: str,
    ) -> ReviewResearchResult:
        from decisionlab import web_feedback

        return await web_feedback.review_research(reports_dir, self._emit)

    async def review_formalize(
        self,
        reports_dir: Path,
        paradigm_slugs: list[str],
        *,
        run_id: str,
    ) -> ReviewFormalizeResult:
        from decisionlab import web_feedback

        return await web_feedback.review_formalize(
            reports_dir, paradigm_slugs, self._emit, run_id=run_id
        )

    async def get_env_spec(self) -> Path:
        from decisionlab import web_feedback

        return await web_feedback.get_env_spec(self._emit)

    async def review_reason(self, reports_dir: Path) -> ReviewReasonResult:
        from decisionlab import web_feedback

        return await web_feedback.review_reason(reports_dir, self._emit)

    async def review_build(
        self,
        reports_dir: Path,
        build_results: dict[str, str],
    ) -> ReviewBuildResult:
        from decisionlab import web_feedback

        return await web_feedback.review_build(reports_dir, build_results, self._emit)

    async def confirm_canonicalize_merge(
        self,
        *,
        candidate: str,
        target: str,
        similarity: float,
        definition: str,
    ) -> bool:
        try:
            from decisionlab import web_feedback
        except ImportError:
            return True
        confirm = getattr(web_feedback, "confirm_canonicalize_merge", None)
        if confirm is None:
            # Web layer hasn't shipped the prompt yet — auto-approve so
            # canonicalization doesn't silently disable.
            return True
        return await confirm(
            candidate=candidate,
            target=target,
            similarity=similarity,
            definition=definition,
            emit=self._emit,
        )


# ---------------------------------------------------------------------------
# AutoApproveFeedback — non-interactive, used by eval harness
# ---------------------------------------------------------------------------


class AutoApproveFeedback:
    """Non-interactive feedback that approves every discovered artifact.

    Behavior at each stage:

    - ``review_research`` — returns all paradigm slugs found in
      ``reports_dir/deep/*.md``, no follow-up paradigms.
    - ``review_formalize`` — keeps every formulation number parsed from each
      paradigm's S3 formulation file (no S3 rewrite — full content preserved).
    - ``get_env_spec`` — returns the ``env_spec_path`` provided at
      construction. Raises ``RuntimeError`` if missing and called.
    - ``review_reason`` — approves every reasoner spec whose ``status`` is not
      ``"invalid"``. No rejections, no formalizer reruns.
    - ``review_build`` — empty-tuple return: the Router ignores the ``approved``
      list (it reads ``state.approved_specs`` directly), so we just signal "no
      rejections, no reasoner reruns" and let it advance to ``DONE``.

    Designed to fail loudly rather than silently when something genuinely
    blocks: e.g. requesting ``get_env_spec`` without a configured path.
    """

    def __init__(self, *, env_spec_path: Path | None = None) -> None:
        self._env_spec_path = env_spec_path

    async def review_research(
        self,
        reports_dir: Path,
        *,
        run_id: str,
    ) -> ReviewResearchResult:
        """Discover paradigm slugs from S3 (where the real pipeline writes
        them via ``save_deep_report``) with a local-disk fallback.

        Real pipeline runs persist ``deep/{slug}.md`` to S3 under the run's
        ``research/{run_id}/`` prefix. The original CLIFeedback inspects the
        local ``reports_dir/deep/`` instead — that path is empty in
        production runs but matches sample fixtures and other tests, so we
        try local first and fall back to S3 only when local has nothing.
        """
        deep_dir = reports_dir / "deep"
        if deep_dir.is_dir():
            local_slugs = sorted(p.stem for p in deep_dir.glob("*.md"))
            if local_slugs:
                return local_slugs, None

        try:
            import shared

            if shared.storage is None:
                raise RuntimeError("shared.storage not initialised")
            keys = await shared.storage.list(f"research/{run_id}/deep/")
            slugs = sorted(Path(k).stem for k in keys if k.endswith(".md"))
            return slugs, None
        except Exception as exc:
            logger.warning(
                "AutoApproveFeedback.review_research: S3 listing failed (%s) "
                "and %s missing — approving 0 paradigms",
                exc,
                deep_dir,
            )
            return [], None

    async def review_formalize(
        self,
        reports_dir: Path,
        paradigm_slugs: list[str],
        *,
        run_id: str,
    ) -> ReviewFormalizeResult:
        import shared
        from decisionlab.parsing import parse_formulation_headers

        result: dict[str, list[int]] = {}
        for slug in paradigm_slugs:
            key = f"research/{run_id}/formulations/{slug}.md"
            try:
                text = await shared.storage.get_text(key)
            except Exception:
                logger.warning(
                    "AutoApproveFeedback.review_formalize: %s unreadable — skipping",
                    key,
                )
                result[slug] = []
                continue
            headers = parse_formulation_headers(text)
            result[slug] = [h[0] for h in headers]
        return result

    async def get_env_spec(self) -> Path:
        if self._env_spec_path is None:
            raise RuntimeError(
                "AutoApproveFeedback: get_env_spec called without env_spec_path. "
                "Pass env_spec_path=<file> when constructing AutoApproveFeedback "
                "if your eval includes the REASON or BUILD stages."
            )
        path = self._env_spec_path
        if not path.exists():
            raise FileNotFoundError(f"env_spec_path does not exist: {path}")
        # Validate JSON eagerly so the failure happens here, not deep in REASON.
        try:
            json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"env_spec at {path} is not valid JSON: {exc}") from exc
        return path

    async def review_reason(self, reports_dir: Path) -> ReviewReasonResult:
        reasoner_dir = reports_dir / "reasoner"
        approved: list[str] = []
        if not reasoner_dir.is_dir():
            return approved, [], []
        for spec_file in sorted(reasoner_dir.glob("*.json")):
            try:
                data = json.loads(spec_file.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    "AutoApproveFeedback.review_reason: unreadable spec %s — skipping",
                    spec_file,
                )
                continue
            if data.get("status") == "invalid":
                continue
            approved.append(data.get("formulation_id", spec_file.stem))
        return approved, [], []

    async def review_build(
        self,
        reports_dir: Path,
        build_results: dict[str, str],
    ) -> ReviewBuildResult:
        # Router only consults rejections/reasoner_reruns — `approved` is unused.
        # Returning ([], [], []) lets the loop advance straight to DONE.
        return [], [], []

    async def confirm_canonicalize_merge(
        self,
        *,
        candidate: str,
        target: str,
        similarity: float,
        definition: str,
    ) -> bool:
        # Eval-harness contract: trust the LLM verifier when similarity is
        # at or above the canonicalizer's threshold. The canonicalizer
        # only reaches this method when the cosine score already crossed
        # τ AND the LLM verifier said merge=true, so a flat ``True`` here
        # is the safe default. Override the threshold by subclassing if
        # the eval needs stricter dedup.
        from decisionlab.canonicalize import DEFAULT_THRESHOLD

        return similarity >= DEFAULT_THRESHOLD
