from __future__ import annotations

import json
import re
from collections.abc import Iterable

from core_surface.models import CoreSurface, NormRecord


MAX_PROJECTED_NORMS = 5
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
CONTEXT_FIELDS = (
    "title",
    "formulation",
    "scope",
    "semantic_target",
    "predicate",
    "trigger",
    "when",
    "modality",
    "execution_mode",
    "operation",
    "desired_value",
    "forbidden_value",
    "exceptions",
    "priority",
    "evidence_requirements",
    "hold",
    "stop",
    "target_state",
    "target_transition",
    "success_criterion",
    "boundary_conditions",
    "defect_signal",
    "repair_path",
    "closure_criterion",
)


def project_core_context(
    surface: CoreSurface,
    query: str,
    *,
    max_norms: int = MAX_PROJECTED_NORMS,
) -> dict:
    """Select bounded, passive Core Surface records for a context frame.

    This is not semantic applicability routing. It exposes immutable package
    identity plus a small lexical projection of canonical norm records so that
    a context consumer can inspect relevant source material without bypassing
    Core Surface integrity checks. The application layer owns this
    request-specific selection; Core Surface remains query-independent.
    """

    query_tokens = _tokens(query)
    candidates = []
    for norm_id in surface.norm_ids:
        record = surface.get_norm(norm_id)
        matched_terms = sorted(query_tokens & _tokens(_record_text(record)))
        score = _score(record, query_tokens)
        candidates.append({
            "score": score,
            "record": record,
            "matched_terms": matched_terms,
            "available": _is_available(record),
            "fallback": False,
        })

    ranked = [
        candidate
        for candidate in candidates
        if candidate["score"] > 0 and candidate["available"]
    ]
    fallback_used = False
    if not ranked:
        fallback_used = True
        ranked = [
            {
                "score": _fallback_score(record),
                "record": record,
                "matched_terms": [],
                "available": True,
                "fallback": True,
            }
            for record in surface.base_norms if _is_available(record)
        ]

    ranked.sort(key=lambda item: (-item["score"], item["record"].norm_id))
    selected = ranked[:max(0, max_norms)]
    selected_ids = {item["record"].norm_id for item in selected}
    chunks = [_identity_chunk(surface)]
    chunks.extend(
        _norm_chunk(item["record"], item["score"])
        for item in selected
    )

    return {
        "mode": "core_surface_projection",
        "chunks": chunks,
        "metadata": {
            "core_source": "core_surface",
            "core_version": surface.artifact_version,
            "core_package_id": surface.package_id,
            "core_release_package_id": (
                surface.release_package_id or surface.package_id
            ),
            "core_release_version": (
                surface.release_version or surface.artifact_version
            ),
            "core_content_set_sha256": surface.content_set_sha256,
            "projected_norm_count": len(selected),
            "projection_kind": "bounded_lexical",
            "semantic_routing": False,
        },
        "diagnostics": {
            "core_surface": {
                **_surface_summary(surface),
                "loading_order": list(getattr(surface, "loading_order", ())),
                "components": [
                    {
                        "path": component.path,
                        "role": component.role,
                        "sha256": component.sha256,
                        "size_bytes": component.size_bytes,
                        "required": component.required,
                    }
                    for component in getattr(surface, "components", ())
                ],
            },
            "query_tokens": sorted(query_tokens),
            "candidate_count": len(candidates),
            "eligible_count": len(ranked),
            "selected_count": len(selected),
            "excluded_count": len(candidates) - len(selected),
            "fallback_used": fallback_used,
            "selected_objects": [
                _diagnostic_object(
                    item["record"],
                    item["score"],
                    item["matched_terms"],
                    "fallback_base_norm" if item["fallback"] else "lexical_match",
                )
                for item in selected
            ],
            "excluded_objects": [
                _diagnostic_object(
                    candidate["record"],
                    candidate["score"],
                    candidate["matched_terms"],
                    _exclusion_reason(candidate, selected_ids, fallback_used),
                )
                for candidate in candidates
                if candidate["record"].norm_id not in selected_ids
            ],
        },
    }


def _identity_chunk(surface: CoreSurface) -> dict:
    identity = {
        "package_identity": dict(surface.package_identity),
        "status": surface.status,
        "purpose": surface.purpose,
        "release_flavor": surface.release_flavor,
        "content_set_sha256": surface.content_set_sha256,
        "manifest_sha256": surface.manifest_sha256,
    }
    return {
        "id": "core-surface:identity",
        "section": "core_surface",
        "title": "Verified Core Surface identity",
        "text": json.dumps(identity, ensure_ascii=False, sort_keys=True),
        "score": 1.0,
    }


def _norm_chunk(record: NormRecord, score: float) -> dict:
    fields = {
        field: value
        for field in CONTEXT_FIELDS
        if (value := str(record.fields.get(field, "")).strip())
    }
    payload = {
        "norm_id": record.norm_id,
        "layer": record.layer,
        "norm_type": record.norm_type,
        "card_status": str(record.fields.get("card_status", "")).strip(),
        "available_for_application": str(
            record.fields.get("available_for_application", "")
        ).strip(),
        "fields": fields,
    }
    return {
        "id": f"core-surface:norm:{record.norm_id}",
        "section": record.layer,
        "title": fields.get("title", record.norm_id),
        "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "score": round(score, 6),
    }


def _diagnostic_object(
    record: NormRecord,
    score: float,
    matched_terms: list[str],
    reason: str,
) -> dict:
    return {
        "object_id": record.norm_id,
        "object_type": "norm",
        "layer": record.layer,
        "norm_type": record.norm_type,
        "card_status": str(record.fields.get("card_status", "")).strip(),
        "available_for_application": str(
            record.fields.get("available_for_application", "")
        ).strip(),
        "score": round(score, 6),
        "matched_terms": list(matched_terms),
        "reason": reason,
    }


def _surface_summary(surface: CoreSurface) -> dict:
    summary = getattr(surface, "summary", None)
    if callable(summary):
        return summary()
    return {
        "package_id": surface.package_id,
        "artifact_version": surface.artifact_version,
        "status": surface.status,
        "purpose": surface.purpose,
        "release_flavor": surface.release_flavor,
        "content_set_sha256": surface.content_set_sha256,
        "manifest_sha256": surface.manifest_sha256,
        "norm_layers": {
            layer: len(records)
            for layer, records in getattr(surface, "norms_by_layer", {}).items()
        },
    }


def _exclusion_reason(candidate: dict, selected_ids: set[str], fallback_used: bool) -> str:
    record = candidate["record"]
    if record.norm_id in selected_ids:
        return "selected"
    if not candidate["available"]:
        return "not_available_for_application"
    if fallback_used:
        return "not_in_fallback_base_set"
    if candidate["score"] <= 0:
        return "no_lexical_match"
    return "below_selection_cutoff"


def _score(record: NormRecord, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    record_tokens = _tokens(_record_text(record))
    overlap = query_tokens & record_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(query_tokens)
    specificity = len(overlap) / max(1, len(record_tokens))
    availability_bonus = 0.05 if _is_available(record) else 0.0
    base_bonus = 0.02 if record.layer == "BASE" else 0.0
    return coverage + specificity + availability_bonus + base_bonus


def _fallback_score(record: NormRecord) -> float:
    priority = str(record.fields.get("priority", "")).strip()
    try:
        priority_value = int(priority)
    except ValueError:
        priority_value = 0
    return 0.1 + min(max(priority_value, 0), 1000) / 10000


def _is_available(record: NormRecord) -> bool:
    availability = str(
        record.fields.get("available_for_application", "")
    ).strip().upper()
    status = str(record.fields.get("card_status", "")).strip().upper()
    return availability in {"", "TRUE"} and status in {"", "ACTIVE"}


def _record_text(record: NormRecord) -> str:
    values: Iterable[str] = (
        record.norm_id,
        record.layer,
        record.norm_type,
        *(str(value) for value in record.fields.values()),
    )
    return " ".join(values)


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(str(value or ""))
        if len(token) > 1
    }
