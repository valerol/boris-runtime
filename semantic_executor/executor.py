from __future__ import annotations

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
            candidate_result=calculation.candidate_result,
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
            if candidate.formal_predicate_result == "UNKNOWN":
                issues.append(ValidationIssue(
                    code="FORMAL_PREDICATE_UNKNOWN",
                    message=(
                        f"{candidate.norm_ref} has an UNKNOWN formal predicate result."
                    ),
                    norm_refs=(candidate.norm_ref,),
                ))
            if (
                candidate.formal_predicate_result in {"FALSE", "UNKNOWN"}
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
        deontic_gate = {
            "HOLD": "HOLD",
            "PROHIBIT": "STOP",
            "REPAIR": "REPAIR",
            "STOP": "STOP",
        }
        decisions.extend(
            deontic_gate[candidate.operation]
            for candidate in view.candidates
            if candidate.operation in deontic_gate
            and candidate.interpretation_status == "SUPPORTED"
            and result_index[candidate.norm_ref].applicability == "TRUE"
        )
        if any(issue.code in compatibility_or_unknown_codes for issue in issues):
            decisions.append("HOLD")
        precedence = tuple(
            rule["result"]
            for rule in view.gate_decision_semantics["mapping_rules"]
        )
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
