"""Resolve __NEW__ paradigm-slug escapes to canonical KG nodes.

When the LLM picks the ``__NEW__`` escape (Researcher emission or MemoryAgent
extraction), this module decides whether the proposed paradigm should:

- merge into an existing canonical Paradigm (when ANN + Sonnet verify-merge agree), or
- mint a fresh slug via ``slugify(name)``.

Paradigm-only for v2; Variable/Postulate self-canonicalization is deferred —
the architecture report §4.3 shows sub-1% within-paradigm fragmentation.

Two integration points share the same core ``resolve_new_paradigm`` helper:

1. ``Researcher._emit_structured`` — when the LLM emits ``slug="__NEW__"``,
   we ANN-search the KG before minting via ``slugify``. This fixes the
   ``slug_hit_rate`` eval metric, which reads from ``tr.run.paradigms``.
2. ``MemoryAgent.run`` — when extraction returns ``Paradigm`` nodes with
   ``slug="__NEW__"`` (or sibling ``Variable``/``Postulate`` with
   ``paradigm_slug="__NEW__"``), ``canonicalize_extraction`` rewrites
   the slug before populate_kg fires.

Falls back to ``slugify(name)`` on every infrastructure failure (KG,
embeddings, Sonnet) — never raises out of the public API.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.structured import (
    DEFAULT_MODEL as _STRUCTURED_MODEL,
)
from decisionlab.structured import (
    StructuredOutputError,
    call_structured,
)
from decisionlab.tools.reports import slugify
from shared.knowledge_graph import vector_index_name

logger = logging.getLogger(__name__)

# Sentinel emitted by both the constrained Researcher emission and the
# constrained extraction Pydantic Literal when the LLM cannot map a
# paradigm to any canonical slug.
CANONICAL_NEW = "__NEW__"

# Per-label cosine threshold for ANN candidate consideration.
# Above τ → Sonnet verify-merge gate. Below τ → mint without LLM call.
PARADIGM_THRESHOLD: float = 0.65

_ANN_TOP_K = 3
_VERIFY_MAX_TOKENS = 1024


class _MergeVerdict(BaseModel):
    decision: Literal["MERGE", "MINT_NEW"]
    canonical_slug: str | None = Field(
        default=None,
        description="Required iff decision=='MERGE'. Must equal one of the existing slugs verbatim.",
    )
    reasoning: str


_VERIFY_SYSTEM = """You decide whether a newly-proposed paradigm is the same as an existing one in a research knowledge graph.

You receive:
- a CANDIDATE paradigm (name + definition the LLM proposed),
- one or more EXISTING paradigms in the KG (slug + definition + cosine similarity).

Decide MERGE iff the candidate and one existing paradigm refer to the SAME umbrella concept.
Examples:
- "TD eligibility traces" candidate + "reinforcement-learning" existing → MERGE (TD is an RL variant under the same umbrella).
- "Predictive coding" candidate + "free-energy-principle" existing → MERGE (predictive coding is a mechanism under the FEP umbrella).
- "DDM with collapsing bounds" candidate + "drift-diffusion-model" existing → MERGE (mechanism variant of the same model).
- "SARSA" candidate + "Q-learning" existing → MINT_NEW (siblings under RL, not the same paradigm — RL is the umbrella that should canonicalize, not Q-learning).
- "Bounded rationality" candidate + "expected-utility-theory" existing → MINT_NEW (genuinely distinct paradigms).

When MERGE, you MUST set canonical_slug to the existing paradigm's slug verbatim.
When MINT_NEW, set canonical_slug=null and explain why none of the candidates match.
"""


async def resolve_new_paradigm(
    name: str,
    description: str,
    *,
    kg,
    embeddings,
    client,
    threshold: float = PARADIGM_THRESHOLD,
) -> str:
    """Return either an existing canonical slug (MERGE) or a freshly-slugified one.

    Used by both ``Researcher._emit_structured`` (for ``__NEW__`` emissions) and
    ``canonicalize_extraction`` (for ``ExtractionResult`` Paradigm nodes with
    ``slug=__NEW__``).

    Falls back to ``slugify(name)`` on any infrastructure failure
    (KG/embeddings/Sonnet). Never raises.
    """
    minted = slugify(name) if name and name.strip() else ""
    if not minted:
        # Caller should have filtered, but stay total: derive from description.
        if description and description.strip():
            digest = slugify(description)[:32]
            minted = f"unnamed-{digest}" if digest else "unnamed"
        else:
            minted = "unnamed"

    if kg is None or embeddings is None:
        return minted

    try:
        index_name = vector_index_name("Paradigm")
    except ValueError:
        return minted

    # Embed the definition alone — seed.py builds canonical Paradigm.embedding
    # from `definition` only (not "name: definition"), so matching that shape
    # keeps cosines on the same distribution. Fall back to name when the
    # candidate has no description.
    text = description.strip() if description and description.strip() else name.strip()
    if not text:
        return minted

    try:
        query_vec = await embeddings.embed_query(text)
        rows = await kg.query(
            "CALL db.index.vector.queryNodes($index_name, $k, $vector) "
            "YIELD node, score WHERE 'Paradigm' IN labels(node) "
            "RETURN node.slug AS slug, node.name AS name, "
            "node.description AS description, score "
            "ORDER BY score DESC",
            {"index_name": index_name, "k": _ANN_TOP_K, "vector": query_vec},
        )
    except Exception as exc:
        logger.warning(
            "canonicalize: ANN query failed for %r — minting %s: %s",
            name,
            minted,
            exc,
        )
        return minted

    candidates = [r for r in (rows or []) if float(r.get("score") or 0.0) >= threshold]
    if not candidates:
        logger.info(
            "canonicalize: no Paradigm above τ=%.2f for %r — minting %s",
            threshold,
            name,
            minted,
        )
        return minted

    try:
        verdict = await _verify_merge(name, description, candidates, client)
    except StructuredOutputError as exc:
        logger.warning(
            "canonicalize: verify-merge failed for %r — minting %s: %s",
            name,
            minted,
            exc,
        )
        return minted
    except Exception as exc:
        logger.warning(
            "canonicalize: verify-merge raised %s for %r — minting %s",
            type(exc).__name__,
            name,
            minted,
        )
        return minted

    if verdict.decision == "MERGE" and verdict.canonical_slug:
        canonical_slugs = {r["slug"] for r in candidates}
        if verdict.canonical_slug in canonical_slugs:
            logger.info(
                "canonicalize: %r → %s (verify-merge: %s)",
                name,
                verdict.canonical_slug,
                verdict.reasoning,
            )
            return verdict.canonical_slug
        logger.warning(
            "canonicalize: verify-merge picked %r not in candidates %s — minting %s",
            verdict.canonical_slug,
            canonical_slugs,
            minted,
        )

    return minted


async def _verify_merge(
    name: str,
    description: str,
    candidates: list[dict],
    client,
) -> _MergeVerdict:
    """Sonnet gate: are any of the ANN hits the same paradigm as the candidate?"""
    cand_block = f"CANDIDATE\nname: {name}\ndefinition: {description}"
    existing_block = "\n\n".join(
        f"EXISTING #{i + 1}\nslug: {r['slug']}\nname: {r.get('name', '')}\n"
        f"definition: {r.get('description', '')}\ncosine: {float(r.get('score') or 0):.3f}"
        for i, r in enumerate(candidates)
    )
    user = f"{cand_block}\n\n{existing_block}\n\nDecide MERGE or MINT_NEW."
    return await call_structured(
        client=client,
        messages=[{"role": "user", "content": user}],
        system=_VERIFY_SYSTEM,
        schema=_MergeVerdict,
        max_tokens=_VERIFY_MAX_TOKENS,
        model=_STRUCTURED_MODEL,
    )


# --- ExtractionResult-level wrapper used by MemoryAgent ----------------------


async def canonicalize_extraction(
    extraction: ExtractionResult,
    *,
    kg,
    embeddings,
    client,
) -> ExtractionResult:
    """Resolve ``__NEW__`` Paradigm slugs in an ``ExtractionResult``.

    Cheap-exit when no ``__NEW__`` appears. When a single ``__NEW__`` Paradigm
    exists, resolves to canonical or minted, then propagates to sibling
    ``Variable``/``Postulate`` nodes whose ``paradigm_slug == __NEW__`` and to
    ``Postulate.id`` prefixes, plus relation endpoints.

    Multi-``__NEW__`` is rare; mints each Paradigm independently (no Sonnet
    call) and leaves sibling ``paradigm_slug=__NEW__`` alone — those nodes
    will be dropped by per-label validation downstream, same outcome as today
    (no regression).
    """
    if not extraction.nodes:
        return extraction

    new_paradigms = [
        n
        for n in extraction.nodes
        if n.label == "Paradigm" and n.properties.get("slug") == CANONICAL_NEW
    ]
    has_new_variable_or_postulate = any(
        n.properties.get("paradigm_slug") == CANONICAL_NEW
        for n in extraction.nodes
        if n.label in ("Variable", "Postulate")
    )

    if not new_paradigms and not has_new_variable_or_postulate:
        return extraction

    if len(new_paradigms) > 1:
        logger.warning(
            "canonicalize_extraction: %d __NEW__ paradigms in batch — "
            "minting each, no Variable remap",
            len(new_paradigms),
        )
        for n in new_paradigms:
            minted = slugify(n.properties.get("name", "")) or "unnamed"
            n.properties["slug"] = minted
            if n.natural_key == CANONICAL_NEW:
                n.natural_key = minted
        return extraction

    if len(new_paradigms) == 1:
        p = new_paradigms[0]
        canonical = await resolve_new_paradigm(
            p.properties.get("name", ""),
            p.properties.get("description", ""),
            kg=kg,
            embeddings=embeddings,
            client=client,
        )
        p.properties["slug"] = canonical
        if p.natural_key == CANONICAL_NEW:
            p.natural_key = canonical
        return _remap_new_to_canonical(extraction, canonical)

    # No ``__NEW__`` Paradigm but Variables/Postulates carry
    # ``paradigm_slug=__NEW__``. Without a Paradigm in the batch we have no
    # name/definition to canonicalize against — leave them; per-label
    # validation downstream handles the orphans.
    logger.info(
        "canonicalize_extraction: __NEW__ paradigm_slug on Variables/Postulates "
        "with no parent Paradigm in batch — no remap (downstream validation drops)"
    )
    return extraction


def _remap_new_to_canonical(
    extraction: ExtractionResult, canonical: str
) -> ExtractionResult:
    """Rewrite sibling Variables/Postulates and relation endpoints in-place.

    The Paradigm itself is rewritten by the caller; this rewrites everything
    else that referenced ``__NEW__`` so the populate_kg writer sees a
    consistent batch.
    """
    new_nodes: list[NodeSpec] = []
    for n in extraction.nodes:
        if n.label == "Variable" and n.properties.get("paradigm_slug") == CANONICAL_NEW:
            n.properties["paradigm_slug"] = canonical
        elif n.label == "Postulate":
            if n.properties.get("paradigm_slug") == CANONICAL_NEW:
                n.properties["paradigm_slug"] = canonical
            pid = n.properties.get("id", "")
            if isinstance(pid, str) and pid.startswith(f"{CANONICAL_NEW}:"):
                new_id = canonical + pid[len(CANONICAL_NEW) :]
                n.properties["id"] = new_id
                if n.natural_key == pid:
                    n.natural_key = new_id
        new_nodes.append(n)

    new_relations: list[RelationSpec] = []
    for r in extraction.relations:
        from_kv = r.from_key_value
        to_kv = r.to_key_value
        if r.from_label == "Paradigm" and from_kv == CANONICAL_NEW:
            from_kv = canonical
        if r.to_label == "Paradigm" and to_kv == CANONICAL_NEW:
            to_kv = canonical
        if (
            r.from_label == "Postulate"
            and isinstance(from_kv, str)
            and from_kv.startswith(f"{CANONICAL_NEW}:")
        ):
            from_kv = canonical + from_kv[len(CANONICAL_NEW) :]
        if (
            r.to_label == "Postulate"
            and isinstance(to_kv, str)
            and to_kv.startswith(f"{CANONICAL_NEW}:")
        ):
            to_kv = canonical + to_kv[len(CANONICAL_NEW) :]
        if (from_kv, to_kv) != (r.from_key_value, r.to_key_value):
            new_relations.append(
                RelationSpec(
                    from_label=r.from_label,
                    from_key_value=from_kv,
                    to_label=r.to_label,
                    to_key_value=to_kv,
                    rel_type=r.rel_type,
                    properties=r.properties,
                )
            )
        else:
            new_relations.append(r)

    return ExtractionResult(
        nodes=new_nodes,
        relations=new_relations,
        facts=extraction.facts,
        stage=extraction.stage,
        run_id=extraction.run_id,
    )
