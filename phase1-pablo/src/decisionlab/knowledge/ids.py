"""Canonical KG identity helpers.

Pipeline artifacts use local IDs for file paths and user-facing names. Neo4j
needs globally unique IDs because constraints are label-wide. This module is
the boundary between those two worlds.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from decisionlab.knowledge.models import ExtractionResult, RelationSpec
from decisionlab.tools.reports import slugify

_GENERIC_FORMULATION_RE = re.compile(r"(?i)^formulation\s+\d+$")
_FORMULATION_SUFFIX_RE = re.compile(r"(?i)\s*\(formulation\s+\d+\)\s*$")
_SCOPED_ID_RE = re.compile(r"^(?P<scope>[a-z0-9-]+):(?P<local>[a-z0-9][a-z0-9-]*)$")

_SYMBOL_REPLACEMENTS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ω": "omega",
    "φ": "phi",
    "ψ": "psi",
    "σ": "sigma",
    "τ": "tau",
    "θ": "theta",
    "²": "2",
}

_CANONICAL_KEYS: dict[str, str] = {
    "Paradigm": "slug",
    "Variable": "id",
    "Equation": "latex",
    "BrainRegion": "name",
    "Author": "name",
    "Paper": "doi",
    "Postulate": "id",
    "Formulation": "id",
    "Parameter": "id",
    "Model": "formulation_id",
    "Reflection": "id",
    "RollupReflection": "id",
}

_SCOPED_LABELS = {
    "Formulation",
    "Variable",
    "Parameter",
    "Equation",
    "Model",
    "Postulate",
}


def component_id(value: object) -> str:
    """Readable stable component for scoped KG IDs."""
    text = str(value or "").strip()
    if not text:
        return ""
    for src, dst in _SYMBOL_REPLACEMENTS.items():
        text = text.replace(src, dst)
    slug = slugify(text)
    if slug:
        return slug
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"h-{digest}"


def canonical_key_for_label(label: str) -> str | None:
    """Return the canonical identity property for a KG label."""
    return _CANONICAL_KEYS.get(label)


def canonical_endpoint_key_for_value(label: str, value: object) -> str | None:
    """Return an endpoint key only when the value already looks canonical.

    Bare display aliases such as ``reward`` must keep flowing through writer
    alias resolution. Forcing them to match ``Variable.id`` would make valid
    generated relations fail after normalization.
    """
    key = canonical_key_for_label(label)
    if key is None:
        return None
    text = str(value or "").strip()
    if not text:
        return None
    if label == "Paradigm":
        return "slug"
    if label in {"Formulation", "Variable", "Parameter", "Postulate", "Model"}:
        return key if ":" in text else None
    if label == "Equation":
        return None
    if label == "Paper":
        return "doi" if "/" in text else None
    return key


def approved_formulation_aliases(
    approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]] | None,
) -> dict[str, str]:
    """Return aliases that resolve approved formulation refs to scoped IDs.

    Approved specs are the pipeline's ground truth after review. If a local
    formulation id is approved under exactly one paradigm, every occurrence of
    that local id should resolve to the reviewed scoped id, even if an LLM later
    emits the wrong paradigm prefix.
    """
    if not approved_specs:
        return {}

    alias_targets: dict[str, set[str]] = defaultdict(set)
    direct: dict[str, str] = {}
    for paradigm, raw_ids in approved_specs.items():
        scope = slugify(paradigm)
        if not scope:
            continue
        for raw_id in raw_ids or []:
            local = local_formulation_id(raw_id)
            if not local:
                continue
            scoped = f"{scope}:{local}"
            direct[scoped] = scoped
            for alias in {str(raw_id), local, component_id(raw_id), scoped}:
                if alias:
                    alias_targets[alias].add(scoped)

    aliases = {
        alias: next(iter(targets))
        for alias, targets in alias_targets.items()
        if len(targets) == 1
    }
    aliases.update(direct)
    return aliases


def align_to_approved_formulations(
    extraction: ExtractionResult,
    *,
    approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]] | None = None,
) -> ExtractionResult:
    """Rewrite formulation references through the reviewed formulation registry."""
    aliases = approved_formulation_aliases(approved_specs)
    if not aliases:
        return extraction

    def resolve_formulation(raw: object, *, name: object | None = None) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        if text in aliases:
            return aliases[text]
        _scope, local = split_scoped_id(text)
        if local in aliases:
            return aliases[local]
        derived = local_formulation_id(text, name=name)
        if derived in aliases:
            return aliases[derived]
        return text

    def apply_formulation_props(props: dict, *, key: str, name: object | None = None):
        raw = props.get(key)
        resolved = resolve_formulation(raw, name=name)
        if not resolved:
            return
        scope, local = split_scoped_id(resolved)
        props[key] = resolved
        if scope:
            props["paradigm_slug"] = scope
        if key == "id":
            props["local_id"] = local
        else:
            props["local_formulation_id"] = local

    for node in extraction.nodes:
        props = node.properties
        if node.label == "Formulation":
            apply_formulation_props(props, key="id", name=props.get("name"))
            node.natural_key = "id"
        elif node.label in {"Equation", "Variable", "Parameter", "Model"}:
            apply_formulation_props(props, key="formulation_id")
            if node.label == "Model":
                node.natural_key = "formulation_id"

    for rel in extraction.relations:
        if rel.from_label in {"Formulation", "Model"}:
            rel.from_key_value = (
                resolve_formulation(rel.from_key_value) or rel.from_key_value
            )
        elif rel.from_label in {"Variable", "Parameter"}:
            rel.from_key_value = _rewrite_formulation_scoped_child(
                rel.from_key_value, resolve_formulation
            )

        if rel.to_label == "Formulation":
            rel.to_key_value = resolve_formulation(rel.to_key_value) or rel.to_key_value
        elif rel.to_label in {"Variable", "Parameter"}:
            rel.to_key_value = _rewrite_formulation_scoped_child(
                rel.to_key_value, resolve_formulation
            )

    return extraction


def local_formulation_id(raw_id: object, *, name: object | None = None) -> str:
    """Return the local formulation slug, replacing generic placeholders."""
    raw = str(raw_id or "").strip()
    raw_slug = component_id(raw)
    name_slug = component_id(name) if name else ""
    if not raw_slug:
        return name_slug
    if _GENERIC_FORMULATION_RE.match(raw) and name_slug:
        return name_slug
    return raw_slug or name_slug


def split_scoped_id(value: object) -> tuple[str | None, str]:
    """Return ``(scope, local)`` for ``scope:local`` or ``(None, local)``."""
    text = str(value or "").strip()
    match = _SCOPED_ID_RE.match(text)
    if match:
        return match.group("scope"), match.group("local")
    return None, component_id(text)


def scoped_formulation_id(
    raw_id: object,
    *,
    paradigm_slug: object | None = None,
    name: object | None = None,
) -> tuple[str, str]:
    """Return ``(global_id, local_id)`` for a Formulation/Model endpoint."""
    existing_scope, local = split_scoped_id(raw_id)
    if not local:
        local = local_formulation_id(raw_id, name=name)
    if not local:
        return "", ""
    scope = slugify(str(paradigm_slug or existing_scope or "").strip()) or "orphan"
    return f"{scope}:{local}", local


def scoped_parameter_id(
    name: object,
    *,
    formulation_id: object | None = None,
    paradigm_slug: object | None = None,
) -> str:
    """Return the globally unique Parameter node id."""
    if formulation_id:
        formulation_global, _local = scoped_formulation_id(
            formulation_id,
            paradigm_slug=paradigm_slug,
        )
    else:
        formulation_global = "orphan"
    symbol = component_id(_FORMULATION_SUFFIX_RE.sub("", str(name or "").strip()))
    if not symbol:
        return ""
    return f"{formulation_global}:{symbol}"


def scoped_variable_id(
    name: object,
    *,
    paradigm_slug: object | None = None,
    formulation_id: object | None = None,
) -> str:
    """Return the globally unique Variable node id.

    Variables are paradigm-level concepts. Formulation-specific usage is
    represented by Formulation -> Variable edges, not by cloning the variable
    under every formulation.
    """
    raw_name = _FORMULATION_SUFFIX_RE.sub("", str(name or "").strip())
    symbol = component_id(raw_name)
    if not symbol:
        return ""

    scope = slugify(str(paradigm_slug or "").strip())
    if not scope and formulation_id:
        scope = split_scoped_id(formulation_id)[0] or ""
    if not scope:
        scope = "orphan"
    return f"{scope}:{symbol}"


def _rewrite_formulation_scoped_child(raw: object, resolve_formulation) -> str:
    text = str(raw or "").strip()
    if ":" not in text:
        return text
    parts = text.split(":")
    if len(parts) == 2:
        target = resolve_formulation(parts[0])
        return f"{target}:{parts[1]}" if target and target != parts[0] else text
    current_formulation = f"{parts[0]}:{parts[1]}"
    target = resolve_formulation(current_formulation)
    if target and target != current_formulation:
        return ":".join([target, *parts[2:]])
    return text


def normalize_extraction_ids(extraction: ExtractionResult) -> ExtractionResult:
    """Normalize node IDs and relation endpoints in-place.

    The function is intentionally deterministic and LLM-free. It converts local
    IDs to globally unique KG IDs while preserving the local value in
    ``local_id`` / ``local_formulation_id`` properties.
    """
    paradigm_scope = _batch_paradigm_scope(extraction)
    formulation_aliases: dict[str, str] = {}

    for node in extraction.nodes:
        if node.label != "Formulation":
            continue
        props = node.properties
        raw_id = props.get("id") or props.get("formulation_id") or props.get("name")
        scope = props.get("paradigm_slug") or paradigm_scope
        global_id, local_id = scoped_formulation_id(
            raw_id,
            paradigm_slug=scope,
            name=props.get("name"),
        )
        if not global_id:
            continue
        _register_aliases(
            formulation_aliases,
            global_id,
            raw_id,
            local_id,
            props.get("name"),
        )
        props["id"] = global_id
        props["local_id"] = local_id
        if scope:
            props["paradigm_slug"] = slugify(str(scope))
        node.natural_key = "id"

    unique_formulation_ids = set(formulation_aliases.values())
    single_formulation_id = (
        next(iter(unique_formulation_ids)) if len(unique_formulation_ids) == 1 else None
    )

    for node in extraction.nodes:
        props = node.properties
        if node.label in {"Equation", "Variable", "Parameter", "Model"}:
            raw_fid = props.get("formulation_id")
            if raw_fid:
                global_id = formulation_aliases.get(str(raw_fid))
                if global_id is None:
                    global_id, local_id = scoped_formulation_id(
                        raw_fid,
                        paradigm_slug=props.get("paradigm_slug") or paradigm_scope,
                    )
                    if not global_id:
                        continue
                    props.setdefault("local_formulation_id", local_id)
                else:
                    _scope, local_id = split_scoped_id(global_id)
                    props.setdefault("local_formulation_id", local_id)
                props["formulation_id"] = global_id
                props.setdefault("paradigm_slug", split_scoped_id(global_id)[0] or "")
            elif single_formulation_id and node.label in {
                "Equation",
                "Variable",
                "Parameter",
            }:
                _scope, local_id = split_scoped_id(single_formulation_id)
                props["formulation_id"] = single_formulation_id
                props.setdefault("local_formulation_id", local_id)
                props.setdefault("paradigm_slug", _scope or "")
            if node.label == "Variable":
                variable_id = scoped_variable_id(
                    _raw_variable_name(props),
                    paradigm_slug=props.get("paradigm_slug"),
                    formulation_id=props.get("formulation_id"),
                )
                if variable_id:
                    scope, local_id = split_scoped_id(variable_id)
                    props["id"] = variable_id
                    props.setdefault("local_id", local_id)
                    if scope:
                        props.setdefault("paradigm_slug", scope)
                    node.natural_key = "id"

    variable_aliases = _normalize_variable_nodes(extraction, paradigm_scope)
    postulate_aliases = _normalize_postulate_nodes(extraction, paradigm_scope)
    parameter_aliases = _normalize_parameter_nodes(extraction)
    _normalize_model_nodes(extraction, formulation_aliases, paradigm_scope)
    _rewrite_relation_endpoints(
        extraction,
        formulation_aliases,
        variable_aliases,
        parameter_aliases,
        postulate_aliases,
        paradigm_scope,
    )
    for rel in extraction.relations:
        rel.from_key = canonical_endpoint_key_for_value(
            rel.from_label, rel.from_key_value
        )
        rel.to_key = canonical_endpoint_key_for_value(rel.to_label, rel.to_key_value)
    return extraction


def prune_to_approved_context(
    extraction: ExtractionResult,
    *,
    approved_paradigms: list[str] | tuple[str, ...] | set[str] | None = None,
    approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]] | None = None,
) -> ExtractionResult:
    """Drop scoped nodes outside the accepted pipeline context.

    Memory runs after HITL/auto review, so the router already knows which
    paradigms/formulations are allowed. Enforcing that context here prevents
    side paradigms emitted by an LLM from leaking into the KG and later being
    made readable by structural repair.
    """
    approved_slugs = {slugify(slug) for slug in approved_paradigms or [] if slug}
    approved_formulations: set[str] = set()
    for paradigm, raw_ids in (approved_specs or {}).items():
        scope = slugify(paradigm)
        if not scope:
            continue
        approved_slugs.add(scope)
        for raw_id in raw_ids or []:
            local = local_formulation_id(raw_id)
            if local:
                approved_formulations.add(local)
                approved_formulations.add(f"{scope}:{local}")

    if not approved_slugs and not approved_formulations:
        return extraction

    kept_nodes = []
    for node in extraction.nodes:
        if _node_outside_approved_context(
            node,
            approved_slugs=approved_slugs,
            approved_formulations=approved_formulations,
        ):
            continue
        kept_nodes.append(node)

    kept_relations = []
    for rel in extraction.relations:
        if _relation_outside_approved_context(
            rel,
            approved_slugs=approved_slugs,
            approved_formulations=approved_formulations,
        ):
            continue
        kept_relations.append(rel)

    extraction.nodes = kept_nodes
    extraction.relations = kept_relations
    return extraction


def materialize_structural_relations(extraction: ExtractionResult) -> ExtractionResult:
    """Add deterministic readability edges implied by normalized IDs/properties.

    These are not scientific claims. They are structural ownership edges that
    make the graph readable before the LLM graph reviewer sees it.
    """
    normalize_extraction_ids(extraction)
    relations = list(extraction.relations)
    seen = {
        (
            rel.from_label,
            str(rel.from_key_value),
            rel.rel_type,
            rel.to_label,
            str(rel.to_key_value),
        )
        for rel in relations
    }

    def add(
        from_label: str,
        from_value: object,
        rel_type: str,
        to_label: str,
        to_value: object,
        reason: str,
    ) -> None:
        if not from_value or not to_value:
            return
        key = (from_label, str(from_value), rel_type, to_label, str(to_value))
        if key in seen:
            return
        seen.add(key)
        relations.append(
            RelationSpec(
                from_label=from_label,
                from_key_value=str(from_value),
                to_label=to_label,
                to_key_value=str(to_value),
                rel_type=rel_type,
                properties={"source": "memory_structural", "reason": reason},
                from_key=canonical_key_for_label(from_label),
                to_key=canonical_key_for_label(to_label),
            )
        )

    for node in extraction.nodes:
        props = node.properties
        if node.label == "Formulation":
            scope = _node_paradigm_slug_from_props(props)
            if scope:
                add(
                    "Formulation",
                    props.get("id"),
                    "BELONGS_TO",
                    "Paradigm",
                    scope,
                    "formulation paradigm_slug",
                )
        elif node.label == "Postulate":
            scope = _node_paradigm_slug_from_props(props)
            if scope:
                add(
                    "Postulate",
                    props.get("id"),
                    "BELONGS_TO",
                    "Paradigm",
                    scope,
                    "postulate paradigm_slug",
                )
        elif node.label == "Model":
            formulation_id = props.get("formulation_id")
            if formulation_id:
                add(
                    "Model",
                    formulation_id,
                    "IMPLEMENTS",
                    "Formulation",
                    formulation_id,
                    "model formulation_id",
                )
                scope = (
                    _node_paradigm_slug_from_props(props)
                    or split_scoped_id(formulation_id)[0]
                )
                if scope:
                    add(
                        "Model",
                        formulation_id,
                        "BELONGS_TO",
                        "Paradigm",
                        scope,
                        "model formulation paradigm",
                    )
        elif node.label in {"Variable", "Parameter", "Equation"}:
            formulation_id = props.get("formulation_id")
            if formulation_id:
                rel_type = {
                    "Variable": "USES_VARIABLE",
                    "Parameter": "HAS_PARAMETER",
                    "Equation": "USES_EQUATION",
                }[node.label]
                node_key = props.get(canonical_key_for_label(node.label) or "")
                add(
                    "Formulation",
                    formulation_id,
                    rel_type,
                    node.label,
                    node_key,
                    "child formulation_id",
                )
            elif node.label == "Variable":
                scope = _node_paradigm_slug_from_props(props)
                if scope:
                    add(
                        "Variable",
                        props.get("id"),
                        "BELONGS_TO",
                        "Paradigm",
                        scope,
                        "paradigm-level variable",
                    )

    extraction.relations = relations
    return extraction


def prune_relationless_leaf_nodes(extraction: ExtractionResult) -> ExtractionResult:
    """Drop generated leaf nodes that cannot be made readable deterministically.

    Authors, papers, and brain regions are useful only when they are attached to
    a paradigm, paper, postulate, or variable. Unlike Parameters/Variables, the
    health pass cannot safely infer those literature edges, so relationless
    leaves would become permanent isolated nodes.
    """
    relation_required_labels = {"Author", "Paper", "BrainRegion"}
    connected_aliases = _relation_endpoint_aliases(extraction)
    kept_nodes = []
    for node in extraction.nodes:
        if node.label not in relation_required_labels:
            kept_nodes.append(node)
            continue
        aliases = _node_endpoint_aliases(node)
        if any((node.label, alias) in connected_aliases for alias in aliases):
            kept_nodes.append(node)

    if len(kept_nodes) == len(extraction.nodes):
        return extraction
    extraction.nodes = kept_nodes
    return extraction


def prune_unresolvable_relations(extraction: ExtractionResult) -> ExtractionResult:
    """Drop relations whose endpoints cannot resolve before KG writes.

    The KG writer can resolve aliases for nodes in the current batch and a small
    set of intentional cross-stage anchors. Generated relation endpoints outside
    those sets only produce recoverable writer errors. The post-write reviewer
    may add safe corrections later, but only against endpoints that actually
    exist in Neo4j.
    """
    local_aliases = _node_alias_index(extraction)
    local_labels = {node.label for node in extraction.nodes}
    kept_relations = []
    for relation in extraction.relations:
        if _relation_endpoint_is_resolvable(
            label=relation.from_label,
            value=relation.from_key_value,
            local_aliases=local_aliases,
            local_labels=local_labels,
        ) and _relation_endpoint_is_resolvable(
            label=relation.to_label,
            value=relation.to_key_value,
            local_aliases=local_aliases,
            local_labels=local_labels,
        ):
            kept_relations.append(relation)
    if len(kept_relations) == len(extraction.relations):
        return extraction
    extraction.relations = kept_relations
    return extraction


def _batch_paradigm_scope(extraction: ExtractionResult) -> str | None:
    scopes: list[str] = []
    for node in extraction.nodes:
        props = node.properties
        raw = props.get("paradigm_slug")
        if not raw and node.label == "Paradigm":
            raw = props.get("slug")
        if isinstance(raw, str) and raw.strip():
            scopes.append(slugify(raw))
    unique = {scope for scope in scopes if scope}
    return next(iter(unique)) if len(unique) == 1 else None


def _node_outside_approved_context(
    node,
    *,
    approved_slugs: set[str],
    approved_formulations: set[str],
) -> bool:
    if node.label == "Paradigm":
        slug = slugify(node.properties.get("slug") or "")
        return bool(approved_slugs and slug and slug not in approved_slugs)

    if node.label not in _SCOPED_LABELS:
        return False

    scope = _node_paradigm_scope(node)
    if approved_slugs and scope and scope not in approved_slugs:
        return True

    formulation_id = _node_formulation_scope(node)
    return bool(
        approved_formulations
        and formulation_id
        and _formulation_ref_outside_approved(formulation_id, approved_formulations)
    )


def _relation_outside_approved_context(
    rel,
    *,
    approved_slugs: set[str],
    approved_formulations: set[str],
) -> bool:
    for label, value in (
        (rel.from_label, rel.from_key_value),
        (rel.to_label, rel.to_key_value),
    ):
        if label == "Paradigm":
            slug = slugify(value)
            if approved_slugs and slug and slug not in approved_slugs:
                return True
        if (
            label == "Formulation"
            and approved_formulations
            and _formulation_ref_outside_approved(value, approved_formulations)
        ):
            return True
        if label in _SCOPED_LABELS:
            prefix = _paradigm_prefix(value)
            if approved_slugs and prefix and prefix not in approved_slugs:
                return True
    return False


def _formulation_ref_outside_approved(
    value: object,
    approved_formulations: set[str],
) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    scope, local = split_scoped_id(text)
    if scope and scope != "orphan":
        return text not in approved_formulations
    return text not in approved_formulations and local not in approved_formulations


def _node_paradigm_scope(node) -> str | None:
    props = node.properties
    scope = _node_paradigm_slug_from_props(props)
    if scope:
        return scope
    for key in ("id", "formulation_id"):
        prefix = _paradigm_prefix(props.get(key))
        if prefix:
            return prefix
    return None


def _node_formulation_scope(node) -> str | None:
    props = node.properties
    if node.label == "Formulation":
        raw = props.get("id")
    else:
        raw = props.get("formulation_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return scoped_formulation_id(
        raw,
        paradigm_slug=props.get("paradigm_slug"),
        name=props.get("name"),
    )[0]


def _node_paradigm_slug_from_props(props: dict) -> str | None:
    raw = props.get("paradigm_slug")
    if isinstance(raw, str) and raw.strip():
        return slugify(raw)
    return None


def _register_aliases(
    aliases: dict[str, str],
    target: str,
    *values: object,
) -> None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        aliases[text] = target
        aliases[component_id(text)] = target


def _normalize_variable_nodes(
    extraction: ExtractionResult,
    paradigm_scope: str | None,
) -> dict[tuple[str | None, str], str]:
    by_raw: dict[str, list[tuple[str | None, str]]] = defaultdict(list)
    aliases: dict[tuple[str | None, str], str] = {}

    for node in extraction.nodes:
        if node.label != "Variable":
            continue
        props = node.properties
        raw_id = props.get("id")
        raw_formulation_id = props.get("formulation_id")
        raw_name = _raw_variable_name(props)
        variable_id = scoped_variable_id(
            raw_name,
            paradigm_slug=props.get("paradigm_slug") or paradigm_scope,
            formulation_id=props.get("formulation_id"),
        )
        if not variable_id:
            continue

        scope, local_id = split_scoped_id(variable_id)
        props["id"] = variable_id
        props.setdefault("name", str(raw_name or ""))
        props.setdefault("local_id", local_id)
        if scope:
            props["paradigm_slug"] = scope
        node.natural_key = "id"

        formulation_id = (
            str(props.get("formulation_id")) if props.get("formulation_id") else None
        )
        _scope, local_formulation_id = split_scoped_id(formulation_id)
        raw_values = {
            variable_id,
            raw_id,
            raw_name,
            props.get("name"),
            props.get("symbol"),
            props.get("display_name"),
            local_id,
        }
        if raw_formulation_id and local_id:
            raw_values.add(f"{raw_formulation_id}:{local_id}")
        if local_formulation_id and local_id:
            raw_values.add(f"{local_formulation_id}:{local_id}")
        if formulation_id and local_id:
            raw_values.add(f"{formulation_id}:{local_id}")

        for raw in raw_values:
            if raw is None:
                continue
            for key in _variable_alias_keys(raw):
                if not key:
                    continue
                aliases[(scope, key)] = variable_id
                by_raw[key].append((scope, variable_id))

    for key, values in by_raw.items():
        unique_ids = {variable_id for _scope, variable_id in values}
        if len(unique_ids) == 1:
            aliases[(None, key)] = next(iter(unique_ids))
    return aliases


def _raw_variable_name(props: dict) -> object:
    raw = props.get("name") or props.get("symbol") or props.get("display_name")
    if raw:
        return raw
    raw_id = props.get("id")
    if isinstance(raw_id, str) and ":" in raw_id:
        return raw_id.rsplit(":", 1)[-1]
    return raw_id


def _normalize_parameter_nodes(
    extraction: ExtractionResult,
) -> dict[tuple[str | None, str], str]:
    by_raw: dict[str, list[tuple[str | None, str]]] = defaultdict(list)
    aliases: dict[tuple[str | None, str], str] = {}

    for node in extraction.nodes:
        if node.label != "Parameter":
            continue
        props = node.properties
        raw_id = props.get("id")
        raw_formulation_id = props.get("formulation_id")
        raw_name = props.get("name") or props.get("symbol") or props.get("display_name")
        param_id = scoped_parameter_id(
            raw_name,
            formulation_id=props.get("formulation_id"),
            paradigm_slug=props.get("paradigm_slug"),
        )
        if not param_id:
            continue
        props["id"] = param_id
        props.setdefault("name", str(raw_name or ""))
        node.natural_key = "id"
        formulation_id = (
            str(props.get("formulation_id")) if props.get("formulation_id") else None
        )
        _scope, local_formulation_id = split_scoped_id(formulation_id)
        symbol = component_id(raw_name)
        raw_values = {
            param_id,
            raw_id,
            props.get("name"),
            props.get("symbol"),
            props.get("display_name"),
        }
        if raw_formulation_id and symbol:
            raw_values.add(f"{raw_formulation_id}:{symbol}")
        if local_formulation_id and symbol:
            raw_values.add(f"{local_formulation_id}:{symbol}")
        if formulation_id and symbol:
            raw_values.add(f"{formulation_id}:{symbol}")
        raw_values.update(_parameter_display_aliases(props))

        for raw in raw_values:
            if raw is None:
                continue
            key = component_id(raw)
            if not key:
                continue
            aliases[(formulation_id, key)] = param_id
            by_raw[key].append((formulation_id, param_id))

    for key, values in by_raw.items():
        unique_ids = {param_id for _fid, param_id in values}
        if len(unique_ids) == 1:
            aliases[(None, key)] = next(iter(unique_ids))
    return aliases


def _normalize_model_nodes(
    extraction: ExtractionResult,
    formulation_aliases: dict[str, str],
    paradigm_scope: str | None,
) -> None:
    for node in extraction.nodes:
        if node.label != "Model":
            continue
        props = node.properties
        raw_fid = props.get("formulation_id")
        if not raw_fid:
            continue
        global_id = formulation_aliases.get(str(raw_fid))
        if global_id is None:
            global_id, local_id = scoped_formulation_id(
                raw_fid,
                paradigm_slug=props.get("paradigm_slug") or paradigm_scope,
            )
            if not global_id:
                continue
        else:
            _scope, local_id = split_scoped_id(global_id)
        props["formulation_id"] = global_id
        props.setdefault("local_formulation_id", local_id)
        props.setdefault("id", global_id)
        node.natural_key = "formulation_id"
        _register_aliases(formulation_aliases, global_id, raw_fid, local_id)


def _normalize_postulate_nodes(
    extraction: ExtractionResult,
    paradigm_scope: str | None,
) -> dict[tuple[str | None, str], str]:
    by_raw: dict[str, list[tuple[str | None, str]]] = defaultdict(list)
    aliases: dict[tuple[str | None, str], str] = {}

    for node in extraction.nodes:
        if node.label != "Postulate":
            continue
        props = node.properties
        raw_id = props.get("id")
        paradigm_slug = slugify(
            str(props.get("paradigm_slug") or paradigm_scope or "").strip()
        )
        if not raw_id:
            continue
        slot = _postulate_slot(raw_id)
        canonical_id = (
            f"{paradigm_slug}:{slot}" if paradigm_slug and slot else str(raw_id)
        )
        if paradigm_slug and str(raw_id) != canonical_id:
            props["id"] = canonical_id
            props["paradigm_slug"] = paradigm_slug
            node.natural_key = "id"

        raw_values = {raw_id, canonical_id, slot}
        for raw in raw_values:
            if raw is None:
                continue
            key = component_id(raw)
            if not key:
                continue
            aliases[(paradigm_slug or None, key)] = canonical_id
            by_raw[key].append((paradigm_slug or None, canonical_id))

    for key, values in by_raw.items():
        unique_ids = {postulate_id for _scope, postulate_id in values}
        if len(unique_ids) == 1:
            aliases[(None, key)] = next(iter(unique_ids))
    return aliases


def _rewrite_relation_endpoints(
    extraction: ExtractionResult,
    formulation_aliases: dict[str, str],
    variable_aliases: dict[tuple[str | None, str], str],
    parameter_aliases: dict[tuple[str | None, str], str],
    postulate_aliases: dict[tuple[str | None, str], str],
    paradigm_scope: str | None,
) -> None:
    for rel in extraction.relations:
        if rel.from_label == "Formulation":
            rel.from_key_value = formulation_aliases.get(
                rel.from_key_value, rel.from_key_value
            )
        if rel.to_label == "Formulation":
            rel.to_key_value = formulation_aliases.get(
                rel.to_key_value, rel.to_key_value
            )

        if rel.from_label == "Model" and rel.to_label == "Formulation":
            rel.from_key_value = formulation_aliases.get(
                rel.from_key_value, rel.from_key_value
            )
            rel.to_key_value = formulation_aliases.get(
                rel.to_key_value, rel.to_key_value
            )

        if rel.to_label == "Variable":
            rel.to_key_value = _resolve_variable_endpoint(
                rel.to_key_value,
                source_paradigm_slug=_relation_source_paradigm(rel, paradigm_scope),
                aliases=variable_aliases,
            )
        if rel.from_label == "Variable":
            rel.from_key_value = _resolve_variable_endpoint(
                rel.from_key_value,
                source_paradigm_slug=_relation_source_paradigm(rel, paradigm_scope),
                aliases=variable_aliases,
            )

        if rel.to_label == "Parameter":
            rel.to_key_value = _resolve_parameter_endpoint(
                rel.to_key_value,
                source_formulation_id=(
                    rel.from_key_value if rel.from_label == "Formulation" else None
                ),
                aliases=parameter_aliases,
            )
        if rel.from_label == "Parameter":
            rel.from_key_value = _resolve_parameter_endpoint(
                rel.from_key_value,
                source_formulation_id=None,
                aliases=parameter_aliases,
            )

        if rel.to_label == "Postulate":
            rel.to_key_value = _resolve_postulate_endpoint(
                rel.to_key_value,
                source_paradigm_slug=_relation_source_paradigm(rel, paradigm_scope),
                aliases=postulate_aliases,
            )
        if rel.from_label == "Postulate":
            rel.from_key_value = _resolve_postulate_endpoint(
                rel.from_key_value,
                source_paradigm_slug=(
                    slugify(rel.to_key_value)
                    if rel.to_label == "Paradigm"
                    else paradigm_scope
                ),
                aliases=postulate_aliases,
            )


def _resolve_variable_endpoint(
    raw: str,
    *,
    source_paradigm_slug: str | None,
    aliases: dict[tuple[str | None, str], str],
) -> str:
    source = slugify(source_paradigm_slug or "")
    keys = _variable_alias_keys(raw)
    if source:
        for key in keys:
            scoped = aliases.get((source, key))
            if scoped is not None:
                return scoped
    for key in keys:
        direct = aliases.get((None, key))
        if direct is not None:
            return direct
    if source:
        tail = str(raw or "").rsplit(":", 1)[-1]
        tail_key = component_id(_FORMULATION_SUFFIX_RE.sub("", tail))
        if tail_key:
            return f"{source}:{tail_key}"
    return raw


def _variable_alias_keys(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    values = {text, component_id(text)}
    tail = text.rsplit(":", 1)[-1]
    if tail != text:
        values.add(tail)
        values.add(component_id(tail))
    stripped_tail = _FORMULATION_SUFFIX_RE.sub("", tail).strip()
    if stripped_tail:
        values.add(stripped_tail)
        values.add(component_id(stripped_tail))
    return [value for value in values if value]


def _resolve_parameter_endpoint(
    raw: str,
    *,
    source_formulation_id: str | None,
    aliases: dict[tuple[str | None, str], str],
) -> str:
    key = component_id(raw)
    direct = aliases.get((None, key))
    if direct is not None and str(raw).count(":") >= 1:
        return direct
    if source_formulation_id is not None:
        scoped = aliases.get((source_formulation_id, key))
        if scoped is not None:
            return scoped
    return direct or raw


def _resolve_postulate_endpoint(
    raw: str,
    *,
    source_paradigm_slug: str | None,
    aliases: dict[tuple[str | None, str], str],
) -> str:
    key = component_id(raw)
    source = slugify(source_paradigm_slug or "")
    if source:
        scoped = aliases.get((source, key))
        if scoped is not None:
            return scoped
    direct = aliases.get((None, key))
    if direct is not None:
        return direct

    slot = _postulate_slot(raw)
    if source and slot:
        return f"{source}:{slot}"
    return raw


def _postulate_slot(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    tail = text.rsplit(":", 1)[-1].strip()
    return tail if re.match(r"(?i)^P\d+$", tail) else component_id(tail)


def _relation_source_paradigm(
    rel,
    paradigm_scope: str | None,
) -> str | None:
    for raw in (rel.from_key_value, rel.to_key_value):
        source = _paradigm_prefix(raw)
        if source:
            return source
    return paradigm_scope


def _paradigm_prefix(raw: object) -> str | None:
    text = str(raw or "").strip()
    if ":" not in text:
        return None
    prefix = text.partition(":")[0]
    if not prefix or prefix == "orphan":
        return None
    return slugify(prefix)


def _relation_endpoint_aliases(extraction: ExtractionResult) -> set[tuple[str, str]]:
    aliases: set[tuple[str, str]] = set()
    for relation in extraction.relations:
        aliases.add((relation.from_label, str(relation.from_key_value)))
        aliases.add((relation.to_label, str(relation.to_key_value)))
        aliases.add((relation.from_label, component_id(relation.from_key_value)))
        aliases.add((relation.to_label, component_id(relation.to_key_value)))
    return aliases


def _node_alias_index(
    extraction: ExtractionResult,
) -> dict[tuple[str, str], tuple[str, str] | None]:
    aliases: dict[tuple[str, str], tuple[str, str] | None] = {}
    for node in extraction.nodes:
        identity = _node_identity(node)
        for alias in _node_endpoint_aliases(node):
            key = (node.label, alias)
            existing = aliases.get(key)
            if existing is None and key in aliases:
                continue
            if existing is not None and existing != identity:
                aliases[key] = None
                continue
            aliases[key] = identity
    return aliases


def _node_identity(node) -> tuple[str, str]:
    natural_value = node.properties.get(node.natural_key)
    if natural_value is None:
        natural_value = (
            node.properties.get("id")
            or node.properties.get("slug")
            or node.properties.get("formulation_id")
            or node.properties.get("name")
            or node.properties.get("title")
            or node.properties.get("doi")
            or node.properties.get("latex")
        )
    return node.natural_key, str(natural_value)


def _node_endpoint_aliases(node) -> set[str]:
    aliases: set[str] = set()
    for raw in {
        node.properties.get(node.natural_key),
        node.properties.get("id"),
        node.properties.get("slug"),
        node.properties.get("name"),
        node.properties.get("title"),
        node.properties.get("doi"),
        node.properties.get("plaintext"),
        node.properties.get("latex"),
        node.properties.get("formulation_id"),
        node.properties.get("local_id"),
        node.properties.get("local_formulation_id"),
        node.properties.get("symbol"),
        node.properties.get("display_name"),
    }:
        if raw is None:
            continue
        text = str(raw)
        aliases.add(text)
        aliases.add(component_id(text))
    if node.label == "Parameter":
        for raw in _parameter_display_aliases(node.properties):
            aliases.add(str(raw))
            aliases.add(component_id(raw))
    if node.label == "Variable":
        local_id = node.properties.get("local_id")
        formulation_id = node.properties.get("formulation_id")
        local_formulation_id = node.properties.get("local_formulation_id")
        for raw_formulation in {formulation_id, local_formulation_id}:
            if raw_formulation and local_id:
                scoped_alias = f"{raw_formulation}:{local_id}"
                aliases.add(scoped_alias)
                aliases.add(component_id(scoped_alias))
    return {alias for alias in aliases if alias}


def _parameter_display_aliases(props: dict) -> set[str]:
    symbol = props.get("symbol") or props.get("name")
    display_name = props.get("display_name")
    aliases: set[str] = set()
    if not symbol or not display_name:
        return aliases

    symbol_id = component_id(symbol)
    display_id = component_id(display_name)
    compact_symbol_id = symbol_id.replace("-", "")
    for left in {str(symbol), symbol_id, compact_symbol_id}:
        if left:
            aliases.add(f"{left}-{display_name}")
            aliases.add(f"{left}-{display_id}")
            aliases.add(f"{left} {display_name}")
    return aliases


def _relation_endpoint_is_resolvable(
    *,
    label: str,
    value: object,
    local_aliases: dict[tuple[str, str], tuple[str, str] | None],
    local_labels: set[str],
) -> bool:
    aliases = {str(value), component_id(value)}
    if any(local_aliases.get((label, alias)) is not None for alias in aliases):
        return True
    if label in local_labels:
        return False
    return _external_endpoint_is_allowed(label, value)


def _external_endpoint_is_allowed(label: str, value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if label == "Paradigm":
        return bool(component_id(text))
    if label == "Postulate":
        prefix, sep, slot = text.partition(":")
        return bool(sep and component_id(prefix) and re.match(r"(?i)^P\d+$", slot))
    if label == "Formulation":
        return bool(component_id(text))
    return False
