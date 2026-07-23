import json

import pytest

from core_surface import CoreSurface
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeAttestationError,
    RuntimeCompatibilityVerifier,
    RuntimeContractError,
)


def test_compatible_contract_produces_exact_accepted_attestation():
    surface = build_contract_surface()
    acceptance = accepted_for(surface)

    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=acceptance,
    )

    assert result.eligible_for_semantic_execution is True
    assert result.attestation.spec_check_status == "PASS"
    assert result.attestation.activation_status == "ACCEPTED_IN_SCOPE"
    assert result.attestation.archive_sha256 == surface.archive_sha256
    assert dict(result.attestation.loaded_component_hashes) == {}
    result.require_semantic_evaluation(surface)


def test_future_version_is_accepted_by_contract_capability_not_number():
    surface = build_contract_surface(version="9.0")

    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=accepted_for(surface),
    )

    assert result.attestation.artifact_version == "9.0"
    assert result.eligible_for_semantic_execution is True


def test_unknown_required_check_holds_future_contract():
    surface = build_contract_surface(
        version="9.0",
        required_checks=["UNSUPPORTED_FUTURE_CHECK"],
    )

    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=accepted_for(surface),
    )

    assert result.attestation.spec_check_status == "HOLD"
    assert result.attestation.activation_status == "HOLD"
    assert result.eligible_for_semantic_execution is False
    assert any(
        check.check_id == "UNSUPPORTED_FUTURE_CHECK"
        and check.status == "HOLD"
        for check in result.checks
    )


def test_default_operator_decision_holds_semantic_execution():
    surface = build_contract_surface()

    result = RuntimeCompatibilityVerifier().verify(surface)

    assert result.attestation.spec_check_status == "PASS"
    assert result.attestation.activation_status == "HOLD"
    assert result.eligible_for_semantic_execution is False
    with pytest.raises(RuntimeAttestationError, match="does not permit"):
        result.require_semantic_evaluation(surface)


def test_contract_identity_mismatch_is_rejected():
    surface = build_contract_surface(schema_version="9.0")

    with pytest.raises(RuntimeContractError, match="artifact_version"):
        RuntimeCompatibilityVerifier().verify(surface)


def test_directory_source_cannot_issue_archive_attestation():
    surface = build_contract_surface(source_kind="directory")

    with pytest.raises(RuntimeContractError, match="pattern"):
        RuntimeCompatibilityVerifier().verify(surface)


def test_operator_acceptance_must_match_exact_archive():
    surface = build_contract_surface()
    acceptance = accepted_for(surface)
    acceptance = OperatorAcceptance(
        package_id=acceptance.package_id,
        artifact_version=acceptance.artifact_version,
        archive_sha256="f" * 64,
        manifest_sha256=acceptance.manifest_sha256,
        operator_role=acceptance.operator_role,
        decision=acceptance.decision,
        accepted_scope=acceptance.accepted_scope,
        decision_time=acceptance.decision_time,
        revocation_route=acceptance.revocation_route,
    )

    with pytest.raises(RuntimeContractError, match="exact loaded archive"):
        RuntimeCompatibilityVerifier().verify(
            surface,
            operator_acceptance=acceptance,
        )


def accepted_for(surface):
    return OperatorAcceptance(
        package_id=surface.package_id,
        artifact_version=surface.artifact_version,
        archive_sha256=surface.archive_sha256,
        manifest_sha256=surface.manifest_sha256,
        operator_role="TEST_OPERATOR",
        decision="ACCEPT",
        accepted_scope=("semantic_evaluation",),
        decision_time="2026-07-23T00:00:00+00:00",
        revocation_route="Replace the test acceptance.",
    )


def build_contract_surface(
    *,
    version="2.18",
    schema_version=None,
    source_kind="archive",
    required_checks=None,
):
    package_id = f"BOIS_TEST_CORE_{version.replace('.', '_')}"
    contract_version = schema_version or version
    schemas = runtime_schemas(package_id, contract_version)
    payloads = {
        "schema/RUNTIME_SCHEMAS.json": json_bytes(schemas),
        "runtime/RUNTIME_TEMPLATES.json": json_bytes({
            "package_id": package_id,
            "artifact_version": version,
            "status": "UNFILLED_TEMPLATES_NOT_ATTESTATIONS",
            "operator_acceptance": unfilled_template(
                schemas,
                "OperatorAcceptance",
            ),
            "runtime_attestation": unfilled_template(
                schemas,
                "RuntimeAttestation",
            ),
            "substrate_declaration": unfilled_template(
                schemas,
                "SubstrateDeclaration",
            ),
        }),
        "assurance/VALIDATION_SPEC.json": json_bytes({
            "package_id": package_id,
            "artifact_version": version,
            "status": "DECLARATIVE_SPECIFICATION_NOT_EXECUTION",
            "prohibited_claims": ["RUNTIME_COMPATIBILITY_PASS"],
            "required_checks": required_checks or [
                "RUNTIME_TEMPLATES_MATCH_SCHEMAS"
            ],
        }),
    }
    return CoreSurface(
        source="synthetic.zip",
        source_kind=source_kind,
        package_id=package_id,
        artifact_version=version,
        status="INTERNAL_CANDIDATE",
        release_flavor="PASSIVE_DATA_ONLY",
        purpose="evaluation",
        root_directory="bois-test-core",
        archive_sha256="a" * 64 if source_kind == "archive" else None,
        content_set_sha256="b" * 64,
        manifest_sha256="c" * 64,
        components=(),
        loading_order=(),
        machine_canon={
            "executable": False,
            "predicate_dsl": {
                "truth_values": ["TRUE", "FALSE", "UNKNOWN"],
                "missing_path_result": "UNKNOWN",
                "unknown_material_result": "HOLD",
                "operators": {
                    name: {}
                    for name in (
                        "all",
                        "always",
                        "any",
                        "exists",
                        "fact",
                        "gte",
                        "in",
                        "neq",
                        "not",
                        "scope_match",
                        "unique",
                    )
                },
            },
            "deontic_semantics": {
                "operations": {
                    name: "test"
                    for name in (
                        "HOLD",
                        "PERMIT",
                        "PROHIBIT",
                        "REPAIR",
                        "REQUIRE",
                        "STOP",
                    )
                },
            },
            "gate_decision_semantics": {
                "results": ["PASS", "HOLD", "STOP", "REPAIR"],
                "mapping_rules": [
                    {"result": "REPAIR"},
                    {"result": "STOP"},
                    {"result": "HOLD"},
                    {"result": "PASS"},
                ],
            },
        },
        norms_by_layer={},
        _norm_index={},
        _payloads=payloads,
    )


def runtime_schemas(package_id, version):
    identity = {
        "package_id": {"const": package_id},
        "artifact_version": {"const": version},
        "archive_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "manifest_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
    }
    return {
        "package_id": package_id,
        "artifact_version": version,
        "$defs": {
            "OperatorAcceptance": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    **identity,
                    "operator_role": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "enum": ["ACCEPT", "REJECT", "HOLD"],
                    },
                    "accepted_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "decision_time": {"type": "string"},
                    "revocation_route": {"type": "string"},
                },
                "required": [
                    *identity,
                    "operator_role",
                    "decision",
                    "accepted_scope",
                    "decision_time",
                    "revocation_route",
                ],
            },
            "SubstrateDeclaration": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    **identity,
                    "substrate_id": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "data_locations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "failure_modes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    *identity,
                    "substrate_id",
                    "capabilities",
                    "limitations",
                    "data_locations",
                    "failure_modes",
                ],
            },
            "RuntimeAttestation": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    **identity,
                    "substrate_id": {"type": "string"},
                    "loaded_component_hashes": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$",
                        },
                    },
                    "spec_check_status": {
                        "type": "string",
                        "enum": ["PASS", "HOLD", "STOP", "REPAIR", "NOT_RUN"],
                    },
                    "activation_status": {
                        "type": "string",
                        "enum": [
                            "NOT_ACCEPTED",
                            "ACCEPTED_IN_SCOPE",
                            "REJECTED",
                            "HOLD",
                        ],
                    },
                    "limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    *identity,
                    "substrate_id",
                    "loaded_component_hashes",
                    "spec_check_status",
                    "activation_status",
                    "limitations",
                ],
            },
        },
    }


def unfilled_template(schemas, definition_name):
    required = schemas["$defs"][definition_name]["required"]
    return {field: None for field in required}


def json_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
