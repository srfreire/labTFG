"""Eval harness for the decisionlab pipeline.

Three layers, top to bottom:

- ``decisionlab eval ...`` CLI subcommands (see ``decisionlab.cli_eval``).
- ``Suite`` runner that iterates topics from a YAML file and applies
  per-topic and suite-level assertions (see ``suite.py``).
- ``run_pipeline`` library function that drives a single topic through
  any prefix of [RESEARCH, FORMALIZE, REASON, BUILD] using
  ``AutoApproveFeedback`` and returns a ``PipelineRunResult`` (see
  ``runner.py``).

KG admin (stats / reset / snapshot / restore / query) lives in
``kgadmin.py`` and is reachable both as a library and via
``decisionlab kg ...``.
"""

from decisionlab.eval.kgadmin import KGStats, query, reset, restore, snapshot, stats
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.runner import run_pipeline

__all__ = [
    "KGStats",
    "PipelineRunResult",
    "query",
    "reset",
    "restore",
    "run_pipeline",
    "snapshot",
    "stats",
]
