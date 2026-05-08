"""Calibrate canonicalize per-label thresholds against the
canonicalize-pairs.json fixture using cached cosine scores only —
no LLM calls. Emits a suggested LABEL_THRESHOLDS dict to stdout.

Usage:
    cd phase1-pablo
    uv run python scripts/calibrate_canonicalize_tau.py

The script:
  1. Loads canonicalize-pairs.json.
  2. Embeds all (candidate, existing) texts via shared.embeddings.
  3. For each label and each tau in [0.70, 0.95, 0.01]:
       - predict merge iff cosine >= tau
       - compute precision/recall/F1 vs labelled should_merge
  4. Pick tau that maximises F1; tie-break toward precision.
  5. Print the resulting dict in copy-pasteable form.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

import shared

load_dotenv()

FIXTURE = Path("evals/fixtures/canonicalize-pairs.json")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _pair_text(node: dict) -> str:
    """Render a candidate/existing entry as a single string for embedding.

    Handles both Paradigm/Variable shape (``name``/``description``) and
    Postulate shape (``id``/``statement``).
    """
    if isinstance(node, str):
        return node
    name = (node.get("name") or node.get("id") or "").strip()
    desc = (node.get("description") or node.get("statement") or "").strip()
    if name and desc:
        return f"{name}: {desc}"
    return name or desc or "(empty)"


async def main() -> None:
    raw = json.loads(FIXTURE.read_text())
    pairs = raw.get("pairs") if isinstance(raw, dict) else raw
    by_label: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_label[p["label"]].append(p)

    await shared.init()
    if shared.embeddings is None:
        await shared.shutdown()
        raise RuntimeError(
            "shared.embeddings not available — set VOYAGE_API_KEY in .env"
        )

    try:
        out: dict[str, tuple[float, float]] = {}
        for label, label_pairs in by_label.items():
            cand_texts = [_pair_text(p["candidate"]) for p in label_pairs]
            exist_texts = [_pair_text(p["existing"]) for p in label_pairs]
            cand_vecs = await shared.embeddings.embed_texts(cand_texts)
            exist_vecs = await shared.embeddings.embed_texts(exist_texts)
            cosines = [cosine(c, e) for c, e in zip(cand_vecs, exist_vecs, strict=True)]
            labels = [bool(p["should_merge"]) for p in label_pairs]

            best_tau = 0.85
            best_f1 = -1.0
            best_p = 0.0
            for tau_int in range(70, 96):
                tau = tau_int / 100.0
                tp = sum(1 for c, l in zip(cosines, labels, strict=True) if c >= tau and l)
                fp = sum(1 for c, l in zip(cosines, labels, strict=True) if c >= tau and not l)
                fn = sum(1 for c, l in zip(cosines, labels, strict=True) if c < tau and l)
                precision = tp / (tp + fp) if (tp + fp) else 0.0
                recall = tp / (tp + fn) if (tp + fn) else 0.0
                f1 = (
                    2 * precision * recall / (precision + recall)
                    if (precision + recall)
                    else 0.0
                )
                if f1 > best_f1 or (f1 == best_f1 and precision > best_p):
                    best_f1 = f1
                    best_p = precision
                    best_tau = tau
            # τ_loose for Paradigm is 0.07 below τ_direct (heuristic);
            # for other labels we keep direct == loose.
            if label == "Paradigm":
                out[label] = (round(best_tau, 2), round(max(0.70, best_tau - 0.07), 2))
            else:
                out[label] = (round(best_tau, 2), round(best_tau, 2))
            print(
                f"  {label:<10} τ_direct={best_tau:.2f} F1={best_f1:.3f} "
                f"(n={len(label_pairs)})"
            )
            print(f"    cosine range: {min(cosines):.3f}..{max(cosines):.3f}")

        print("\nSuggested LABEL_THRESHOLDS:")
        print("LABEL_THRESHOLDS = {")
        for k, v in sorted(out.items()):
            print(f"    {k!r:<12}: ({v[0]:.2f}, {v[1]:.2f}),")
        print("}")
    finally:
        await shared.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
