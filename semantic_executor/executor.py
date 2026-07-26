from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import uuid4

from semantic_executor.models import (
    ExecutionCandidate,
    ExecutionTrace,
    RuntimeAttestationReference,
    SemanticInput,
    ValidationIssue,
)
from semantic_executor.errors import SemanticCompatibilityError
from semantic_executor.validation import SemanticCalculationValidator
from semantic_executor.view import SemanticViewBuilder


class SemanticExecutor:
    """Isolated Phase 4F executor that cannot mutate Runtime or Core state."""

    def __init__(
        self,
        surface,
        calculator,
        compatibility,
        view_builder=None,
        validator=None,
    ):
        self.surface = surface
        self.calculator = calculator
        self.compatibility = compatibility
        self.view_builder = view_builder or SemanticViewBuilder()
        self.validator = validator or SemanticCalculationValidator()

    def execute(self, semantic_input: SemanticInput) -> ExecutionCandidate:
        try:
            self.compatibility.require_semantic_evaluation(self.surface)
        except (AttributeError, ValueError) as exc:
            raise SemanticCompatibilityError(
                "Semantic execution requires a valid RuntimeAttestation "
                "accepted for semantic_evaluation."
            ) from exc
        view = self.view_builder.build(self.surface, semantic_input)
        raw_calculation = self.calculator.calculate(view, semantic_input)
        calculation = self.validator.validate(raw_calculation, view)
        issues = self._guard_issues(view, calculation)
        final_gate = self._constrain_gate(view, calculation, issues)
        candidate_result = calculation.candidate_result
        if not candidate_result and final_gate != "HOLD":
            issues = tuple(_dedupe_issues([
                *issues,
                ValidationIssue(
                    code="CANDIDATE_RESULT_PROJECTED",
                    message=(
                        "The semantic calculator returned no candidate material "
                        "for a non-HOLD route. Runtime projected a minimal "
                        "candidate from the validated calculation."
                    ),
                ),
            ]))
            candidate_result = _project_candidate_result(
                calculation,
                final_gate,
            )
        attestation = self.compatibility.attestation
        trace = ExecutionTrace(
            trace_id=str(uuid4()),
            core_ref=view.core_ref,
            phase=view.phase,
            runtime_attestation=RuntimeAttestationReference(
                substrate_id=attestation.substrate_id,
                attestation_sha256=self.compatibility.attestation_sha256,
                spec_check_status=attestation.spec_check_status,
                activation_status=attestation.activation_status,
            ),
            active_layers=view.active_layers,
            candidate_norm_refs=tuple(
                candidate.norm_ref
                for candidate in view.candidates
            ),
            formal_predicate_results={
                candidate.norm_ref: candidate.formal_predicate_result
                for candidate in view.candidates
            },
            required_inputs=_required_inputs(view),
            selection=view.selection_trace,
            calculator_called=True,
            llm_suggested_gate=calculation.suggested_gate,
            final_gate=final_gate,
            validation_issues=issues,
        )
        return ExecutionCandidate(
            core_ref=view.core_ref,
            phase=view.phase,
            gate=final_gate,
            suggested_gate=calculation.suggested_gate,
            candidate_result=candidate_result,
            norm_results=calculation.norm_results,
            unknowns=calculation.unknowns,
            conflicts=calculation.conflicts,
            alternatives=calculation.alternatives,
            validation_issues=issues,
            trace=trace,
        )

    @staticmethod
    def _guard_issues(view, calculation):
        issues = []
        result_index = {
            result.norm_ref: result
            for result in calculation.norm_results
        }
        if not view.candidates:
            issues.append(ValidationIssue(
                code="NO_CANDIDATE_NORMS",
                message="No norms were selected for this phase and trigger context.",
            ))

        for candidate in view.candidates:
            result = result_index[candidate.norm_ref]
            if candidate.interpretation_status != "SUPPORTED":
                issues.append(ValidationIssue(
                    code=candidate.interpretation_status,
                    message=(
                        f"{candidate.norm_ref} cannot be automatically interpreted "
                        "by the current norm interpretation profile."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                candidate.predicate_mode != "semantic_interpreted"
                and candidate.formal_predicate_result == "UNKNOWN"
                and candidate.formal_applicability_result != "FALSE"
            ):
                issues.append(ValidationIssue(
                    code="FORMAL_PREDICATE_UNKNOWN",
                    message=(
                        f"{candidate.norm_ref} has an UNKNOWN formal predicate result."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                candidate.predicate_mode != "semantic_interpreted"
                and candidate.formal_predicate_result == "ERROR"
                and candidate.formal_applicability_result != "FALSE"
            ):
                issues.append(ValidationIssue(
                    code="FORMAL_PREDICATE_ERROR",
                    message=(
                        f"{candidate.norm_ref} has an ERROR formal predicate "
                        "result and requires repair."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                candidate.predicate_mode == "legacy_formal"
                and candidate.formal_predicate_result
                in {"FALSE", "UNKNOWN", "ERROR"}
                and result.applicability == "TRUE"
            ):
                issues.append(ValidationIssue(
                    code="APPLICABILITY_UPGRADE_REJECTED",
                    message=(
                        f"{candidate.norm_ref} semantic applicability cannot upgrade "
                        f"formal {candidate.formal_predicate_result} to TRUE."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if result.applicability == "UNKNOWN":
                issues.append(ValidationIssue(
                    code="SEMANTIC_APPLICABILITY_UNKNOWN",
                    message=(
                        f"{candidate.norm_ref} semantic applicability remains UNKNOWN."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if result.applicability == "ERROR":
                issues.append(ValidationIssue(
                    code="SEMANTIC_APPLICABILITY_ERROR",
                    message=(
                        f"{candidate.norm_ref} applicability calculation "
                        "returned ERROR and requires repair."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                result.applicability != "FALSE"
                and result.predicate_result == "UNKNOWN"
            ):
                issues.append(ValidationIssue(
                    code="SEMANTIC_PREDICATE_UNKNOWN",
                    message=(
                        f"{candidate.norm_ref} violation status remains UNKNOWN."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                result.applicability != "FALSE"
                and result.predicate_result == "ERROR"
            ):
                issues.append(ValidationIssue(
                    code="SEMANTIC_PREDICATE_ERROR",
                    message=(
                        f"{candidate.norm_ref} violation calculation returned "
                        "ERROR and requires repair."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if result.unknowns:
                issues.append(ValidationIssue(
                    code="NORM_MATERIAL_UNKNOWNS",
                    message=f"{candidate.norm_ref} retains material unknowns.",
                    norm_refs=(candidate.norm_ref,),
                ))

        if calculation.unknowns:
            issues.append(ValidationIssue(
                code="CALCULATION_MATERIAL_UNKNOWNS",
                message="The semantic calculation retains material unknowns.",
            ))
        if any(conflict.disposition == "HOLD" for conflict in calculation.conflicts):
            norm_refs = tuple(dict.fromkeys(
                norm_ref
                for conflict in calculation.conflicts
                if conflict.disposition == "HOLD"
                for norm_ref in conflict.norm_refs
            ))
            issues.append(ValidationIssue(
                code="UNRESOLVED_RULE_CONFLICT",
                message="The calculation retains a conflict with HOLD disposition.",
                norm_refs=norm_refs,
            ))
        return tuple(_dedupe_issues(issues))

    @staticmethod
    def _constrain_gate(view, calculation, issues):
        compatibility_or_unknown_codes = {
            "NO_CANDIDATE_NORMS",
            "EVALUATION_ONLY_INACTIVE",
            "EVALUATION_ONLY_NOT_APPLICABLE",
            "UNSUPPORTED_SOURCE_NORM_TYPE",
            "UNSUPPORTED_DEONTIC_OPERATION",
            "DEONTIC_SOURCE_MISMATCH",
            "INVALID_PRIORITY",
            "FORMAL_PREDICATE_UNKNOWN",
            "APPLICABILITY_UPGRADE_REJECTED",
            "SEMANTIC_APPLICABILITY_UNKNOWN",
            "SEMANTIC_PREDICATE_UNKNOWN",
            "NORM_MATERIAL_UNKNOWNS",
            "CALCULATION_MATERIAL_UNKNOWNS",
            "UNRESOLVED_RULE_CONFLICT",
        }
        decisions = [calculation.suggested_gate]
        decisions.extend(
            conflict.disposition
            for conflict in calculation.conflicts
        )
        result_index = {
            result.norm_ref: result
            for result in calculation.norm_results
        }
        legacy_deontic_gate = {
            "HOLD": "HOLD",
            "PROHIBIT": "STOP",
            "REPAIR": "REPAIR",
            "STOP": "STOP",
        }
        decisions.extend(
            legacy_deontic_gate[candidate.operation]
            for candidate in view.candidates
            if candidate.predicate_mode == "legacy_formal"
            and candidate.operation in legacy_deontic_gate
            and candidate.interpretation_status == "SUPPORTED"
            and result_index[candidate.norm_ref].applicability == "TRUE"
        )
        violation_gate = {
            "HOLD": "HOLD",
            "PROHIBIT": "STOP",
            "REPAIR": "REPAIR",
            "REQUIRE": "HOLD",
            "STOP": "STOP",
        }
        decisions.extend(
            violation_gate[candidate.operation]
            for candidate in view.candidates
            if candidate.predicate_mode != "legacy_formal"
            and candidate.operation in violation_gate
            and candidate.interpretation_status == "SUPPORTED"
            and result_index[candidate.norm_ref].applicability == "TRUE"
            and result_index[candidate.norm_ref].predicate_result == "TRUE"
        )
        if any(issue.code in compatibility_or_unknown_codes for issue in issues):
            decisions.append("HOLD")
        if any(
            issue.code in {
                "FORMAL_PREDICATE_ERROR",
                "SEMANTIC_APPLICABILITY_ERROR",
                "SEMANTIC_PREDICATE_ERROR",
            }
            for issue in issues
        ):
            decisions.append("REPAIR")
        precedence = tuple(dict.fromkeys(
            rule["result"]
            for rule in view.gate_decision_semantics["mapping_rules"]
        ))
        return min(decisions, key=precedence.index)


def _dedupe_issues(issues):
    result = []
    seen = set()
    for issue in issues:
        marker = (issue.code, issue.norm_refs)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(issue)
    return result


def _project_candidate_result(calculation, final_gate):
    """Build candidate material without adding a semantic conclusion."""
    calculation_payload = calculation.to_dict()
    return {
        "status": "CANDIDATE_ONLY",
        "projection_version": "boris-candidate-projection/1.0",
        "projection_kind": "validated_semantic_calculation",
        "gate": final_gate,
        "norm_results": calculation_payload["norm_results"],
        "unknowns": calculation_payload["unknowns"],
        "conflicts": calculation_payload["conflicts"],
        "alternatives": calculation_payload["alternatives"],
    }


def _required_inputs(view):
    requirements = {}
    for candidate in view.candidates:
        if candidate.predicate_mode == "semantic_interpreted":
            continue
        if candidate.predicate_mode == "runtime_typed":
            if candidate.formal_applicability_result == "UNKNOWN":
                predicates = (candidate.applicability_predicate,)
            elif (
                candidate.formal_applicability_result == "TRUE"
                and candidate.formal_predicate_result == "UNKNOWN"
            ):
                predicates = (candidate.violation_predicate,)
            else:
                predicates = ()
        elif candidate.formal_predicate_result == "UNKNOWN":
            predicates = (candidate.when,)
        else:
            predicates = ()
        for predicate in predicates:
            for path, constraint in _predicate_path_requirements(predicate):
                current = requirements.setdefault(
                    path,
                    {
                        "path": path,
                        "norm_refs": [],
                        "constraints": [],
                    },
                )
                if candidate.norm_ref not in current["norm_refs"]:
                    current["norm_refs"].append(candidate.norm_ref)
                if constraint not in current["constraints"]:
                    current["constraints"].append(constraint)
    return tuple(
        requirements[path]
        for path in sorted(requirements)
    )


def _predicate_path_requirements(value):
    if isinstance(value, Mapping):
        operation = value.get("op")
        for key in ("path", "left_path", "right_path"):
            path = value.get(key)
            if isinstance(path, str) and path.strip():
                yield path.strip(), _path_constraint(value, operation, key)
        paths = value.get("paths")
        if isinstance(paths, Sequence) and not isinstance(
            paths,
            (str, bytes),
        ):
            for path in paths:
                if isinstance(path, str) and path.strip():
                    yield path.strip(), _path_constraint(
                        value,
                        operation,
                        "paths",
                    )
        for nested in value.values():
            yield from _predicate_path_requirements(nested)
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes),
    ):
        for nested in value:
            yield from _predicate_path_requirements(nested)


def _path_constraint(expression, operation, path_key):
    constraint = {
        "operator": operation or "unknown",
        "path_role": path_key,
    }
    if operation == "fact" and "equals" in expression:
        constraint["expected"] = expression["equals"]
    elif operation in {"gte", "min_items"} and "value" in expression:
        constraint["minimum"] = expression["value"]
    elif operation == "enum_member" and "values" in expression:
        constraint["allowed_values"] = expression["values"]
    elif operation == "in":
        if "value" in expression:
            constraint["contains"] = expression["value"]
        elif "values" in expression:
            constraint["allowed_values"] = expression["values"]
    return constraint
