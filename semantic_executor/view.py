from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core_surface import CoreSurface, NormRecord
from runtime_compatibility.profile import (
    SUPPORTED_GATE_RESULTS,
    SUPPORTED_SOURCE_NORM_TYPES,
)
from semantic_executor.errors import SemanticViewError
from semantic_executor.models import (
    ApplicabilityBinding,
    CoreReference,
    NormCandidate,
    SemanticInput,
    SemanticView,
)
from semantic_executor.predicates import (
    SUPPORTED_OPERATORS,
    PredicateEvaluator,
)
from semantic_executor.uncertainty import (
    build_uncertainty_resolution_catalog,
)


PHASE_APPLICABILITY_PATH = "assurance/NORM_PHASE_APPLICABILITY.tsv"
MAX_CANDIDATE_NORMS = 64
MAX_DECLARED_CANDIDATE_NORMS = 1024


@dataclass(frozen=True, slots=True)
class NormInterpretationProfile:
    supported_source_norm_types: frozenset[str] = SUPPORTED_SOURCE_NORM_TYPES


class SemanticViewBuilder:
    def __init__(self, interpretation_profile=None, predicate_evaluator=None):
        self.interpretation_profile = (
            interpretation_profile or NormInterpretationProfile()
        )
        self.predicate_evaluator = predicate_evaluator or PredicateEvaluator()

    def build(
        self,
        surface: CoreSurface,
        semantic_input: SemanticInput,
        operator_decision: Mapping | None = None,
    ) -> SemanticView:
        if (
            surface.phase_contexts
            and semantic_input.phase not in surface.phase_contexts
        ):
            raise SemanticViewError(
                f"Core contract does not publish an executable context for "
                f"phase {semantic_input.phase!r}."
            )
        predicate_dsl = self._require_machine_object(surface, "predicate_dsl")
        deontic = self._require_machine_object(surface, "deontic_semantics")
        gates = self._require_machine_object(
            surface,
            "gate_decision_semantics",
        )
        self._validate_predicate_dsl(predicate_dsl)
        self._validate_gate_semantics(gates)
        predicate_evaluator = (
            self.predicate_evaluator or PredicateEvaluator(surface)
        )
        bindings = self._load_bindings(surface)
        active_layers = tuple(dict.fromkeys(("BASE", *semantic_input.active_layers)))
        if surface.accepted_layers:
            unaccepted_layers = set(active_layers) - set(surface.accepted_layers)
            if unaccepted_layers:
                raise SemanticViewError(
                    "Semantic input requests layers that are not accepted by "
                    f"the loaded Core contract: {sorted(unaccepted_layers)}"
                )
        active_scopes = {
            "ALL_PHASES",
            "GLOBAL_CONTROL",
            semantic_input.phase,
            *semantic_input.applicability_scopes,
        }
        requested = set(semantic_input.requested_norm_refs)
        input_triggers = set(semantic_input.triggers)
        candidates = []
        excluded = defaultdict(int)

        for layer in active_layers:
            for record in surface.norms_for_layer(layer):
                norm_bindings = tuple(
                    binding
                    for binding in bindings.get(record.norm_id, ())
                    if binding.required_phase in active_scopes
                )
                if not norm_bindings:
                    excluded["phase"] += 1
                    continue

                explicitly_requested = record.norm_id in requested
                phase_complete = any(
                    binding.application_kind == "PHASE_COMPLETE"
                    for binding in norm_bindings
                )
                if (
                    not phase_complete
                    and not explicitly_requested
                    and not any(
                        "*" in binding.triggers
                        or input_triggers.intersection(binding.triggers)
                        for binding in norm_bindings
                    )
                ):
                    excluded["trigger"] += 1
                    continue

                if not record.available_for_evaluation:
                    excluded["not_evaluable"] += 1
                    continue

                active_card = record.lifecycle_status == "ACTIVE"
                if not active_card and not (
                    explicitly_requested and semantic_input.evaluate_inactive
                ):
                    excluded["inactive"] += 1
                    continue

                candidates.append(self._candidate(
                    record,
                    norm_bindings,
                    deontic,
                    semantic_input,
                    predicate_evaluator,
                    operator_decision=operator_decision,
                ))

        missing_requested = requested - {item.norm_ref for item in candidates}
        if missing_requested:
            raise SemanticViewError(
                "Requested norms are not eligible in the selected phase, layer, "
                f"trigger, or lifecycle context: {sorted(missing_requested)}"
            )
        declared_limit = surface.compatibility_contract.get(
            "maximum_phase_candidate_count",
            MAX_CANDIDATE_NORMS,
        )
        if (
            isinstance(declared_limit, bool)
            or not isinstance(declared_limit, int)
            or declared_limit < 1
            or declared_limit > MAX_DECLARED_CANDIDATE_NORMS
        ):
            raise SemanticViewError(
                "Core contract candidate capacity is invalid or exceeds the "
                f"Runtime safety limit of {MAX_DECLARED_CANDIDATE_NORMS}."
            )
        candidate_limit = declared_limit
        if len(candidates) > candidate_limit:
            raise SemanticViewError(
                f"Semantic candidate set exceeds the Phase 4F limit of "
                f"{candidate_limit}: {len(candidates)}"
            )

        candidates.sort(key=lambda item: (-item.priority, item.norm_ref))
        execution_context = surface.phase_context(
            semantic_input.phase
        )
        return SemanticView(
            core_ref=CoreReference.from_surface(surface),
            phase=semantic_input.phase,
            active_layers=active_layers,
            candidates=tuple(candidates),
            predicate_dsl=predicate_dsl,
            deontic_semantics=deontic,
            gate_decision_semantics=gates,
            execution_context=execution_context,
            uncertainty_resolution_catalog=(
                build_uncertainty_resolution_catalog(execution_context)
            ),
            operator_decision=(
                dict(operator_decision)
                if operator_decision is not None
                else {}
            ),
            selection_trace={
                "active_scopes": sorted(active_scopes),
                "input_triggers": sorted(input_triggers),
                "requested_norm_refs": sorted(requested),
                "selected_count": len(candidates),
                "excluded": dict(sorted(excluded.items())),
                "norm_type_policy": "source_values_preserved_with_adapter_coverage",
                "operator_decision_id": (
                    operator_decision.get("decision_id")
                    if isinstance(operator_decision, Mapping)
                    else None
                ),
            },
        )

    def applicability_catalog(self, surface: CoreSurface) -> dict[str, tuple[str, ...]]:
        """Expose the verified selector vocabulary without selecting any norms."""

        bindings = self._load_bindings(surface)
        phases = {
            binding.required_phase
            for norm_bindings in bindings.values()
            for binding in norm_bindings
            if binding.required_phase != "ALL_PHASES"
        }
        if surface.phase_contexts:
            phases.intersection_update(surface.phase_contexts)
        triggers = {
            trigger
            for norm_bindings in bindings.values()
            for binding in norm_bindings
            for trigger in binding.triggers
            if trigger != "*"
        }
        return {
            "phases": tuple(sorted(phases)),
            "triggers": tuple(sorted(triggers)),
            "layers": tuple(sorted(
                surface.accepted_layers or surface.norms_by_layer
            )),
            "applicability_scopes": tuple(sorted(phases)),
            "norm_refs": tuple(sorted(surface.norm_ids)),
        }

    def _candidate(
        self,
        record: NormRecord,
        bindings,
        deontic,
        semantic_input,
        predicate_evaluator,
        operator_decision=None,
    ):
        when = _optional_json_object_field(record, "when")
        predicate_context = semantic_input.predicate_context()
        if isinstance(operator_decision, Mapping):
            _apply_predicate_overrides(
                predicate_context,
                operator_decision.get("values", {}),
            )
        if record.predicate_mode == "runtime_typed":
            applicability_predicate = _json_object_field(
                record,
                "applicability_predicate",
            )
            violation_predicate = _json_object_field(
                record,
                "violation_predicate",
            )
            formal_applicability = predicate_evaluator.evaluate(
                applicability_predicate,
                predicate_context,
            )
            formal_result = predicate_evaluator.evaluate(
                violation_predicate,
                predicate_context,
            )
        elif record.predicate_mode == "semantic_interpreted":
            applicability_predicate = {}
            violation_predicate = {}
            formal_applicability = "UNKNOWN"
            formal_result = "UNKNOWN"
        else:
            applicability_predicate = when
            violation_predicate = when
            formal_result = predicate_evaluator.evaluate(
                when,
                predicate_context,
            )
            formal_applicability = formal_result
        operation = record.fields.get("operation", "").strip()
        modality = record.fields.get("modality", "").strip()
        operations = deontic.get("operations", {})
        modality_map = deontic.get("modality_map", {})

        if record.lifecycle_status != "ACTIVE":
            interpretation_status = "EVALUATION_ONLY_INACTIVE"
        elif not record.available_for_application:
            interpretation_status = "EVALUATION_ONLY_NOT_APPLICABLE"
        elif (
            record.norm_type
            not in self.interpretation_profile.supported_source_norm_types
        ):
            interpretation_status = "UNSUPPORTED_SOURCE_NORM_TYPE"
        elif operation not in operations:
            interpretation_status = "UNSUPPORTED_DEONTIC_OPERATION"
        elif modality_map.get(modality) != operation:
            interpretation_status = "DEONTIC_SOURCE_MISMATCH"
        else:
            interpretation_status = "SUPPORTED"

        try:
            priority = int(record.fields.get("priority", ""))
        except ValueError:
            priority = 0
            interpretation_status = "INVALID_PRIORITY"

        return NormCandidate(
            norm_ref=record.norm_id,
            layer=record.layer,
            card_status=record.fields.get("card_status", ""),
            norm_type=record.norm_type,
            modality=modality,
            operation=operation,
            execution_mode=record.fields.get("execution_mode", "").strip(),
            priority=priority,
            when=when,
            applicability_predicate=applicability_predicate,
            violation_predicate=violation_predicate,
            formal_applicability_result=formal_applicability,
            formal_predicate_result=formal_result,
            predicate_mode=record.predicate_mode,
            bindings=bindings,
            interpretation_status=interpretation_status,
            source_fields=record.fields,
            source_record=record.source_record,
        )

    @staticmethod
    def _require_machine_object(surface, field):
        value = surface.machine_canon.get(field)
        if not isinstance(value, Mapping):
            raise SemanticViewError(f"machine/CORE_CANON.json lacks object {field!r}.")
        return value

    @staticmethod
    def _validate_predicate_dsl(predicate_dsl):
        if predicate_dsl.get("missing_path_result") != "UNKNOWN":
            raise SemanticViewError(
                "Predicate DSL missing_path_result must be UNKNOWN for Phase 4F."
            )
        if tuple(predicate_dsl.get("truth_values", ())) not in {
            ("TRUE", "FALSE", "UNKNOWN"),
            ("TRUE", "FALSE", "UNKNOWN", "ERROR"),
        }:
            raise SemanticViewError(
                "Predicate DSL truth_values are incompatible with Phase 4F."
            )
        operators = predicate_dsl.get("operators")
        if (
            not isinstance(operators, Mapping)
            or not set(operators).issubset(SUPPORTED_OPERATORS)
        ):
            raise SemanticViewError(
                "Predicate DSL operators are incompatible with Phase 4F."
            )
        if predicate_dsl.get("unknown_material_result") != "HOLD":
            raise SemanticViewError(
                "Predicate DSL unknown_material_result must be HOLD for Phase 4F."
            )

    @staticmethod
    def _validate_gate_semantics(gates):
        if tuple(gates.get("results", ())) != (
            "PASS",
            "HOLD",
            "STOP",
            "REPAIR",
        ):
            raise SemanticViewError(
                "GateDecision results are incompatible with Phase 4F."
            )
        mapping = gates.get("mapping_rules")
        if (
            not isinstance(mapping, Sequence)
            or isinstance(mapping, (str, bytes))
        ):
            raise SemanticViewError(
                "GateDecision mapping_rules must be an array."
            )
        precedence = tuple(dict.fromkeys(
            item.get("result")
            for item in mapping
            if isinstance(item, Mapping)
        ))
        if precedence != SUPPORTED_GATE_RESULTS:
            raise SemanticViewError(
                "GateDecision precedence is incompatible with Phase 4F."
            )

    @staticmethod
    def _load_bindings(surface):
        if surface.applicability_by_norm:
            return {
                norm_ref: tuple(ApplicabilityBinding(
                    required_phase=record.required_phase,
                    application_kind=record.application_kind,
                    triggers=record.triggers,
                    reason=record.reason,
                    owner=record.owner,
                    review_status=record.review_status,
                ) for record in records)
                for norm_ref, records in surface.applicability_by_norm.items()
            }
        try:
            payload = surface.read_bytes(PHASE_APPLICABILITY_PATH)
        except KeyError as exc:
            raise SemanticViewError(
                f"Core package lacks required semantic surface: {PHASE_APPLICABILITY_PATH}"
            ) from exc
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SemanticViewError(
                f"{PHASE_APPLICABILITY_PATH} is not valid UTF-8."
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
            raise SemanticViewError(
                f"{PHASE_APPLICABILITY_PATH} is missing required columns."
            )

        result = defaultdict(list)
        seen = set()
        for row_number, row in enumerate(reader, start=2):
            norm_ref = row["norm_id"].strip()
            required_phase = row["required_phase"].strip()
            key = (norm_ref, required_phase, row["application_kind"], row["trigger"])
            if not norm_ref or not required_phase:
                raise SemanticViewError(
                    f"Incomplete phase applicability row {row_number}."
                )
            if key in seen:
                raise SemanticViewError(
                    f"Duplicate phase applicability binding on row {row_number}."
                )
            seen.add(key)
            if not surface.has_norm(norm_ref):
                raise SemanticViewError(
                    f"Phase applicability references unknown norm: {norm_ref}"
                )
            triggers = _json_string_array(row["trigger"], f"row {row_number} trigger")
            result[norm_ref].append(ApplicabilityBinding(
                required_phase=required_phase,
                application_kind=row["application_kind"].strip(),
                triggers=triggers,
                reason=row["reason"].strip(),
                owner=row["owner"].strip(),
                review_status=row["review_status"].strip(),
            ))
        return {
            norm_ref: tuple(records)
            for norm_ref, records in result.items()
        }


def _apply_predicate_overrides(context, values):
    if not isinstance(values, Mapping):
        raise SemanticViewError(
            "OperatorDecision values must be a path-to-value object."
        )
    for path, value in values.items():
        if not isinstance(path, str) or not path.strip():
            raise SemanticViewError(
                "OperatorDecision selector paths must be non-empty strings."
            )
        parts = path.split(".")
        current = context
        for part in parts[:-1]:
            nested = current.get(part)
            if nested is None:
                nested = {}
                current[part] = nested
            if not isinstance(nested, dict):
                raise SemanticViewError(
                    "OperatorDecision selector conflicts with semantic context."
                )
            current = nested
        current[parts[-1]] = value


def _source_bool(record, field):
    value = record.fields.get(field, "").strip()
    if value not in {"TRUE", "FALSE"}:
        raise SemanticViewError(
            f"{record.norm_id}.{field} must be TRUE or FALSE, got {value!r}."
        )
    return value == "TRUE"


def _json_object_field(record, field):
    raw = record.fields.get(field, "")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticViewError(
            f"{record.norm_id}.{field} is not valid JSON."
        ) from exc
    if not isinstance(value, dict):
        raise SemanticViewError(f"{record.norm_id}.{field} must be a JSON object.")
    return value


def _optional_json_object_field(record, field):
    raw = record.fields.get(field, "")
    if not raw:
        return {}
    return _json_object_field(record, field)


def _json_string_array(raw, label):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticViewError(f"{label} is not valid JSON.") from exc
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise SemanticViewError(f"{label} must be a non-empty string array.")
    return tuple(value)
