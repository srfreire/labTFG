"""Core extraction logic: dispatches to stage-specific prompts, calls Sonnet, parses JSON.

Switched to ``decisionlab.structured.call_structured`` (forced tool-use +
Pydantic) so a malformed model response now raises
``StructuredOutputError`` immediately. The pre-rewrite path silently
retried once and then crashed, which on cumulative-growth t1 voided the
whole topic without any actionable signal in the trace.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from decisionlab.config import SETTINGS
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec
from decisionlab.knowledge.prompts import (
    _CANONICAL,
    BUILDER_SYSTEM,
    BUILDER_USER,
    FORMALIZER_SYSTEM,
    FORMALIZER_USER,
    REASONER_SYSTEM,
    REASONER_USER,
    RESEARCHER_SYSTEM,
    RESEARCHER_USER,
)
from decisionlab.parsing import parse_formulation_headers
from decisionlab.structured import call_structured
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_MAX_TOKENS = int(os.getenv("DECISIONLAB_EXTRACTION_MAX_TOKENS", "16384"))

_STAGE_PROMPTS: dict[str, tuple[str, str]] = {
    "researcher": (RESEARCHER_SYSTEM, RESEARCHER_USER),
    "formalizer": (FORMALIZER_SYSTEM, FORMALIZER_USER),
    "reasoner": (REASONER_SYSTEM, REASONER_USER),
    "builder": (BUILDER_SYSTEM, BUILDER_USER),
}

# Per-stage extraction model tiering. Judgment-heavy stages (Researcher
# filters paradigm slugs across nested entities; Reasoner walks
# DERIVES_FROM chains) get the structured Sonnet slot; mechanical stages
# (Formalizer pulls from rigid tables, Builder extracts a single Model
# node) get the fast Haiku slot. Replaces a blanket Sonnet default that
# was 10× more expensive than the architecture doc claimed — see
# docs/specs/memory-refactor/phase-0-stop-lying.md §R1.
_STAGE_MODELS: dict[str, str] = {
    "researcher": SETTINGS.knowledge_structured_model,
    "formalizer": SETTINGS.knowledge_fast_model,
    "reasoner": SETTINGS.knowledge_structured_model,
    "builder": SETTINGS.knowledge_fast_model,
}

_TOP_LEVEL_MARKDOWN_RE = re.compile(r"(?m)(?=^#\s+)")


# Pydantic schemas mirror the pre-rewrite prompt JSON shape so the
# downstream ``_build_result`` parser still sees the same dict structure.
# ``properties`` stays ``dict[str, Any]`` on the wire, but slug-bearing
# labels (Paradigm/Variable/Postulate) get a typed sub-validator dispatched
# by ``_NodeRaw``'s ``model_validator`` — malformed slugs raise
# ``ValidationError`` (which ``call_structured`` translates to
# ``StructuredOutputError``). This is the gate that keeps minted-variant
# slugs like ``q-eligibility-traces`` out of the KG.

# Build the canonical-slug Literal at module import. ``Literal[tuple]``
# unpacks the tuple into the literal's args at runtime — Pydantic still
# validates membership the same way as a hand-written
# ``Literal["a", "b", ...]``. ``__NEW__`` is the LLM's "doesn't fit any of
# these" escape; routed through ``canonicalize.resolve_new_paradigm`` in
# MemoryAgent and Researcher (issue 1) before reaching the KG.
_CANONICAL_SLUGS: tuple[str, ...] = (
    *(p["slug"] for p in _CANONICAL),
    "__NEW__",
)
ParadigmSlug = Literal[_CANONICAL_SLUGS]  # type: ignore[valid-type]

# Postulate ids are scoped by their parent paradigm slug to prevent
# cross-paradigm collisions (e.g. RL's "P1" colliding with Prospect
# Theory's "P1"). The regex tolerates the ``__NEW__`` escape so that an
# extraction for an unknown paradigm still parses —
# ``canonicalize.canonicalize_extraction`` (issue 1) rewrites the prefix
# to the resolved canonical slug before the writer runs.
_POSTULATE_ID_RE = re.compile(r"^(__NEW__|[a-z0-9-]+):P\d+$")
_SHORT_POSTULATE_ID_RE = re.compile(r"^P\d+$")


class _ParadigmProps(BaseModel):
    slug: ParadigmSlug  # type: ignore[valid-type]
    name: str
    description: str = ""


class _VariableProps(BaseModel):
    name: str
    paradigm_slug: ParadigmSlug  # type: ignore[valid-type]
    description: str = ""
    type: str | None = None
    range: str | None = None
    unit: str | None = None


class _PostulateProps(BaseModel):
    id: str
    statement: str
    falsifiable: bool
    paradigm_slug: ParadigmSlug  # type: ignore[valid-type]

    @field_validator("id")
    @classmethod
    def _validate_id_prefix(cls, v: str) -> str:
        # Two gates: regex enforces shape (kebab + the ``__NEW__`` escape);
        # membership check enforces canonical-set vocabulary so
        # ``valid-shape-but-fabricated:P1`` is caught.
        m = _POSTULATE_ID_RE.match(v)
        if m is None:
            raise ValueError(
                f"Postulate.id must match '<paradigm-slug>:P<num>'; got {v!r}"
            )
        prefix = m.group(1)
        if prefix not in _CANONICAL_SLUGS:
            raise ValueError(
                f"Postulate.id prefix {prefix!r} is not a canonical paradigm slug"
            )
        return v


_LABEL_TO_PROPS: dict[str, type[BaseModel]] = {
    "Paradigm": _ParadigmProps,
    "Variable": _VariableProps,
    "Postulate": _PostulateProps,
}


class _Extraction(BaseModel):
    """Permissive envelope: nodes/relations stay as raw dicts so the LLM
    emitting one bad slug among many valid nodes doesn't void the whole
    batch. Per-label validation (``_LABEL_TO_PROPS``) is applied per-node
    in ``_build_result``, where invalid items are logged and skipped.
    """

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

    @field_validator("nodes", "relations", "facts", mode="before")
    @classmethod
    def _coerce_json_list_string(cls, value: Any) -> Any:
        """Accept tool payload fields accidentally emitted as JSON strings."""
        if not isinstance(value, str):
            return value

        text = value.strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            if start < 0:
                return value
            try:
                parsed, _end = json.JSONDecoder().raw_decode(text[start:])
            except json.JSONDecodeError:
                return value

        if isinstance(parsed, list):
            return parsed
        return value


async def extract(
    stage: str,
    output_text: str,
    run_id: str,
    client: AsyncAnthropic,
) -> ExtractionResult:
    """Extract entities, relations, and facts from a pipeline stage's output.

    Uses ``call_structured`` so the model is forced to emit JSON matching
    ``_Extraction``. Schema violation raises ``StructuredOutputError`` —
    callers decide whether to skip the stage or surface the failure.
    """
    if stage not in _STAGE_PROMPTS:
        raise ValueError(
            f"Unknown stage: {stage!r}. Expected one of {list(_STAGE_PROMPTS)}"
        )

    parts = _split_stage_output_for_extraction(stage, output_text)
    if len(parts) > 1:
        merged = ExtractionResult(
            nodes=[], relations=[], facts=[], stage=stage, run_id=run_id
        )
        logger.info(
            "extract[%s]: splitting stage output into %d structured calls",
            stage,
            len(parts),
        )
        for part in parts:
            part_result = await _extract_single(stage, part, run_id, client)
            _merge_result(merged, part_result)
        return merged

    return await _extract_single(stage, output_text, run_id, client)


async def _extract_single(
    stage: str,
    output_text: str,
    run_id: str,
    client: AsyncAnthropic,
) -> ExtractionResult:
    system_prompt, user_template = _STAGE_PROMPTS[stage]
    user_message = user_template.replace("{text}", output_text)

    parsed = await call_structured(
        client=client,
        messages=[{"role": "user", "content": user_message}],
        system=system_prompt,
        schema=_Extraction,
        max_tokens=_MAX_TOKENS,
        model=_STAGE_MODELS[stage],
    )
    return _build_result(parsed.model_dump(), stage, run_id, source_text=output_text)


def _split_stage_output_for_extraction(stage: str, output_text: str) -> list[str]:
    """Split naturally batched stage output before structured extraction."""
    text = output_text.strip()
    if not text:
        return []

    if stage == "formalizer":
        # Router concatenates one markdown file per paradigm. Extracting all
        # of them at once can exceed the structured output budget, so keep each
        # paradigm document as its own extraction call.
        parts = [p.strip() for p in _TOP_LEVEL_MARKDOWN_RE.split(text) if p.strip()]
        return parts or [text]

    if stage == "reasoner":
        objects = list(_iter_json_objects(text))
        if len(objects) > 1:
            return [json.dumps(obj, ensure_ascii=False) for obj in objects]

    return [text]


def _merge_result(target: ExtractionResult, source: ExtractionResult) -> None:
    """Merge a chunk-level extraction into a stage-level result."""
    node_keys: set[tuple[str, str, str]] = {
        (node.label, node.natural_key, str(node.properties.get(node.natural_key)))
        for node in target.nodes
    }
    for node in source.nodes:
        key = (node.label, node.natural_key, str(node.properties.get(node.natural_key)))
        if key in node_keys:
            for existing in target.nodes:
                if (
                    existing.label == key[0]
                    and existing.natural_key == key[1]
                    and str(existing.properties.get(existing.natural_key)) == key[2]
                ):
                    for prop_key, prop_value in node.properties.items():
                        existing.properties.setdefault(prop_key, prop_value)
                    break
            continue
        target.nodes.append(node)
        node_keys.add(key)

    relation_keys: set[tuple[str, str, str, str, str]] = {
        (
            rel.from_label,
            rel.from_key_value,
            rel.to_label,
            rel.to_key_value,
            rel.rel_type,
        )
        for rel in target.relations
    }
    for rel in source.relations:
        key = (
            rel.from_label,
            rel.from_key_value,
            rel.to_label,
            rel.to_key_value,
            rel.rel_type,
        )
        if key in relation_keys:
            continue
        target.relations.append(rel)
        relation_keys.add(key)

    seen_facts = set(target.facts)
    for fact in source.facts:
        if fact in seen_facts:
            continue
        target.facts.append(fact)
        seen_facts.add(fact)


_TEST_RESULT_PROPS = ("passed", "failure_reason")
_MISSING = object()


def _fold_legacy_test_results(raw_nodes: list) -> list:
    """Drop legacy ``TestResult`` nodes, merging their test props into matching Model nodes.

    Older Builder extractions emitted ``TestResult`` as a separate node. The current
    schema carries ``passed`` / ``failure_reason`` directly on ``Model``. This keeps
    old-format extractions usable: test props are copied onto the Model with the same
    ``formulation_id`` (when one exists), and the TestResult entry is discarded.
    """
    test_props_by_fid: dict[str, dict] = {}
    survivors: list = []
    for raw in raw_nodes:
        if isinstance(raw, dict) and raw.get("label") == "TestResult":
            properties = raw.get("properties")
            if isinstance(properties, dict):
                fid = properties.get("formulation_id")
                if fid is not None:
                    test_props_by_fid[str(fid)] = {
                        k: properties[k] for k in _TEST_RESULT_PROPS if k in properties
                    }
            continue
        survivors.append(raw)

    if not test_props_by_fid:
        return survivors

    matched_fids: set[str] = set()
    for raw in survivors:
        if not isinstance(raw, dict) or raw.get("label") != "Model":
            continue
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            continue
        fid = properties.get("formulation_id")
        if fid is None:
            continue
        fid_key = str(fid)
        fold = test_props_by_fid.get(fid_key)
        if not fold:
            continue
        matched_fids.add(fid_key)
        for prop_key, value in fold.items():
            existing = properties.get(prop_key, _MISSING)
            if existing is _MISSING:
                properties[prop_key] = value
            elif existing != value:
                logger.warning(
                    "Legacy TestResult conflicts with Model on formulation_id=%r "
                    "property=%r: keeping Model value %r (discarding %r)",
                    fid_key,
                    prop_key,
                    existing,
                    value,
                )

    orphans = set(test_props_by_fid) - matched_fids
    if orphans:
        logger.warning(
            "Legacy TestResult nodes without matching Model discarded for "
            "formulation_ids=%s",
            sorted(orphans),
        )
    return survivors


def _build_result(
    data: dict, stage: str, run_id: str, *, source_text: str = ""
) -> ExtractionResult:
    """Convert parsed JSON dict into an ExtractionResult with validated fields."""
    raw_nodes = _fold_legacy_test_results(data.get("nodes", []))
    if stage == "builder":
        raw_nodes = [
            raw
            for raw in raw_nodes
            if isinstance(raw, dict) and raw.get("label") == "Model"
        ]
    # Pre-pass: defensive paradigm_slug fill-in. The LLM regularly emits
    # a Variable inside a Paradigm batch without copying the slug down,
    # even though the prompt tells it to. We scan raw_nodes for the
    # batch's Paradigm slug, then patch Variables missing paradigm_slug
    # *before* per-node validation runs — otherwise the validation would
    # reject those Variables (paradigm_slug is required) and they'd be
    # dropped silently when a free fill-in would have saved them.
    paradigm_slug_for_batch: str | None = None
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        if raw.get("label") != "Paradigm":
            continue
        props = raw.get("properties")
        if not isinstance(props, dict):
            continue
        slug = props.get("slug")
        if isinstance(slug, str):
            paradigm_slug_for_batch = slug
            break
    if paradigm_slug_for_batch:
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                continue
            if raw.get("label") != "Variable":
                continue
            props = raw.get("properties")
            if not isinstance(props, dict):
                continue
            if not props.get("paradigm_slug"):
                props["paradigm_slug"] = paradigm_slug_for_batch

    nodes = []
    n_dropped_invalid = 0
    drop_reasons: list[str] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = raw.get("label")
        properties = raw.get("properties")
        natural_key = raw.get("natural_key")
        if not (label and isinstance(properties, dict) and natural_key):
            continue

        # Per-label property validation. Slug-bearing labels enforce the
        # canonical Literal here so a single bad node is dropped instead
        # of failing the whole list at parse time (see _Extraction).
        sub_model = _LABEL_TO_PROPS.get(str(label))
        if sub_model is not None:
            try:
                sub_model.model_validate(properties)
            except ValidationError as exc:
                n_dropped_invalid += 1
                drop_reasons.append(
                    f"{label}({properties.get('slug') or properties.get('name') or '?'}): "
                    f"{exc.error_count()} field error(s)"
                )
                continue

        nodes.append(
            NodeSpec(
                label=str(label),
                properties=properties,
                natural_key=str(natural_key),
            )
        )

    if n_dropped_invalid:
        logger.warning(
            "extract[%s]: dropped %d/%d nodes failing per-label validation: %s",
            stage,
            n_dropped_invalid,
            len(raw_nodes),
            "; ".join(drop_reasons[:5]) + (" ..." if len(drop_reasons) > 5 else ""),
        )

    relations = []
    for raw in data.get("relations", []):
        if not isinstance(raw, dict):
            continue
        if stage == "builder" and raw.get("rel_type") != "IMPLEMENTS":
            continue
        required = (
            "from_label",
            "from_key_value",
            "to_label",
            "to_key_value",
            "rel_type",
        )
        if all(raw.get(k) for k in required):
            relations.append(
                RelationSpec(
                    from_label=str(raw["from_label"]),
                    from_key_value=str(raw["from_key_value"]),
                    to_label=str(raw["to_label"]),
                    to_key_value=str(raw["to_key_value"]),
                    rel_type=str(raw["rel_type"]),
                    properties=raw.get("properties", {}),
                )
            )

    facts = []
    for raw in data.get("facts", []):
        if isinstance(raw, str) and raw.strip():
            facts.append(raw.strip())

    result = ExtractionResult(
        nodes=nodes,
        relations=relations,
        facts=facts,
        stage=stage,
        run_id=run_id,
    )
    if stage == "formalizer":
        _enrich_formalizer_markdown(result, source_text)
    if stage == "reasoner":
        _enrich_reasoner_formulation_paradigms(result, source_text)
        _enrich_reasoner_parameters(result, source_text)
        _scope_reasoner_postulate_refs(result, source_text)
    return result


def _iter_json_objects(text: str):
    """Yield JSON objects embedded in a concatenated stage-output string."""
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        if text[idx] != "{":
            idx += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            yield obj
        idx = end


def _upsert_node(
    nodes: list[NodeSpec],
    *,
    label: str,
    natural_key: str,
    key_value: str,
    properties: dict[str, Any],
) -> None:
    for node in nodes:
        if node.label == label and str(node.properties.get(natural_key)) == key_value:
            for prop_key, prop_value in properties.items():
                node.properties.setdefault(prop_key, prop_value)
            return
    nodes.append(NodeSpec(label=label, properties=properties, natural_key=natural_key))


def _relation_exists(
    relations: list[RelationSpec],
    *,
    from_label: str,
    from_key_value: str,
    to_label: str,
    to_key_value: str,
    rel_type: str,
) -> bool:
    return any(
        rel.from_label == from_label
        and rel.from_key_value == from_key_value
        and rel.to_label == to_label
        and rel.to_key_value == to_key_value
        and rel.rel_type == rel_type
        for rel in relations
    )


def _add_relation(
    relations: list[RelationSpec],
    *,
    from_label: str,
    from_key_value: str,
    to_label: str,
    to_key_value: str,
    rel_type: str,
    properties: dict[str, Any] | None = None,
) -> None:
    if _relation_exists(
        relations,
        from_label=from_label,
        from_key_value=from_key_value,
        to_label=to_label,
        to_key_value=to_key_value,
        rel_type=rel_type,
    ):
        return
    relations.append(
        RelationSpec(
            from_label=from_label,
            from_key_value=from_key_value,
            to_label=to_label,
            to_key_value=to_key_value,
            rel_type=rel_type,
            properties=properties or {},
        )
    )


_MATH_SYMBOL_REPLACEMENTS = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\varepsilon": "ε",
    r"\kappa": "κ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\omega": "ω",
    r"\phi": "φ",
    r"\psi": "ψ",
    r"\sigma": "σ",
}


def _clean_math_symbol(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.strip("$").strip()
    text = re.sub(r"\\text\{([^{}]+)\}", r"\1", text)
    text = re.sub(r"_\{([^{}]+)\}", r"_\1", text)
    text = re.sub(r"\^\{2\}|\^2", "²", text)
    for src, dst in _MATH_SYMBOL_REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = text.replace("\\bar{R}", "R_bar")
    text = text.replace("\\", "")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\s+", "", text)
    return text


def _extract_markdown_table(section: str, heading: str) -> list[dict[str, str]]:
    match = re.search(rf"(?mi)^###\s+{re.escape(heading)}\s*$", section)
    if match is None:
        return []
    body = section[match.end() :]
    next_heading = re.search(r"(?m)^###\s+", body)
    if next_heading is not None:
        body = body[: next_heading.start()]

    table_lines = [
        line.strip() for line in body.splitlines() if line.strip().startswith("|")
    ]
    if len(table_lines) < 2:
        return []

    header_cells = _table_cells(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = _table_cells(line)
        if len(cells) < len(header_cells):
            continue
        rows.append(dict(zip(header_cells, cells, strict=False)))
    return rows


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_formalizer_equations(section: str) -> list[tuple[str, str]]:
    match = re.search(r"(?mi)^###\s+Equations\s*$", section)
    if match is None:
        return []
    body = section[match.end() :]
    next_heading = re.search(r"(?m)^###\s+", body)
    if next_heading is not None:
        body = body[: next_heading.start()]

    equations: list[tuple[str, str]] = []
    for eq_match in re.finditer(r"`([^`]+)`\s*\n\$\$(.*?)\$\$", body, re.DOTALL):
        plaintext = eq_match.group(1).strip()
        latex = eq_match.group(2).strip()
        latex = re.sub(r"\s*\\tag\{[^{}]+\}\s*", "", latex).strip()
        if plaintext and latex:
            equations.append((plaintext, latex))
    return equations


def _infer_paradigm_slug(result: ExtractionResult, source_text: str) -> str | None:
    for node in result.nodes:
        slug = node.properties.get("paradigm_slug") or node.properties.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slugify(slug)

    lowered = source_text.lower()
    for item in _CANONICAL:
        slug = str(item.get("slug", ""))
        name = str(item.get("name", ""))
        if slug and slug in lowered:
            return slug
        if name and name.lower() in lowered:
            return slug

    first_line = next(
        (
            line.strip("# ").strip()
            for line in source_text.splitlines()
            if line.startswith("#")
        ),
        "",
    )
    if first_line:
        title = re.split(r"\s+[—-]\s+", first_line, maxsplit=1)[0]
        slug = slugify(title)
        return slug or None
    return None


def _enrich_formalizer_markdown(result: ExtractionResult, source_text: str) -> None:
    """Add deterministic formulation-local structure from markdown sections."""
    headers = parse_formulation_headers(source_text)
    if not headers:
        return

    paradigm_slug = _infer_paradigm_slug(result, source_text)
    id_by_local: dict[str, str] = {}
    for number, name, _start, _end in headers:
        formulation_id = slugify(name)
        id_by_local[f"Formulation {number}"] = formulation_id
        id_by_local[name] = formulation_id

    for node in result.nodes:
        if node.label != "Formulation":
            continue
        current_id = str(node.properties.get("id") or "")
        replacement = id_by_local.get(current_id)
        if replacement:
            node.properties["id"] = replacement
        if paradigm_slug:
            node.properties.setdefault("paradigm_slug", paradigm_slug)

    for rel in result.relations:
        if rel.from_label == "Formulation":
            rel.from_key_value = id_by_local.get(rel.from_key_value, rel.from_key_value)
        if rel.to_label == "Formulation":
            rel.to_key_value = id_by_local.get(rel.to_key_value, rel.to_key_value)

    for number, name, start, end in headers:
        formulation_id = slugify(name)
        section = source_text[start:end]
        _upsert_node(
            result.nodes,
            label="Formulation",
            natural_key="id",
            key_value=formulation_id,
            properties={
                "id": formulation_id,
                "name": name,
                "type": "formalizer_markdown",
                "description": "",
                "paradigm_slug": paradigm_slug or "",
            },
        )
        if paradigm_slug:
            _add_relation(
                result.relations,
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Paradigm",
                to_key_value=paradigm_slug,
                rel_type="BELONGS_TO",
            )

        parameter_aliases: dict[str, str] = {}
        for row in _extract_markdown_table(section, "Parameters"):
            symbol = _clean_math_symbol(row.get("Symbol"))
            if not symbol:
                continue
            display_name = row.get("Name", "").strip()
            parameter_aliases[display_name] = symbol
            parameter_aliases[symbol] = symbol
            _upsert_node(
                result.nodes,
                label="Parameter",
                natural_key="name",
                key_value=symbol,
                properties={
                    "name": symbol,
                    "display_name": display_name,
                    "default_value": row.get("Default", ""),
                    "source": row.get("Source", ""),
                    "range": row.get("Range", ""),
                    "paradigm_slug": paradigm_slug or "",
                    "formulation_id": formulation_id,
                },
            )
            _add_relation(
                result.relations,
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Parameter",
                to_key_value=symbol,
                rel_type="HAS_PARAMETER",
            )

        for node in result.nodes:
            if node.label != "Parameter":
                continue
            raw_name = str(node.properties.get("name") or "")
            if raw_name in parameter_aliases:
                node.properties.setdefault("display_name", raw_name)
                node.properties["name"] = parameter_aliases[raw_name]

        for row in _extract_markdown_table(section, "Variables"):
            symbol = _clean_math_symbol(row.get("Symbol"))
            if not symbol or not paradigm_slug:
                continue
            variable_name = f"{symbol} (Formulation {number})"
            _upsert_node(
                result.nodes,
                label="Variable",
                natural_key="name",
                key_value=variable_name,
                properties={
                    "name": variable_name,
                    "symbol": symbol,
                    "display_name": row.get("Name", ""),
                    "description": row.get("Description", ""),
                    "type": row.get("Type", ""),
                    "range": row.get("Range", ""),
                    "unit": row.get("Unit", ""),
                    "paradigm_slug": paradigm_slug,
                    "formulation_id": formulation_id,
                },
            )
            _add_relation(
                result.relations,
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Variable",
                to_key_value=variable_name,
                rel_type="USES_VARIABLE",
            )

        for plaintext, latex in _parse_formalizer_equations(section):
            _upsert_node(
                result.nodes,
                label="Equation",
                natural_key="latex",
                key_value=latex,
                properties={
                    "latex": latex,
                    "plaintext": plaintext,
                    "type": "algebraic",
                    "paradigm_slug": paradigm_slug or "",
                    "formulation_id": formulation_id,
                },
            )
            _add_relation(
                result.relations,
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Equation",
                to_key_value=latex,
                rel_type="USES_EQUATION",
            )


def _enrich_reasoner_parameters(result: ExtractionResult, source_text: str) -> None:
    """Normalize reasoner parameters to their symbolic identity."""
    alias_to_symbol: dict[str, str] = {}

    for spec in _iter_json_objects(source_text):
        formulation_id = spec.get("formulation_id")
        paradigm_slug = spec.get("paradigm")
        if not isinstance(formulation_id, str) or not formulation_id.strip():
            continue
        formulation_id = formulation_id.strip()
        paradigm_slug = str(paradigm_slug).strip() if paradigm_slug else ""

        params = spec.get("parameters")
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            symbol = _clean_math_symbol(param.get("symbol"))
            display_name = str(param.get("name") or "").strip()
            canonical = symbol or slugify(display_name)
            if not canonical:
                continue
            alias_to_symbol[canonical] = canonical
            if display_name:
                alias_to_symbol[display_name] = canonical
            if symbol:
                alias_to_symbol[symbol] = canonical

            _upsert_node(
                result.nodes,
                label="Parameter",
                natural_key="name",
                key_value=canonical,
                properties={
                    "name": canonical,
                    "symbol": symbol,
                    "display_name": display_name,
                    "default_value": param.get(
                        "default", param.get("default_value", "")
                    ),
                    "source": param.get("source", ""),
                    "range": param.get("range", ""),
                    "paradigm_slug": paradigm_slug,
                    "formulation_id": formulation_id,
                },
            )
            _add_relation(
                result.relations,
                from_label="Formulation",
                from_key_value=formulation_id,
                to_label="Parameter",
                to_key_value=canonical,
                rel_type="HAS_PARAMETER",
            )

    if not alias_to_symbol:
        return

    for node in result.nodes:
        if node.label != "Parameter":
            continue
        raw_name = str(node.properties.get("name") or "")
        canonical = alias_to_symbol.get(raw_name)
        if canonical is None:
            continue
        if raw_name != canonical:
            node.properties.setdefault("display_name", raw_name)
        node.properties["name"] = canonical

    for rel in result.relations:
        if rel.from_label == "Parameter":
            rel.from_key_value = alias_to_symbol.get(
                rel.from_key_value, rel.from_key_value
            )
        if rel.to_label == "Parameter":
            rel.to_key_value = alias_to_symbol.get(rel.to_key_value, rel.to_key_value)


def _enrich_reasoner_formulation_paradigms(
    result: ExtractionResult, source_text: str
) -> None:
    """Deterministically link reasoner Formulation nodes to their Paradigm.

    The reasoner JSON specs are the canonical source for the formulation IDs
    later implemented by Builder models. The LLM extractor may omit this graph
    edge, so add it from the raw JSON specs to guarantee:
    Model -[:IMPLEMENTS]-> Formulation -[:BELONGS_TO]-> Paradigm.
    """
    for spec in _iter_json_objects(source_text):
        formulation_id = spec.get("formulation_id")
        paradigm_slug = spec.get("paradigm")
        if not isinstance(formulation_id, str) or not formulation_id.strip():
            continue
        if not isinstance(paradigm_slug, str) or not paradigm_slug.strip():
            continue
        formulation_id = formulation_id.strip()
        paradigm_slug = paradigm_slug.strip()

        _upsert_node(
            result.nodes,
            label="Paradigm",
            natural_key="slug",
            key_value=paradigm_slug,
            properties={
                "slug": paradigm_slug,
                "name": paradigm_slug.replace("-", " ").title(),
                "description": "Paradigm referenced by a reasoner formulation spec.",
            },
        )
        _upsert_node(
            result.nodes,
            label="Formulation",
            natural_key="id",
            key_value=formulation_id,
            properties={
                "id": formulation_id,
                "name": spec.get("name") or formulation_id,
                "type": spec.get("status") or "reasoner_spec",
                "description": spec.get("description") or "",
                "paradigm_slug": paradigm_slug,
            },
        )

        if not _relation_exists(
            result.relations,
            from_label="Formulation",
            from_key_value=formulation_id,
            to_label="Paradigm",
            to_key_value=paradigm_slug,
            rel_type="BELONGS_TO",
        ):
            result.relations.append(
                RelationSpec(
                    from_label="Formulation",
                    from_key_value=formulation_id,
                    to_label="Paradigm",
                    to_key_value=paradigm_slug,
                    rel_type="BELONGS_TO",
                    properties={},
                )
            )


def _scope_reasoner_postulate_refs(result: ExtractionResult, source_text: str) -> None:
    """Rewrite reasoner ``P1``/``P2`` references to ``<paradigm>:P1``.

    Researcher extraction stores postulates with paradigm-scoped ids to avoid
    collisions. Reasoner specs often keep the shorter local ids in ``rules`` and
    parameter derivation chains; each reasoner JSON object has one top-level
    ``paradigm`` field, so we can safely scope local references before KG write.
    """
    paradigms = {
        str(spec.get("paradigm")).strip()
        for spec in _iter_json_objects(source_text)
        if isinstance(spec.get("paradigm"), str) and str(spec.get("paradigm")).strip()
    }
    if len(paradigms) != 1:
        return

    paradigm_slug = next(iter(paradigms))
    for rel in result.relations:
        if rel.to_label != "Postulate":
            continue
        if ":" in rel.to_key_value:
            continue
        if not _SHORT_POSTULATE_ID_RE.match(rel.to_key_value):
            continue
        rel.to_key_value = f"{paradigm_slug}:{rel.to_key_value}"
