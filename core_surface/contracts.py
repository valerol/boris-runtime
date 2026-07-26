from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Mapping

from core_surface.errors import CatalogError
from core_surface.manifest import PUBLIC_CORE_MANIFEST_DIALECT
from core_surface.models import ApplicabilityRecord, ManifestRecord, NormRecord


LEGACY_NORM_CATALOG_PATH = "assurance/NORM_CATALOG.tsv"
LEGACY_PHASE_APPLICABILITY_PATH = "assurance/NORM_PHASE_APPLICABILITY.tsv"
PUBLIC_CORE_CANON_PATH = "machine/CORE_CANON.json"
PUBLIC_APPLICABILITY_PATH = "machine/APPLICABILITY_SELECTOR.json"
PUBLIC_OPERATIONAL_SEMANTICS_PATH = "machine/OPERATIONAL_SEMANTICS.json"
PUBLIC_GATE_CONTRACTS_PATH = "machine/GATE_CONTRACTS.json"
PUBLIC_PHASE_VOCABULARY_PATH = "machine/PHASE_VOCABULARY.json"
PUBLIC_OPERATOR_ACCEPTANCE_PATH = "runtime/operator_acceptance.json"
PUBLIC_BOOT_CAPSULE_PATH = "runtime/capsules/BOOT_CAPSULE.json"
PUBLIC_PHASE_CAPSULE_PATTERN = "runtime/capsules/PHASE_{phase}_CAPSULE.json"
PUBLIC_CONTEXT_BUDGET_PATH = "assurance/CONTEXT_BUDGET_REPORT.json"


def normalize_contract(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> tuple[
    dict,
    dict[str, tuple[NormRecord, ...]],
    dict[str, NormRecord],
    dict[str, tuple[ApplicabilityRecord, ...]],
    dict[str, str],
    dict[str, dict],
    tuple[str, ...],
    dict,
]:
    if manifest.manifest_dialect == PUBLIC_CORE_MANIFEST_DIALECT:
        return _normalize_public_core(manifest, payloads)
    return _normalize_legacy_contract(manifest, payloads)


def _normalize_public_core(manifest, payloads):
    canon = _read_json_object(payloads, PUBLIC_CORE_CANON_PATH)
    operational = _read_json_object(
        payloads,
        PUBLIC_OPERATIONAL_SEMANTICS_PATH,
    )
    gates = _read_json_object(payloads, PUBLIC_GATE_CONTRACTS_PATH)
    selector = _read_json_object(payloads, PUBLIC_APPLICABILITY_PATH)
    phase_vocabulary = _read_json_object(
        payloads,
        PUBLIC_PHASE_VOCABULARY_PATH,
    )
    acceptance = _read_json_object(
        payloads,
        PUBLIC_OPERATOR_ACCEPTANCE_PATH,
    )

    normalized_canon = dict(canon)
    normalized_canon["executable"] = False
    normalized_canon["predicate_dsl"] = _public_predicate_dsl(operational)
    normalized_canon["deontic_semantics"] = _required_object(
        operational,
        "deontic_semantics",
        PUBLIC_OPERATIONAL_SEMANTICS_PATH,
    )
    normalized_canon["gate_decision_semantics"] = (
        _public_gate_decision_semantics(gates)
    )

    norms_by_layer, norm_index = _public_norms(canon)
    applicability = _public_applicability(selector, norm_index)
    descriptions = _public_phase_descriptions(phase_vocabulary, gates)
    phase_contexts = _public_phase_contexts(
        payloads,
        phase_vocabulary,
    )
    accepted_layers = _public_accepted_layers(acceptance)
    maximum_phase_candidate_count = _maximum_phase_candidate_count(
        applicability,
        norm_index,
        accepted_layers,
        phase_contexts,
    )
    context_windows = {
        phase: context["minimum_context_window_tokens"]
        for phase, context in phase_contexts.items()
    }
    compatibility_contract = {
        "source_contract": "public-core-v2",
        "predicate_operators": tuple(
            normalized_canon["predicate_dsl"]["operators"]
        ),
        "predicate_truth_values": tuple(
            normalized_canon["predicate_dsl"]["truth_values"]
        ),
        "deontic_operations": tuple(
            normalized_canon["deontic_semantics"]["operations"]
        ),
        "gate_results": tuple(
            normalized_canon["gate_decision_semantics"]["results"]
        ),
        "gate_precedence": tuple(
            item["result"]
            for item in normalized_canon[
                "gate_decision_semantics"
            ]["mapping_rules"]
        ),
        "norm_types": tuple(sorted({
            record.norm_type
            for record in norm_index.values()
        })),
        "selector_id": str(selector.get("selector_id", "")),
        "phase_complete_selection": (
            selector.get("semantic_completeness_scope", {}).get(
                "task_specific_narrowing"
            )
        ),
        "phase_context_windows": context_windows,
        "executable_phases": tuple(phase_contexts),
        "minimum_context_window_tokens": max(
            context_windows.values(),
            default=0,
        ),
        "maximum_phase_candidate_count": maximum_phase_candidate_count,
    }
    return (
        normalized_canon,
        norms_by_layer,
        norm_index,
        applicability,
        descriptions,
        phase_contexts,
        accepted_layers,
        compatibility_contract,
    )


def _normalize_legacy_contract(manifest, payloads):
    canon = _read_json_object(payloads, PUBLIC_CORE_CANON_PATH)
    norms_by_layer, norm_index = _legacy_norms(payloads)
    applicability = _legacy_applicability(payloads, norm_index)
    compatibility_contract = {
        "source_contract": manifest.manifest_dialect,
        "predicate_operators": tuple(
            canon.get("predicate_dsl", {}).get("operators", {})
        ),
        "predicate_truth_values": tuple(
            canon.get("predicate_dsl", {}).get("truth_values", ())
        ),
        "deontic_operations": tuple(
            canon.get("deontic_semantics", {}).get("operations", {})
        ),
        "gate_results": tuple(
            canon.get("gate_decision_semantics", {}).get("results", ())
        ),
        "gate_precedence": tuple(
            item.get("result")
            for item in canon.get(
                "gate_decision_semantics",
                {},
            ).get("mapping_rules", ())
            if isinstance(item, Mapping)
        ),
        "norm_types": tuple(sorted({
            record.norm_type
            for record in norm_index.values()
        })),
    }
    return (
        canon,
        norms_by_layer,
        norm_index,
        applicability,
        {},
        {},
        tuple(sorted(norms_by_layer)),
        compatibility_contract,
    )


def _public_predicate_dsl(operational):
    semantics = _required_object(
        operational,
        "predicate_semantics",
        PUBLIC_OPERATIONAL_SEMANTICS_PATH,
    )
    operators = _required_object(
        semantics,
        "operators",
        f"{PUBLIC_OPERATIONAL_SEMANTICS_PATH}#predicate_semantics",
    )
    truth_values = operational.get("truth_values")
    if not isinstance(truth_values, list) or not truth_values:
        raise CatalogError(
            f"{PUBLIC_OPERATIONAL_SEMANTICS_PATH}.truth_values is invalid."
        )
    missing_result = semantics.get("path_resolution", {}).get(
        "missing_path"
    )
    unknown_result = semantics.get("gate_mapping", {}).get("UNKNOWN")
    return {
        "truth_values": truth_values,
        "missing_path_result": missing_result,
        "unknown_material_result": unknown_result,
        "operators": operators,
        "test_vectors": semantics.get("test_vectors", []),
        "source_ref": (
            f"{PUBLIC_OPERATIONAL_SEMANTICS_PATH}#/predicate_semantics"
        ),
    }


def _public_gate_decision_semantics(gates):
    results = _required_object(
        gates,
        "result_semantics",
        PUBLIC_GATE_CONTRACTS_PATH,
    )
    required = {"PASS", "HOLD", "STOP", "REPAIR"}
    if set(results) != required:
        raise CatalogError(
            f"{PUBLIC_GATE_CONTRACTS_PATH}.result_semantics is not closed."
        )
    precedence = ("REPAIR", "STOP", "HOLD", "PASS")
    return {
        "results": ["PASS", "HOLD", "STOP", "REPAIR"],
        "mapping_rules": [
            {
                "result": result,
                "source": (
                    f"{PUBLIC_GATE_CONTRACTS_PATH}#/result_semantics/{result}"
                ),
            }
            for result in precedence
        ],
        "source_ref": f"{PUBLIC_GATE_CONTRACTS_PATH}#/result_semantics",
    }


def _public_norms(canon):
    records = canon.get("norms")
    if not isinstance(records, list) or not records:
        raise CatalogError(f"{PUBLIC_CORE_CANON_PATH}.norms is missing.")
    layers = defaultdict(list)
    index = {}
    for position, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise CatalogError(
                f"{PUBLIC_CORE_CANON_PATH}.norms[{position}] is not an object."
            )
        norm_id = _required_text(raw, "norm_id", position)
        layer = _required_text(raw, "layer", position)
        norm_type = _required_text(raw, "norm_type", position)
        if norm_id in index:
            raise CatalogError(f"Duplicate norm ID: {norm_id}")
        fields = {
            key: _field_text(value)
            for key, value in raw.items()
        }
        lifecycle_status = str(raw.get("status", "")).strip()
        fields["card_status"] = lifecycle_status
        fields["available_for_evaluation"] = (
            "TRUE" if lifecycle_status == "ACTIVE" else "FALSE"
        )
        fields["available_for_application"] = (
            "TRUE"
            if lifecycle_status == "ACTIVE" and layer == "BASE"
            else "FALSE"
        )
        execution_mode = str(raw.get("execution_mode", "")).strip()
        predicate_mode = (
            "runtime_typed"
            if execution_mode == "KERNEL_COMPUTED_TYPED_PREDICATE"
            else "semantic_interpreted"
        )
        record = NormRecord(
            norm_id=norm_id,
            layer=layer,
            norm_type=norm_type,
            fields=fields,
            lifecycle_status=lifecycle_status,
            available_for_evaluation=lifecycle_status == "ACTIVE",
            available_for_application=(
                lifecycle_status == "ACTIVE" and layer == "BASE"
            ),
            predicate_mode=predicate_mode,
            source_record=dict(raw),
        )
        layers[layer].append(record)
        index[norm_id] = record
    declared = canon.get("norm_counts")
    if isinstance(declared, Mapping):
        if declared.get("total") != len(index):
            raise CatalogError("CORE_CANON norm_counts.total mismatch.")
        for layer, records_for_layer in layers.items():
            field = layer.lower()
            if field in declared and declared[field] != len(records_for_layer):
                raise CatalogError(
                    f"CORE_CANON norm_counts.{field} mismatch."
                )
    return (
        {
            layer: tuple(records_for_layer)
            for layer, records_for_layer in layers.items()
        },
        index,
    )


def _public_applicability(selector, norm_index):
    records = selector.get("norm_index")
    if not isinstance(records, list) or not records:
        raise CatalogError(
            f"{PUBLIC_APPLICABILITY_PATH}.norm_index is missing."
        )
    result = defaultdict(list)
    seen_norms = set()
    for position, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            raise CatalogError(
                f"{PUBLIC_APPLICABILITY_PATH}.norm_index[{position}] is invalid."
            )
        norm_id = str(raw.get("norm_id", "")).strip()
        if norm_id not in norm_index:
            raise CatalogError(
                f"Applicability selector references unknown norm: {norm_id}"
            )
        if norm_id in seen_norms:
            raise CatalogError(
                f"Applicability selector duplicates norm: {norm_id}"
            )
        seen_norms.add(norm_id)
        phases = raw.get("required_phase")
        if (
            not isinstance(phases, list)
            or not phases
            or any(not isinstance(item, str) or not item for item in phases)
        ):
            raise CatalogError(
                f"Applicability selector phases are invalid for {norm_id}."
            )
        record = norm_index[norm_id]
        triggers = _json_array_field(record, "trigger") or ("*",)
        for phase in phases:
            result[norm_id].append(ApplicabilityRecord(
                required_phase=phase,
                application_kind="PHASE_COMPLETE",
                triggers=triggers,
                reason=(
                    f"{PUBLIC_APPLICABILITY_PATH}#/norm_index/{position}"
                ),
                owner=record.fields.get("owner", ""),
                review_status=(
                    "RUNTIME_TYPED"
                    if record.predicate_mode == "runtime_typed"
                    else "KERNEL_INTERPRETATION_REQUIRED"
                ),
            ))
    if seen_norms != set(norm_index):
        missing = sorted(set(norm_index) - seen_norms)
        raise CatalogError(
            f"Applicability selector omits canonical norms: {missing[:10]}"
        )
    return {
        norm_id: tuple(bindings)
        for norm_id, bindings in result.items()
    }


def _public_phase_descriptions(phase_vocabulary, gates):
    result = {}
    for item in phase_vocabulary.get("cycle_phases", ()):
        if isinstance(item, Mapping):
            phase = str(item.get("phase_id", "")).strip()
            if phase:
                result[phase] = phase
    for item in phase_vocabulary.get("external_phases_and_events", ()):
        if isinstance(item, Mapping):
            phase = str(item.get("phase_id", "")).strip()
            description = str(item.get("definition", "")).strip()
            if phase:
                result[phase] = description or phase
    for contract in gates.get("contracts", ()):
        if not isinstance(contract, Mapping):
            continue
        phase = str(contract.get("gate_id", "")).strip()
        name = str(contract.get("name", "")).strip()
        condition = str(contract.get("pass_condition", "")).strip()
        if phase:
            result[phase] = " — ".join(
                value for value in (name, condition) if value
            ) or phase
    return result


def _public_phase_contexts(payloads, phase_vocabulary):
    boot = _read_json_object(payloads, PUBLIC_BOOT_CAPSULE_PATH)
    budgets = _read_json_object(payloads, PUBLIC_CONTEXT_BUDGET_PATH)
    budget_records = budgets.get("phase_budgets")
    if not isinstance(budget_records, list) or not budget_records:
        raise CatalogError(
            f"{PUBLIC_CONTEXT_BUDGET_PATH}.phase_budgets is invalid."
        )
    budgets_by_phase = {}
    for position, raw in enumerate(budget_records):
        if not isinstance(raw, Mapping):
            raise CatalogError(
                f"{PUBLIC_CONTEXT_BUDGET_PATH}.phase_budgets[{position}] "
                "must be an object."
            )
        phase = str(raw.get("phase", "")).strip()
        minimum = raw.get("minimum_context_window_tokens")
        aggregate = raw.get("aggregate_required_tokens")
        if (
            not phase
            or isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 1
            or isinstance(aggregate, bool)
            or not isinstance(aggregate, int)
            or aggregate < 1
        ):
            raise CatalogError(
                f"{PUBLIC_CONTEXT_BUDGET_PATH}.phase_budgets[{position}] "
                "has an invalid capacity declaration."
            )
        if phase in budgets_by_phase:
            raise CatalogError(
                f"Duplicate context budget for phase {phase}."
            )
        budgets_by_phase[phase] = {
            "minimum_context_window_tokens": minimum,
            "aggregate_required_tokens": aggregate,
        }

    cycle_phases = tuple(
        str(item.get("phase_id", "")).strip()
        for item in phase_vocabulary.get("cycle_phases", ())
        if isinstance(item, Mapping)
    )
    if (
        not cycle_phases
        or any(not phase for phase in cycle_phases)
        or set(cycle_phases) != set(budgets_by_phase)
    ):
        raise CatalogError(
            "Phase vocabulary and context budget phase sets do not match."
        )

    result = {}
    for phase in cycle_phases:
        path = PUBLIC_PHASE_CAPSULE_PATTERN.format(phase=phase)
        capsule = _read_json_object(payloads, path)
        if capsule.get("phase_id") != phase:
            raise CatalogError(f"{path}.phase_id mismatch.")
        result[phase] = {
            "boot_capsule": boot,
            "phase_capsule": capsule,
            **budgets_by_phase[phase],
        }
    return result


def _public_accepted_layers(acceptance):
    layers = acceptance.get("accepted_layers")
    if (
        not isinstance(layers, list)
        or not layers
        or any(not isinstance(item, str) or not item for item in layers)
    ):
        raise CatalogError(
            f"{PUBLIC_OPERATOR_ACCEPTANCE_PATH}.accepted_layers is invalid."
        )
    return tuple(dict.fromkeys(layers))


def _maximum_phase_candidate_count(
    applicability,
    norm_index,
    accepted_layers,
    phase_contexts,
):
    accepted = set(accepted_layers)
    phase_norms = {
        phase: set()
        for phase in phase_contexts
    }
    for phase, norm_ids in phase_norms.items():
        active_scopes = {phase, "GLOBAL_CONTROL", "ALL_PHASES"}
        for norm_id, bindings in applicability.items():
            if norm_index[norm_id].layer not in accepted:
                continue
            if any(
                binding.required_phase in active_scopes
                for binding in bindings
            ):
                norm_ids.add(norm_id)
    maximum = max(
        (len(norm_ids) for norm_ids in phase_norms.values()),
        default=0,
    )
    if maximum < 1:
        raise CatalogError(
            "The accepted public Core layers have no phase candidates."
        )
    return maximum


def _legacy_norms(payloads):
    try:
        text = payloads[LEGACY_NORM_CATALOG_PATH].decode("utf-8")
    except KeyError as exc:
        raise CatalogError(
            f"Required norm catalog is missing: {LEGACY_NORM_CATALOG_PATH}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise CatalogError(
            f"{LEGACY_NORM_CATALOG_PATH} is not valid UTF-8."
        ) from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required = {"norm_id", "layer", "norm_type"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise CatalogError(
            f"{LEGACY_NORM_CATALOG_PATH} is missing required columns."
        )
    layers = defaultdict(list)
    index = {}
    for row_number, row in enumerate(reader, start=2):
        norm_id = (row.get("norm_id") or "").strip()
        layer = (row.get("layer") or "").strip()
        norm_type = (row.get("norm_type") or "").strip()
        if not norm_id or not layer or not norm_type:
            raise CatalogError(
                f"Incomplete norm identity on row {row_number}."
            )
        if norm_id in index:
            raise CatalogError(f"Duplicate norm ID: {norm_id}")
        lifecycle = (row.get("card_status") or "").strip()
        record = NormRecord(
            norm_id=norm_id,
            layer=layer,
            norm_type=norm_type,
            fields=row,
            lifecycle_status=lifecycle,
            available_for_evaluation=(
                (row.get("available_for_evaluation") or "").strip() == "TRUE"
            ),
            available_for_application=(
                (row.get("available_for_application") or "").strip() == "TRUE"
            ),
            predicate_mode="legacy_formal",
        )
        layers[layer].append(record)
        index[norm_id] = record
    if not index:
        raise CatalogError(
            f"{LEGACY_NORM_CATALOG_PATH} contains no norms."
        )
    return (
        {
            layer: tuple(records)
            for layer, records in layers.items()
        },
        index,
    )


def _legacy_applicability(payloads, norm_index):
    payload = payloads.get(LEGACY_PHASE_APPLICABILITY_PATH)
    if payload is None:
        return {}
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogError(
            f"{LEGACY_PHASE_APPLICABILITY_PATH} is not valid UTF-8."
        ) from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required = {
        "norm_id",
        "required_phase",
        "application_kind",
        "trigger",
        "reason",
        "owner",
        "review_status",
    }
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise CatalogError(
            f"{LEGACY_PHASE_APPLICABILITY_PATH} is missing required columns."
        )
    result = defaultdict(list)
    seen = set()
    for row_number, row in enumerate(reader, start=2):
        norm_id = row["norm_id"].strip()
        phase = row["required_phase"].strip()
        marker = (
            norm_id,
            phase,
            row["application_kind"],
            row["trigger"],
        )
        if not norm_id or not phase or norm_id not in norm_index:
            raise CatalogError(
                f"Invalid applicability binding on row {row_number}."
            )
        if marker in seen:
            raise CatalogError(
                f"Duplicate applicability binding on row {row_number}."
            )
        seen.add(marker)
        result[norm_id].append(ApplicabilityRecord(
            required_phase=phase,
            application_kind=row["application_kind"].strip(),
            triggers=_decode_string_array(
                row["trigger"],
                f"row {row_number} trigger",
            ),
            reason=row["reason"].strip(),
            owner=row["owner"].strip(),
            review_status=row["review_status"].strip(),
        ))
    return {
        norm_id: tuple(bindings)
        for norm_id, bindings in result.items()
    }


def _read_json_object(payloads, path):
    try:
        value = json.loads(payloads[path].decode("utf-8"))
    except KeyError as exc:
        raise CatalogError(f"Required Core contract is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"{path} is not valid UTF-8 JSON.") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"{path} must contain an object.")
    return value


def _required_object(value, field, path):
    nested = value.get(field)
    if not isinstance(nested, Mapping):
        raise CatalogError(f"{path}.{field} must contain an object.")
    return dict(nested)


def _required_text(value, field, position):
    text = value.get(field)
    if not isinstance(text, str) or not text.strip():
        raise CatalogError(
            f"{PUBLIC_CORE_CANON_PATH}.norms[{position}].{field} is invalid."
        )
    return text.strip()


def _field_text(value):
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return str(value)


def _json_array_field(record, field):
    raw = record.fields.get(field, "")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CatalogError(
            f"{record.norm_id}.{field} is not valid JSON."
        ) from exc
    if not isinstance(value, list):
        raise CatalogError(f"{record.norm_id}.{field} must be an array.")
    return tuple(
        item
        for item in value
        if isinstance(item, str) and item
    )


def _decode_string_array(raw, label):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{label} is not valid JSON.") from exc
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise CatalogError(f"{label} must be a non-empty string array.")
    return tuple(value)
