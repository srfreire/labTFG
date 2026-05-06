"""Canonicalize extracted entities against existing KG nodes.

Inserted between ``extract`` and ``populate_kg`` in the Memory Agent
pipeline. For every Paradigm / Variable / Postulate that the extraction
emits, the canonicalizer:

1. Embeds ``name + description`` (the most discriminative fields for
   each label) through Voyage.
2. Cosine-matches against existing same-label nodes' embeddings,
   computed on the fly from the same fields.
3. Above the cosine threshold (default τ=0.85, see plan §3) it asks
   Sonnet 4.6 to verify whether the candidate is genuinely the same
   entity as the canonical, with structured output enforcing a strict
   merge / keep-separate decision.
4. Approved merges remap relation endpoints to the canonical key and
   drop the duplicate node from the extraction so ``populate_kg`` only
   touches (extends ``run_ids``) the existing KG node.

Below threshold, or when verification rejects the merge, or when KG/
embedding infrastructure is unavailable, the extraction is returned
unchanged — degrades safely. Paper canonicalization stays DOI-keyed in
``kg_writer`` (Phase A), it doesn't go through this path.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.structured import (
    DEFAULT_MODEL as _STRUCTURED_MODEL,
)
from decisionlab.structured import (
    StructuredOutputError,
    call_structured,
)

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from decisionlab.feedback_port import FeedbackPort
    from shared.embedding import EmbeddingService
    from shared.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

CANONICALIZE_LABELS: tuple[str, ...] = ("Paradigm", "Variable", "Postulate")
DEFAULT_THRESHOLD: float = 0.85

# When the candidate text is shorter than this, defer entirely to the LLM
# verification step rather than trusting cosine — short strings amplify
# spurious similarity ("reward" vs. "reward signal" can cosine-match >0.95).
_MIN_TEXT_LENGTH_FOR_COSINE = 20

# Verification token budget — enough for a paragraph of justification
# without bloating cost.
_VERIFY_MAX_TOKENS = 1024


class _MergeVerification(BaseModel):
    merge: bool
    reason: str


@dataclass(frozen=True)
class _ExistingNode:
    key_value: str
    text: str
    properties: dict


_VERIFY_SYSTEM_PROMPT = """\
You decide whether two entities from a research knowledge graph are the same thing.

You receive:
- the LABEL (Paradigm / Variable / Postulate),
- a CANDIDATE entity newly proposed by the pipeline,
- an EXISTING entity already in the knowledge graph,
- the cosine similarity between their embeddings.

Decide:
- merge=true  iff they refer to the SAME concept (same paradigm under different
              names, the same variable expressed differently, the same postulate
              with rephrasing). Be strict for Paradigm — different paradigms
              that share a common ancestor (e.g. Q-learning vs. SARSA) are NOT
              the same paradigm; both are children of reinforcement-learning,
              and reinforcement-learning is what should canonicalize.
- merge=false iff they are genuinely distinct concepts that just happen to
              share vocabulary or notation.

Always include a one-sentence reason citing the specific feature that drove
your decision (e.g. "different update rules", "same author defining the same
construct under two names").
"""


async def canonicalize(
    extraction: ExtractionResult,
    *,
    kg: KnowledgeGraph | None,
    embedding_service: EmbeddingService | None,
    client: AsyncAnthropic,
    threshold: float = DEFAULT_THRESHOLD,
    feedback: FeedbackPort | None = None,
) -> ExtractionResult:
    """Resolve potential duplicates against existing KG nodes.

    Returns a (possibly rewritten) ``ExtractionResult`` with merged nodes
    dropped and relation endpoints rewritten. Always returns a result —
    failures degrade silently to "no canonicalization performed" so the
    pipeline can proceed even when KG/embedding services are unavailable.
    """
    if kg is None or embedding_service is None or not extraction.nodes:
        return extraction

    by_label: dict[str, list[NodeSpec]] = defaultdict(list)
    for node in extraction.nodes:
        if node.label in CANONICALIZE_LABELS:
            by_label[node.label].append(node)

    if not by_label:
        return extraction

    # remap[(label, original_key_value)] -> canonical_key_value
    remap: dict[tuple[str, str], str] = {}
    dropped_keys: set[tuple[str, str]] = set()

    for label, candidates in by_label.items():
        try:
            existing = await _fetch_existing_nodes(kg, label)
        except Exception as exc:
            logger.warning(
                "canonicalize: KG fetch failed for label=%s — skipping label: %s",
                label,
                exc,
            )
            continue
        if not existing:
            continue

        candidate_texts = [_node_to_text(n) for n in candidates]
        existing_texts = [e.text for e in existing]

        try:
            all_vecs = await embedding_service.embed_texts(
                candidate_texts + existing_texts
            )
        except Exception as exc:
            logger.warning(
                "canonicalize: embedding failed for label=%s — skipping label: %s",
                label,
                exc,
            )
            continue

        cand_vecs = all_vecs[: len(candidate_texts)]
        exist_vecs = all_vecs[len(candidate_texts) :]

        for i, candidate in enumerate(candidates):
            cand_text = candidate_texts[i]
            cand_vec = cand_vecs[i]

            best_score = -1.0
            best_idx = -1
            for j, exist_vec in enumerate(exist_vecs):
                sim = _cosine(cand_vec, exist_vec)
                if sim > best_score:
                    best_score = sim
                    best_idx = j

            if best_idx < 0 or best_score < threshold:
                continue
            if len(cand_text) < _MIN_TEXT_LENGTH_FOR_COSINE:
                # Short candidates can cosine-match by accident — defer to
                # the LLM verifier; if it also says no, we won't merge.
                pass

            target = existing[best_idx]
            try:
                decision = await _verify_merge(
                    label=label,
                    candidate_text=cand_text,
                    existing_text=target.text,
                    similarity=best_score,
                    client=client,
                )
            except StructuredOutputError as exc:
                logger.warning(
                    "canonicalize: verification failed for %s candidate — keeping separate: %s",
                    label,
                    exc,
                )
                continue

            if not decision.merge:
                logger.info(
                    "canonicalize: %s candidate kept separate (sim=%.3f, reason=%s)",
                    label,
                    best_score,
                    decision.reason,
                )
                continue

            cand_key_value = _candidate_key_value(candidate, kg)
            if cand_key_value is None:
                continue
            if str(cand_key_value) == str(target.key_value):
                continue  # already canonical

            if feedback is not None:
                approved = await _confirm_via_feedback(
                    feedback,
                    candidate=str(cand_key_value),
                    target=target.key_value,
                    similarity=best_score,
                    definition=target.text,
                )
                if not approved:
                    logger.info(
                        "canonicalize: human rejected merge %s -> %s",
                        cand_key_value,
                        target.key_value,
                    )
                    continue

            remap[(label, str(cand_key_value))] = target.key_value
            dropped_keys.add((label, str(cand_key_value)))
            logger.info(
                "canonicalize: %s '%s' -> '%s' (sim=%.3f)",
                label,
                cand_key_value,
                target.key_value,
                best_score,
            )

    if not remap:
        return extraction

    new_nodes: list[NodeSpec] = []
    for node in extraction.nodes:
        key_value = _candidate_key_value(node, kg)
        if (
            node.label in CANONICALIZE_LABELS
            and key_value is not None
            and (node.label, str(key_value)) in dropped_keys
        ):
            continue
        new_nodes.append(node)

    new_relations: list[RelationSpec] = []
    for rel in extraction.relations:
        from_remap = remap.get((rel.from_label, str(rel.from_key_value)))
        to_remap = remap.get((rel.to_label, str(rel.to_key_value)))
        new_relations.append(
            RelationSpec(
                from_label=rel.from_label,
                from_key_value=from_remap or rel.from_key_value,
                to_label=rel.to_label,
                to_key_value=to_remap or rel.to_key_value,
                rel_type=rel.rel_type,
                properties=rel.properties,
            )
        )

    return ExtractionResult(
        nodes=new_nodes,
        relations=new_relations,
        facts=extraction.facts,
        stage=extraction.stage,
        run_id=extraction.run_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_to_text(node: NodeSpec) -> str:
    """Build the text we embed for similarity comparison.

    Different labels emphasize different fields:
      - Paradigm: name + description
      - Variable: name + type + description (when present)
      - Postulate: statement (the only meaningful field)
    """
    props = node.properties
    if node.label == "Paradigm":
        name = str(props.get("name") or props.get("slug") or "")
        desc = str(props.get("description") or "")
        return f"{name}: {desc}".strip(": ").strip()
    if node.label == "Variable":
        name = str(props.get("name") or "")
        vtype = str(props.get("type") or "")
        desc = str(props.get("description") or "")
        parts = [name]
        if vtype:
            parts.append(f"({vtype})")
        if desc:
            parts.append(desc)
        return " ".join(parts).strip()
    if node.label == "Postulate":
        return str(props.get("statement") or props.get("id") or "")
    # Fallback for unhandled labels
    return str(props.get("name") or props.get("slug") or props.get("id") or "")


_LABEL_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "Paradigm": ("slug", "name", "description"),
    "Variable": ("name", "type", "description"),
    "Postulate": ("id", "statement"),
}


async def _fetch_existing_nodes(kg: KnowledgeGraph, label: str) -> list[_ExistingNode]:
    """Pull existing nodes' canonical key + text-for-embedding."""
    fields = _LABEL_KEY_FIELDS.get(label, ("name",))
    return_clause = ", ".join(f"n.{f} AS {f}" for f in fields)
    key = kg.unique_key_for(label)
    cypher = f"MATCH (n:{label}) RETURN {return_clause}, n.{key} AS _key"
    rows = await kg.query(cypher)
    out: list[_ExistingNode] = []
    for row in rows:
        key_value = row.get("_key")
        if key_value is None:
            continue
        # Build a synthetic NodeSpec view to reuse _node_to_text uniformly.
        synthetic = NodeSpec(
            label=label,
            properties={f: row.get(f) for f in fields if row.get(f) is not None},
            natural_key=key,
        )
        out.append(
            _ExistingNode(
                key_value=str(key_value),
                text=_node_to_text(synthetic),
                properties=dict(synthetic.properties),
            )
        )
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, no numpy. Returns 0 when either vector is degenerate."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _candidate_key_value(node: NodeSpec, kg: KnowledgeGraph | None) -> object | None:
    """Pick the same key the kg_writer's _resolve_natural_key would pick.

    Mirrors the precedence: schema unique key first, then declared
    natural_key, then common fallbacks. Avoids importing kg_writer to keep
    canonicalize a leaf module.
    """
    if kg is not None:
        try:
            schema_key = kg.unique_key_for(node.label)
        except (ValueError, AttributeError):
            schema_key = None
        if schema_key:
            v = node.properties.get(schema_key)
            if v is not None and v != "":
                return v
    declared = node.natural_key
    if declared:
        v = node.properties.get(declared)
        if v is not None:
            return v
    for fallback in ("slug", "id", "name", "title"):
        v = node.properties.get(fallback)
        if v is not None:
            return v
    return None


async def _verify_merge(
    *,
    label: str,
    candidate_text: str,
    existing_text: str,
    similarity: float,
    client: AsyncAnthropic,
) -> _MergeVerification:
    user_message = (
        f"LABEL: {label}\n"
        f"COSINE SIMILARITY: {similarity:.3f}\n\n"
        f"CANDIDATE:\n{candidate_text}\n\n"
        f"EXISTING:\n{existing_text}\n\n"
        "Decide whether to merge."
    )
    return await call_structured(
        client=client,
        messages=[{"role": "user", "content": user_message}],
        system=_VERIFY_SYSTEM_PROMPT,
        schema=_MergeVerification,
        max_tokens=_VERIFY_MAX_TOKENS,
        model=_STRUCTURED_MODEL,
    )


async def _confirm_via_feedback(
    feedback: FeedbackPort,
    *,
    candidate: str,
    target: str,
    similarity: float,
    definition: str,
) -> bool:
    """Route a merge decision to the FeedbackPort if the port supports it.

    Older ports (interactive CLI / Web) gain ``confirm_canonicalize_merge``
    in Phase D; the AutoApproveFeedback used by the eval harness implements
    it as ``return similarity >= threshold``. When a port doesn't define
    the method (e.g. a test stub), we auto-approve to preserve the
    eval-harness behaviour.
    """
    confirm = getattr(feedback, "confirm_canonicalize_merge", None)
    if confirm is None:
        return True
    return await confirm(
        candidate=candidate,
        target=target,
        similarity=similarity,
        definition=definition,
    )
