from __future__ import annotations

from collections.abc import Mapping, Sequence


UNCERTAINTY_RESOLUTION_CLASSES = frozenset({
    "OPERATOR_INPUT",
    "RUNTIME_DERIVABLE",
    "FUTURE_CONTINGENT",
    "MODEL_UNCERTAINTY",
    "DOWNSTREAM_PRECONDITION",
    "UNRESOLVABLE_LIMITATION",
})

OPERATOR_RESOLUTION_CLASS = "OPERATOR_INPUT"
RUNTIME_RESOLUTION_CLASS = "RUNTIME_DERIVABLE"
NON_BLOCKING_RESOLUTION_CLASSES = frozenset({
    "FUTURE_CONTINGENT",
    "MODEL_UNCERTAINTY",
    "DOWNSTREAM_PRECONDITION",
    "UNRESOLVABLE_LIMITATION",
})

RESOLUTION_ACTIONS = {
    "OPERATOR_INPUT": "ASK_OPERATOR",
    "RUNTIME_DERIVABLE": "RESOLVE_IN_RUNTIME",
    "FUTURE_CONTINGENT": "BOUND_AS_SCENARIO",
    "MODEL_UNCERTAINTY": "BOUND_CONFIDENCE",
    "DOWNSTREAM_PRECONDITION": "DEFER_TO_DOWNSTREAM_STAGE",
    "UNRESOLVABLE_LIMITATION": "DISCLOSE_LIMITATION",
}


def build_uncertainty_resolution_catalog(execution_context):
    if not isinstance(execution_context, Mapping):
        return {
            "catalog_version": "boris-uncertainty-resolution/1.0",
            "entries": [],
        }
    capsule = execution_context.get("phase_capsule")
    if not isinstance(capsule, Mapping):
        return {
            "catalog_version": "boris-uncertainty-resolution/1.0",
            "entries": [],
        }
    gate = capsule.get("gate_contract")
    if not isinstance(gate, Mapping):
        gate = {}
    projection = gate.get("canonical_object_projection")
    if not isinstance(projection, Mapping):
        projection = {}
    evidence_contract = gate.get("required_evidence_contract")
    if not isinstance(evidence_contract, Mapping):
        evidence_contract = {}

    schemas = _object_schemas(capsule.get("required_object_schemas"))
    outputs = _string_sequence(projection.get("output_objects"))
    output_identities = {_object_identity(value) for value in outputs}
    assessments = _string_sequence(projection.get("assessment_objects"))
    entries = []

    for position, object_type in enumerate(outputs):
        schema = schemas.get(_object_identity(object_type), {})
        entries.append(_catalog_entry(
            resolution_ref=(
                "phase_capsule#/gate_contract/"
                f"canonical_object_projection/output_objects/{position}"
            ),
            resolution_class=RUNTIME_RESOLUTION_CLASS,
            kind="CURRENT_PHASE_OUTPUT",
            object_type=object_type,
            owner=_text(schema.get("owner")),
            source_class="CURRENT_RUNTIME",
            required_fields=_string_sequence(schema.get("required_fields")),
            schema_ref=_schema_ref(schema),
        ))

    for position, object_type in enumerate(assessments):
        if _object_identity(object_type) in output_identities:
            continue
        schema = schemas.get(_object_identity(object_type), {})
        entries.append(_catalog_entry(
            resolution_ref=(
                "phase_capsule#/gate_contract/"
                f"canonical_object_projection/assessment_objects/{position}"
            ),
            resolution_class="DOWNSTREAM_PRECONDITION",
            kind="CURRENT_CYCLE_ASSESSMENT",
            object_type=object_type,
            owner=_text(schema.get("owner")),
            source_class="CURRENT_RUNTIME",
            required_fields=_string_sequence(schema.get("required_fields")),
            schema_ref=_schema_ref(schema),
        ))

    bindings = evidence_contract.get("object_bindings")
    if not isinstance(bindings, Sequence) or isinstance(
        bindings,
        (str, bytes),
    ):
        bindings = ()
    for position, raw in enumerate(bindings):
        if not isinstance(raw, Mapping):
            continue
        object_type = _text(raw.get("object_type"))
        is_current_output = (
            _object_identity(object_type) in output_identities
            and raw.get("source_class") == "CURRENT_RUNTIME"
        )
        entries.append(_catalog_entry(
            resolution_ref=(
                "phase_capsule#/gate_contract/"
                "required_evidence_contract/object_bindings/"
                f"{position}"
            ),
            resolution_class=(
                RUNTIME_RESOLUTION_CLASS
                if is_current_output
                else "DOWNSTREAM_PRECONDITION"
            ),
            kind="GATE_OBJECT_BINDING",
            object_type=object_type,
            target_path=_text(raw.get("context_path")),
            owner=_text(raw.get("owner")),
            source_class=_text(raw.get("source_class")),
            required_fields=(),
            schema_ref="",
        ))

    registry_path = _text(evidence_contract.get("registry_path"))
    registry_type = _text(evidence_contract.get("registry_type"))
    if registry_path or registry_type:
        entries.append(_catalog_entry(
            resolution_ref=(
                "phase_capsule#/gate_contract/"
                "required_evidence_contract/registry_path"
            ),
            resolution_class="DOWNSTREAM_PRECONDITION",
            kind="RUNTIME_REGISTRY",
            object_type=registry_type,
            target_path=registry_path,
            owner="",
            source_class="CURRENT_RUNTIME",
            required_fields=(),
            schema_ref="",
        ))

    evidence_type = _text(evidence_contract.get("gate_evidence_type"))
    if evidence_type:
        entries.append(_catalog_entry(
            resolution_ref=(
                "phase_capsule#/gate_contract/"
                "required_evidence_contract/gate_evidence_type"
            ),
            resolution_class="DOWNSTREAM_PRECONDITION",
            kind="GATE_EVIDENCE",
            object_type=evidence_type,
            target_path="",
            owner=_text(evidence_contract.get("gate_evidence_owner")),
            source_class="CURRENT_RUNTIME",
            required_fields=(),
            schema_ref="",
        ))

    deduped = []
    seen = set()
    for entry in entries:
        marker = (
            entry["resolution_ref"],
            entry["resolution_class"],
            entry["object_type"],
            entry["target_path"],
        )
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(entry)
    return {
        "catalog_version": "boris-uncertainty-resolution/1.0",
        "entries": deduped,
    }


def resolution_catalog_index(catalog):
    if not isinstance(catalog, Mapping):
        return {}
    entries = catalog.get("entries")
    if not isinstance(entries, Sequence) or isinstance(
        entries,
        (str, bytes),
    ):
        return {}
    return {
        entry["resolution_ref"]: entry
        for entry in entries
        if isinstance(entry, Mapping)
        and isinstance(entry.get("resolution_ref"), str)
        and entry["resolution_ref"]
    }


def resolution_action(resolution_class):
    return RESOLUTION_ACTIONS[resolution_class]


def resolution_blocks_semantic_pass(resolution_class):
    return resolution_class in {
        OPERATOR_RESOLUTION_CLASS,
        RUNTIME_RESOLUTION_CLASS,
    }


def _object_schemas(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return {}
    result = {}
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        object_type = _text(raw.get("object_type"))
        if object_type:
            result[_object_identity(object_type)] = raw
    return result


def _object_identity(value):
    return "".join(
        character.lower()
        for character in str(value or "")
        if character.isalnum()
    )


def _schema_ref(schema):
    object_type = _text(schema.get("object_type"))
    if not object_type:
        return ""
    return f"phase_capsule#/required_object_schemas/{object_type}"


def _catalog_entry(
    *,
    resolution_ref,
    resolution_class,
    kind,
    object_type,
    owner,
    source_class,
    required_fields,
    schema_ref,
    target_path="",
):
    return {
        "resolution_ref": resolution_ref,
        "resolution_class": resolution_class,
        "kind": kind,
        "object_type": object_type,
        "target_path": target_path,
        "owner": owner,
        "source_class": source_class,
        "required_fields": list(required_fields),
        "schema_ref": schema_ref,
    }


def _string_sequence(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(
        text
        for text in (_text(item) for item in value)
        if text
    )


def _text(value):
    return value.strip() if isinstance(value, str) else ""
