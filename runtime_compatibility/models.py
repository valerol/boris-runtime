from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from core_surface import CoreSurface
from runtime_compatibility.errors import RuntimeAttestationError


SEMANTIC_EVALUATION_SCOPE = "semantic_evaluation"


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class SubstrateDeclaration:
    package_id: str
    artifact_version: str
    archive_sha256: str
    manifest_sha256: str
    substrate_id: str
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    data_locations: tuple[str, ...]
    failure_modes: tuple[str, ...]
    source_kind: str
    content_set_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "artifact_version": self.artifact_version,
            "archive_sha256": self.archive_sha256,
            "manifest_sha256": self.manifest_sha256,
            "substrate_id": self.substrate_id,
            "capabilities": list(self.capabilities),
            "limitations": list(self.limitations),
            "data_locations": list(self.data_locations),
            "failure_modes": list(self.failure_modes),
            "source_kind": self.source_kind,
            "content_set_sha256": self.content_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class OperatorAcceptance:
    package_id: str
    artifact_version: str
    archive_sha256: str
    manifest_sha256: str
    operator_role: str
    decision: str
    accepted_scope: tuple[str, ...]
    decision_time: str
    revocation_route: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OperatorAcceptance":
        if not isinstance(value, Mapping):
            raise RuntimeAttestationError("OperatorAcceptance must be an object.")
        try:
            return cls(
                package_id=value["package_id"],
                artifact_version=value["artifact_version"],
                archive_sha256=value["archive_sha256"],
                manifest_sha256=value["manifest_sha256"],
                operator_role=value["operator_role"],
                decision=value["decision"],
                accepted_scope=tuple(value["accepted_scope"]),
                decision_time=value["decision_time"],
                revocation_route=value["revocation_route"],
            )
        except (KeyError, TypeError) as exc:
            raise RuntimeAttestationError(
                "OperatorAcceptance lacks required fields or field types."
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "artifact_version": self.artifact_version,
            "archive_sha256": self.archive_sha256,
            "manifest_sha256": self.manifest_sha256,
            "operator_role": self.operator_role,
            "decision": self.decision,
            "accepted_scope": list(self.accepted_scope),
            "decision_time": self.decision_time,
            "revocation_route": self.revocation_route,
        }


@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    package_id: str
    artifact_version: str
    archive_sha256: str
    manifest_sha256: str
    substrate_id: str
    loaded_component_hashes: Mapping[str, str] = field(repr=False)
    spec_check_status: str
    activation_status: str
    limitations: tuple[str, ...]
    source_kind: str
    content_set_sha256: str

    def __post_init__(self):
        object.__setattr__(
            self,
            "loaded_component_hashes",
            MappingProxyType(dict(self.loaded_component_hashes)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "artifact_version": self.artifact_version,
            "archive_sha256": self.archive_sha256,
            "manifest_sha256": self.manifest_sha256,
            "substrate_id": self.substrate_id,
            "loaded_component_hashes": dict(self.loaded_component_hashes),
            "spec_check_status": self.spec_check_status,
            "activation_status": self.activation_status,
            "limitations": list(self.limitations),
            "source_kind": self.source_kind,
            "content_set_sha256": self.content_set_sha256,
        }


@dataclass(frozen=True, slots=True)
class SpecificationCheck:
    check_id: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RuntimeCompatibilityResult:
    declaration: SubstrateDeclaration
    operator_acceptance: OperatorAcceptance
    attestation: RuntimeAttestation
    checks: tuple[SpecificationCheck, ...]
    attestation_sha256: str
    schema_validated: bool

    @property
    def eligible_for_semantic_execution(self) -> bool:
        return (
            self.schema_validated
            and self.attestation.spec_check_status == "PASS"
            and self.attestation.activation_status == "ACCEPTED_IN_SCOPE"
            and self.operator_acceptance.decision == "ACCEPT"
            and SEMANTIC_EVALUATION_SCOPE
            in self.operator_acceptance.accepted_scope
        )

    def require_semantic_evaluation(self, surface: CoreSurface) -> None:
        expected_identity = (
            surface.package_id,
            surface.artifact_version,
            surface.archive_sha256,
            surface.manifest_sha256,
            surface.content_set_sha256,
        )
        actual_identity = (
            self.attestation.package_id,
            self.attestation.artifact_version,
            self.attestation.archive_sha256,
            self.attestation.manifest_sha256,
            self.attestation.content_set_sha256,
        )
        if expected_identity != actual_identity:
            raise RuntimeAttestationError(
                "RuntimeAttestation does not match the loaded Core Surface identity."
            )
        acceptance_identity = (
            self.operator_acceptance.package_id,
            self.operator_acceptance.artifact_version,
            self.operator_acceptance.archive_sha256,
            self.operator_acceptance.manifest_sha256,
        )
        if acceptance_identity != expected_identity[:4]:
            raise RuntimeAttestationError(
                "OperatorAcceptance does not match the loaded Core Surface identity."
            )
        declaration_identity = (
            self.declaration.package_id,
            self.declaration.artifact_version,
            self.declaration.archive_sha256,
            self.declaration.manifest_sha256,
            self.declaration.content_set_sha256,
        )
        if declaration_identity != expected_identity:
            raise RuntimeAttestationError(
                "SubstrateDeclaration does not match the loaded Core Surface identity."
            )
        if self.declaration.source_kind != surface.source_kind:
            raise RuntimeAttestationError(
                "SubstrateDeclaration source_kind does not match the Core Surface."
            )
        if self.declaration.substrate_id != self.attestation.substrate_id:
            raise RuntimeAttestationError(
                "SubstrateDeclaration and RuntimeAttestation substrate IDs differ."
            )
        if self.attestation.source_kind != surface.source_kind:
            raise RuntimeAttestationError(
                "RuntimeAttestation source_kind does not match the Core Surface."
            )
        if dict(self.attestation.loaded_component_hashes) != dict(
            surface.loaded_component_hashes
        ):
            raise RuntimeAttestationError(
                "RuntimeAttestation component hashes do not match the Core Surface."
            )
        if canonical_sha256(self.attestation.to_dict()) != self.attestation_sha256:
            raise RuntimeAttestationError("RuntimeAttestation hash is invalid.")
        if not self.eligible_for_semantic_execution:
            raise RuntimeAttestationError(
                "RuntimeAttestation does not permit semantic_evaluation."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration": self.declaration.to_dict(),
            "operator_acceptance": self.operator_acceptance.to_dict(),
            "attestation": self.attestation.to_dict(),
            "attestation_sha256": self.attestation_sha256,
            "schema_validated": self.schema_validated,
            "eligible_for_semantic_execution": self.eligible_for_semantic_execution,
            "checks": [check.to_dict() for check in self.checks],
        }
