import json
from dataclasses import replace

import pytest

from core_surface import ComponentRecord, CoreSurface
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


def test_release_contract_attests_normative_and_release_identity_separately():
    surface = build_release_contract_surface()

    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=accepted_for(surface),
    )

    assert result.attestation.spec_check_status == "PASS"
    assert result.attestation.activation_status == "ACCEPTED_IN_SCOPE"
    assert result.eligible_for_semantic_execution is True
    assert dict(result.package_identity) == {
        "manifest_dialect": "release-envelope-v1",
        "release_package_id": "BOIS_TEST_RELEASE_V3",
        "release_version": "3.0",
        "normative_package_id": "BOIS_TEST_NORMATIVE_V2",
        "normative_content_version": "2.0",
    }
    assert set(result.canonical_records) == {
        "substrate_declaration",
        "operator_acceptance",
        "specification_check_receipt",
        "runtime_attestation",
    }
    assert (
        result.canonical_records["runtime_attestation"]["package_id"]
        == "BOIS_TEST_NORMATIVE_V2"
    )
    assert (
        result.canonical_records["runtime_attestation"][
            "loaded_component_hashes"
        ]
        == dict(surface.loaded_component_hashes)
    )
    result.require_semantic_evaluation(surface)


def test_release_embedded_validation_failure_holds_attestation():
    surface = build_release_contract_surface(receipt_result="HOLD")

    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=accepted_for(surface),
    )

    assert result.attestation.spec_check_status == "HOLD"
    assert result.attestation.activation_status == "HOLD"
    assert result.eligible_for_semantic_execution is False
    assert (
        result.canonical_records["runtime_attestation"]["activation_status"]
        == "NOT_ACCEPTED"
    )
    assert (
        result.canonical_records["runtime_attestation"][
            "loaded_component_hashes"
        ]
        == {}
    )


def test_release_identity_change_invalidates_compatibility_result():
    surface = build_release_contract_surface()
    result = RuntimeCompatibilityVerifier().verify(
        surface,
        operator_acceptance=accepted_for(surface),
    )
    changed_surface = replace(surface, release_version="3.1")

    with pytest.raises(RuntimeAttestationError, match="release and normative"):
        result.require_semantic_evaluation(changed_surface)


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


def build_release_contract_surface(*, receipt_result="PASS"):
    package_id = "BOIS_TEST_NORMATIVE_V2"
    artifact_version = "2.0"
    release_package_id = "BOIS_TEST_RELEASE_V3"
    release_version = "3.0"
    schemas = release_runtime_schemas(package_id, artifact_version)
    templates = {
        "package_id": package_id,
        "artifact_version": artifact_version,
        "templates": {
            "OperatorAcceptance": unfilled_template(
                schemas,
                "OperatorAcceptanceDraft",
            ),
            "RuntimeAttestation": unfilled_template(
                schemas,
                "RuntimeAttestationDraft",
            ),
            "SpecificationCheckReceipt": unfilled_template(
                schemas,
                "SpecificationCheckReceiptDraft",
            ),
            "SubstrateDeclaration": unfilled_template(
                schemas,
                "SubstrateDeclarationDraft",
            ),
        },
    }
    payloads = {
        "schema/RUNTIME_SCHEMAS.json": json_bytes(schemas),
        "runtime/RUNTIME_TEMPLATES.json": json_bytes(templates),
        "assurance/VALIDATION_SPEC.json": json_bytes({
            "release_package_id": release_package_id,
            "release_version": release_version,
            "normative_package_id": package_id,
            "normative_content_version": artifact_version,
            "inside_archive_status": "PASSIVE_SPECIFICATION",
            "execution_location": (
                "OUTSIDE_ARCHIVE_VALIDATOR; RESULTS_INSIDE_ARCHIVE"
            ),
            "mandatory_checks": [
                {"check_id": "TEST-RELEASE-CONTRACT"},
            ],
        }),
        "assurance/VALIDATION_RECEIPT.json": json_bytes({
            "checks": {
                "TEST-RELEASE-CONTRACT": {
                    "result": receipt_result,
                    "trace_sha256": "d" * 64,
                },
            },
        }),
        "machine/CORE_CANON.json": json_bytes({"executable": False}),
    }
    component = ComponentRecord(
        path="machine/CORE_CANON.json",
        role="TEST_MACHINE_CANON",
        sha256="e" * 64,
        size_bytes=len(payloads["machine/CORE_CANON.json"]),
    )
    return CoreSurface(
        source="synthetic-release.zip",
        source_kind="archive",
        package_id=package_id,
        artifact_version=artifact_version,
        status="INTERNAL_STATIC_PASS",
        release_flavor="PASSIVE_DATA_ONLY",
        purpose="evaluation",
        root_directory="bois-release-core",
        archive_sha256="a" * 64,
        content_set_sha256="b" * 64,
        manifest_sha256="c" * 64,
        components=(component,),
        loading_order=(component.path,),
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
        manifest_dialect="release-envelope-v1",
        release_package_id=release_package_id,
        release_version=release_version,
        normative_package_id=package_id,
        normative_content_version=artifact_version,
        transport="SINGLE_PASSIVE_DATA_ZIP",
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


def release_runtime_schemas(package_id, version):
    identifier = {
        "type": "string",
        "minLength": 1,
        "pattern": "^[A-Za-z][A-Za-z0-9]*(?:[-_.:][A-Za-z0-9]+)*$",
    }
    string_or_list = {
        "oneOf": [
            {"type": "string", "minLength": 1},
            {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        ],
    }
    acceptance_properties = {
        "record_id": {"$ref": "#/$defs/Identifier"},
        "record_status": {"const": "FINAL"},
        "package_id": {"const": package_id},
        "artifact_version": {"const": version},
        "archive_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "operator_id": {"$ref": "#/$defs/Identifier"},
        "decision": {"enum": ["ACCEPT", "REJECT", "DEFER"]},
        "accepted_scope": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "accepted_components": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
        "decision_time": {"type": "string", "format": "date-time"},
    }
    attestation_properties = {
        "record_id": {"$ref": "#/$defs/Identifier"},
        "record_status": {"const": "FINAL"},
        "package_id": {"const": package_id},
        "artifact_version": {"const": version},
        "archive_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "activation_status": {
            "enum": ["ACCEPTED_IN_SCOPE", "NOT_ACCEPTED", "REJECTED"],
        },
        "spec_check_status": {
            "enum": ["PASS", "HOLD", "STOP", "REPAIR", "NOT_RUN"],
        },
        "loaded_component_hashes": {
            "type": "object",
            "additionalProperties": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
        },
        "substrate_declaration_ref": {"$ref": "#/$defs/Identifier"},
        "operator_acceptance_ref": {"$ref": "#/$defs/Identifier"},
        "specification_check_ref": {"$ref": "#/$defs/Identifier"},
        "limitations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    }
    specification_properties = {
        "record_id": {"$ref": "#/$defs/Identifier"},
        "record_status": {"const": "FINAL"},
        "package_id": {"const": package_id},
        "artifact_version": {"const": version},
        "archive_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "check_status": {
            "enum": ["PASS", "HOLD", "STOP", "REPAIR", "NOT_RUN"],
        },
        "checks": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "check_id": {"type": "string", "minLength": 1},
                    "status": {
                        "enum": ["PASS", "HOLD", "STOP", "REPAIR"],
                    },
                    "evidence_ref": {"type": "string", "minLength": 1},
                },
                "required": ["check_id", "status", "evidence_ref"],
            },
        },
        "completed_at": {"type": "string", "format": "date-time"},
    }
    substrate_properties = {
        "declaration_id": {"$ref": "#/$defs/Identifier"},
        "record_status": {"const": "FINAL"},
        "package_id": {"const": package_id},
        "archive_sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$",
        },
        "owner_ref": {"$ref": "#/$defs/Identifier"},
        "substrate_kind": {"type": "string", "minLength": 1},
        "capabilities": {"$ref": "#/$defs/StringOrList"},
        "limitations": {"$ref": "#/$defs/StringOrList"},
        "security_constraints": {"$ref": "#/$defs/StringOrList"},
        "memory_constraints": {"$ref": "#/$defs/StringOrList"},
        "tool_constraints": {"$ref": "#/$defs/StringOrList"},
        "fallbacks": {"$ref": "#/$defs/StringOrList"},
        "declared_at": {"type": "string", "format": "date-time"},
    }
    definitions = {
        "Identifier": identifier,
        "StringOrList": string_or_list,
        "OperatorAcceptanceFinal": {
            "type": "object",
            "additionalProperties": False,
            "allOf": [{
                "if": {
                    "properties": {"decision": {"const": "ACCEPT"}},
                },
                "then": {
                    "properties": {
                        "accepted_scope": {"minItems": 1},
                        "accepted_components": {"minItems": 1},
                    },
                },
            }],
            "properties": acceptance_properties,
            "required": list(acceptance_properties),
        },
        "RuntimeAttestationFinal": {
            "type": "object",
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "activation_status": {
                                "const": "ACCEPTED_IN_SCOPE",
                            },
                        },
                    },
                    "then": {
                        "properties": {
                            "loaded_component_hashes": {"minProperties": 1},
                            "spec_check_status": {"const": "PASS"},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {
                            "activation_status": {
                                "enum": ["NOT_ACCEPTED", "REJECTED"],
                            },
                        },
                    },
                    "then": {
                        "properties": {
                            "loaded_component_hashes": {"maxProperties": 0},
                        },
                    },
                },
            ],
            "properties": attestation_properties,
            "required": list(attestation_properties),
        },
        "SpecificationCheckReceiptFinal": {
            "type": "object",
            "additionalProperties": False,
            "properties": specification_properties,
            "required": list(specification_properties),
        },
        "SubstrateDeclarationFinal": {
            "type": "object",
            "additionalProperties": False,
            "properties": substrate_properties,
            "required": list(substrate_properties),
        },
    }
    for draft_name, final_name in (
        ("OperatorAcceptanceDraft", "OperatorAcceptanceFinal"),
        ("RuntimeAttestationDraft", "RuntimeAttestationFinal"),
        ("SpecificationCheckReceiptDraft", "SpecificationCheckReceiptFinal"),
        ("SubstrateDeclarationDraft", "SubstrateDeclarationFinal"),
    ):
        definitions[draft_name] = {
            "type": "object",
            "properties": definitions[final_name]["properties"],
            "required": definitions[final_name]["required"],
        }
    return {"$defs": definitions}


def unfilled_template(schemas, definition_name):
    required = schemas["$defs"][definition_name]["required"]
    return {field: None for field in required}


def json_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
