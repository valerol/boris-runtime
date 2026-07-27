from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from semantic_executor.models import freeze_value, thaw_value


REVIEW_VERSION = "boris-independent-review/1.0"
REVIEW_DECISIONS = frozenset({"PASS", "HOLD", "REJECTED"})
GATE_ASSESSMENTS = frozenset({
    "SUPPORTED",
    "INDETERMINATE",
    "UNSUPPORTED",
})
INDEPENDENCE_LEVELS = frozenset({"IND2", "IND3", "IND4"})


@dataclass(frozen=True, slots=True)
class ReviewBindings:
    semantic_input_sha256: str
    semantic_calculation_sha256: str
    execution_candidate_sha256: str
    core_ref: Mapping[str, Any]
    runtime_attestation: Mapping[str, Any]

    def __post_init__(self):
        object.__setattr__(
            self,
            "core_ref",
            freeze_value(dict(self.core_ref)),
        )
        object.__setattr__(
            self,
            "runtime_attestation",
            freeze_value(dict(self.runtime_attestation)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_input_sha256": self.semantic_input_sha256,
            "semantic_calculation_sha256": (
                self.semantic_calculation_sha256
            ),
            "execution_candidate_sha256": (
                self.execution_candidate_sha256
            ),
            "core_ref": thaw_value(self.core_ref),
            "runtime_attestation": thaw_value(
                self.runtime_attestation
            ),
        }


@dataclass(frozen=True, slots=True)
class IndependentReview:
    review_id: str
    reviewer_ref: str
    producer_ref: str
    independence_level: str
    method: str
    decision: str
    candidate_gate_assessment: str
    summary: str
    supported_claims: tuple[str, ...]
    refuted_claims: tuple[str, ...]
    unresolved_issues: tuple[str, ...]
    distortions: tuple[str, ...]
    bindings: ReviewBindings
    evidence: Mapping[str, Any] = field(repr=False)
    state_mutation: bool = False
    review_version: str = REVIEW_VERSION

    def __post_init__(self):
        if self.review_version != REVIEW_VERSION:
            raise ValueError(
                f"Unsupported review version: {self.review_version}"
            )
        if self.decision not in REVIEW_DECISIONS:
            raise ValueError(
                f"Unsupported review decision: {self.decision}"
            )
        if self.candidate_gate_assessment not in GATE_ASSESSMENTS:
            raise ValueError(
                "Unsupported candidate gate assessment: "
                f"{self.candidate_gate_assessment}"
            )
        if self.independence_level not in INDEPENDENCE_LEVELS:
            raise ValueError(
                "IndependentReview requires IND2, IND3, or IND4."
            )
        if self.state_mutation is not False:
            raise ValueError(
                "IndependentReview cannot mutate Runtime state."
            )
        for field_name in (
            "supported_claims",
            "refuted_claims",
            "unresolved_issues",
            "distortions",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(
                    dict.fromkeys(
                        str(item).strip()
                        for item in getattr(self, field_name)
                        if str(item).strip()
                    )
                ),
            )
        object.__setattr__(
            self,
            "evidence",
            freeze_value(dict(self.evidence)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_version": self.review_version,
            "review_id": self.review_id,
            "reviewer_ref": self.reviewer_ref,
            "producer_ref": self.producer_ref,
            "independence_level": self.independence_level,
            "method": self.method,
            "decision": self.decision,
            "candidate_gate_assessment": (
                self.candidate_gate_assessment
            ),
            "summary": self.summary,
            "supported_claims": list(self.supported_claims),
            "refuted_claims": list(self.refuted_claims),
            "unresolved_issues": list(self.unresolved_issues),
            "distortions": list(self.distortions),
            "bindings": self.bindings.to_dict(),
            "evidence": thaw_value(self.evidence),
            "state_mutation": self.state_mutation,
        }
