from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from core_surface import CoreSurface
from core_surface.models import freeze_value


TRUTH_VALUES = frozenset({"TRUE", "FALSE", "UNKNOWN"})
GATE_RESULTS = frozenset({"PASS", "HOLD", "STOP", "REPAIR"})


def thaw_value(value):
    if isinstance(value, Mapping):
        return {
            key: thaw_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, (tuple, list, frozenset, set)):
        return [thaw_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class CoreReference:
    package_id: str
    artifact_version: str
    source_kind: str
    archive_sha256: str
    content_set_sha256: str
    manifest_sha256: str

    @classmethod
    def from_surface(cls, surface: CoreSurface) -> "CoreReference":
        return cls(
            package_id=surface.package_id,
            artifact_version=surface.artifact_version,
            source_kind=surface.source_kind,
            archive_sha256=surface.archive_sha256 or "",
            content_set_sha256=surface.content_set_sha256,
            manifest_sha256=surface.manifest_sha256,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "package_id": self.package_id,
            "artifact_version": self.artifact_version,
            "source_kind": self.source_kind,
            "archive_sha256": self.archive_sha256,
            "content_set_sha256": self.content_set_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class RuntimeAttestationReference:
    substrate_id: str
    attestation_sha256: str
    spec_check_status: str
    activation_status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "substrate_id": self.substrate_id,
            "attestation_sha256": self.attestation_sha256,
            "spec_check_status": self.spec_check_status,
            "activation_status": self.activation_status,
        }


@dataclass(frozen=True, slots=True)
class SemanticInput:
    phenomenon: Any
    phase: str
    facts: Mapping[str, Any] = field(default_factory=dict)
    unknowns: tuple[str, ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()
    authority: Mapping[str, Any] = field(default_factory=dict)
    active_layers: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    applicability_scopes: tuple[str, ...] = ()
    requested_norm_refs: tuple[str, ...] = ()
    evaluate_inactive: bool = False

    def __post_init__(self):
        phase = str(self.phase).strip()
        if not phase:
            raise ValueError("SemanticInput.phase must be a non-empty string.")
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "phenomenon", freeze_value(self.phenomenon))
        object.__setattr__(self, "facts", freeze_value(dict(self.facts)))
        object.__setattr__(self, "authority", freeze_value(dict(self.authority)))
        object.__setattr__(
            self,
            "evidence",
            tuple(freeze_value(dict(item)) for item in self.evidence),
        )
        for field_name in (
            "unknowns",
            "active_layers",
            "triggers",
            "applicability_scopes",
            "requested_norm_refs",
        ):
            values = tuple(
                value
                for value in (
                    str(item).strip()
                    for item in getattr(self, field_name)
                )
                if value
            )
            object.__setattr__(self, field_name, tuple(dict.fromkeys(values)))

    def predicate_context(self) -> dict[str, Any]:
        context = thaw_value(self.facts)
        phenomenon = thaw_value(self.phenomenon)
        authority = thaw_value(self.authority)
        evidence = thaw_value(self.evidence)
        context.setdefault("phenomenon", phenomenon)
        context.setdefault("authority", authority)
        context.setdefault("authorization", authority)
        context.setdefault("evidence", evidence)
        context.setdefault("unknowns", list(self.unknowns))
        return context

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "phenomenon": thaw_value(self.phenomenon),
            "phase": self.phase,
            "facts": thaw_value(self.facts),
            "unknowns": list(self.unknowns),
            "evidence": thaw_value(self.evidence),
            "authority": thaw_value(self.authority),
            "active_layers": list(self.active_layers),
            "triggers": list(self.triggers),
            "applicability_scopes": list(self.applicability_scopes),
            "requested_norm_refs": list(self.requested_norm_refs),
            "evaluate_inactive": self.evaluate_inactive,
        }


@dataclass(frozen=True, slots=True)
class ApplicabilityBinding:
    required_phase: str
    application_kind: str
    triggers: tuple[str, ...]
    reason: str
    owner: str
    review_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_phase": self.required_phase,
            "application_kind": self.application_kind,
            "triggers": list(self.triggers),
            "reason": self.reason,
            "owner": self.owner,
            "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class NormCandidate:
    norm_ref: str
    layer: str
    card_status: str
    norm_type: str
    modality: str
    operation: str
    execution_mode: str
    priority: int
    when: Mapping[str, Any]
    formal_predicate_result: str
    bindings: tuple[ApplicabilityBinding, ...]
    interpretation_status: str
    source_fields: Mapping[str, str] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "when", freeze_value(dict(self.when)))
        object.__setattr__(
            self,
            "source_fields",
            MappingProxyType(dict(self.source_fields)),
        )

    def to_prompt_dict(self) -> dict[str, Any]:
        semantic_fields = (
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
            "forbidden_state",
            "boundary_conditions",
            "defect_signal",
            "repair_path",
            "closure_criterion",
        )
        return {
            "norm_ref": self.norm_ref,
            "layer": self.layer,
            "card_status": self.card_status,
            "norm_type": self.norm_type,
            "interpretation_status": self.interpretation_status,
            "formal_predicate_result": self.formal_predicate_result,
            "phase_bindings": [binding.to_dict() for binding in self.bindings],
            "source": {
                name: self.source_fields.get(name, "")
                for name in semantic_fields
            },
        }


@dataclass(frozen=True, slots=True)
class SemanticView:
    core_ref: CoreReference
    phase: str
    active_layers: tuple[str, ...]
    candidates: tuple[NormCandidate, ...]
    predicate_dsl: Mapping[str, Any] = field(repr=False)
    deontic_semantics: Mapping[str, Any] = field(repr=False)
    gate_decision_semantics: Mapping[str, Any] = field(repr=False)
    selection_trace: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(
            self,
            "predicate_dsl",
            freeze_value(dict(self.predicate_dsl)),
        )
        object.__setattr__(
            self,
            "deontic_semantics",
            freeze_value(dict(self.deontic_semantics)),
        )
        object.__setattr__(
            self,
            "gate_decision_semantics",
            freeze_value(dict(self.gate_decision_semantics)),
        )
        object.__setattr__(
            self,
            "selection_trace",
            freeze_value(dict(self.selection_trace)),
        )

    def get_candidate(self, norm_ref: str) -> NormCandidate:
        for candidate in self.candidates:
            if candidate.norm_ref == norm_ref:
                return candidate
        raise KeyError(norm_ref)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "core_ref": self.core_ref.to_dict(),
            "phase": self.phase,
            "active_layers": list(self.active_layers),
            "predicate_dsl": thaw_value(self.predicate_dsl),
            "deontic_semantics": thaw_value(self.deontic_semantics),
            "gate_decision_semantics": thaw_value(
                self.gate_decision_semantics
            ),
            "candidates": [
                candidate.to_prompt_dict()
                for candidate in self.candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class NormCalculation:
    norm_ref: str
    layer: str
    operation: str
    predicate_result: str
    applicability: str
    reason: str
    unknowns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "norm_ref": self.norm_ref,
            "layer": self.layer,
            "operation": self.operation,
            "predicate_result": self.predicate_result,
            "applicability": self.applicability,
            "reason": self.reason,
            "unknowns": list(self.unknowns),
        }


@dataclass(frozen=True, slots=True)
class ConflictCalculation:
    norm_refs: tuple[str, ...]
    kind: str
    disposition: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "norm_refs": list(self.norm_refs),
            "kind": self.kind,
            "disposition": self.disposition,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SemanticCalculation:
    core_ref: CoreReference
    phase: str
    norm_results: tuple[NormCalculation, ...]
    unknowns: tuple[str, ...]
    conflicts: tuple[ConflictCalculation, ...]
    alternatives: tuple[Mapping[str, Any], ...]
    suggested_gate: str
    candidate_result: Mapping[str, Any]

    def __post_init__(self):
        object.__setattr__(
            self,
            "alternatives",
            tuple(freeze_value(dict(item)) for item in self.alternatives),
        )
        object.__setattr__(
            self,
            "candidate_result",
            freeze_value(dict(self.candidate_result)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_ref": self.core_ref.to_dict(),
            "phase": self.phase,
            "norm_results": [result.to_dict() for result in self.norm_results],
            "unknowns": list(self.unknowns),
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "alternatives": thaw_value(self.alternatives),
            "suggested_gate": self.suggested_gate,
            "candidate_result": thaw_value(self.candidate_result),
        }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    norm_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "norm_refs": list(self.norm_refs),
        }


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    trace_id: str
    core_ref: CoreReference
    phase: str
    runtime_attestation: RuntimeAttestationReference
    active_layers: tuple[str, ...]
    candidate_norm_refs: tuple[str, ...]
    formal_predicate_results: Mapping[str, str]
    selection: Mapping[str, Any]
    calculator_called: bool
    llm_suggested_gate: str
    final_gate: str
    validation_issues: tuple[ValidationIssue, ...]

    def __post_init__(self):
        object.__setattr__(
            self,
            "formal_predicate_results",
            MappingProxyType(dict(self.formal_predicate_results)),
        )
        object.__setattr__(self, "selection", freeze_value(dict(self.selection)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "core_ref": self.core_ref.to_dict(),
            "phase": self.phase,
            "runtime_attestation": self.runtime_attestation.to_dict(),
            "active_layers": list(self.active_layers),
            "candidate_norm_refs": list(self.candidate_norm_refs),
            "formal_predicate_results": dict(self.formal_predicate_results),
            "selection": thaw_value(self.selection),
            "calculator_called": self.calculator_called,
            "llm_suggested_gate": self.llm_suggested_gate,
            "final_gate": self.final_gate,
            "validation_issues": [
                issue.to_dict()
                for issue in self.validation_issues
            ],
        }


@dataclass(frozen=True, slots=True)
class ExecutionCandidate:
    core_ref: CoreReference
    phase: str
    gate: str
    suggested_gate: str
    candidate_result: Mapping[str, Any]
    norm_results: tuple[NormCalculation, ...]
    unknowns: tuple[str, ...]
    conflicts: tuple[ConflictCalculation, ...]
    alternatives: tuple[Mapping[str, Any], ...]
    validation_issues: tuple[ValidationIssue, ...]
    trace: ExecutionTrace

    def __post_init__(self):
        object.__setattr__(
            self,
            "alternatives",
            tuple(freeze_value(dict(item)) for item in self.alternatives),
        )
        object.__setattr__(
            self,
            "candidate_result",
            freeze_value(dict(self.candidate_result)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_ref": self.core_ref.to_dict(),
            "phase": self.phase,
            "gate": self.gate,
            "suggested_gate": self.suggested_gate,
            "candidate_result": thaw_value(self.candidate_result),
            "norm_results": [result.to_dict() for result in self.norm_results],
            "unknowns": list(self.unknowns),
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "alternatives": thaw_value(self.alternatives),
            "validation_issues": [
                issue.to_dict()
                for issue in self.validation_issues
            ],
            "trace": self.trace.to_dict(),
        }
