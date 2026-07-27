from dataclasses import replace

import pytest

from application.phase_output import (
    PhaseOutputContract,
    PhaseOutputContractError,
    PhaseOutputValidationError,
)
from semantic_executor import SemanticInput, SemanticViewBuilder
from tests.test_semantic_executor import build_surface


def test_c04_contract_uses_full_question_and_not_gate_projection():
    surface = replace(
        build_surface(),
        phase_contexts={
            "C04": {
                "phase_capsule": {
                    "phase_id": "C04",
                    "required_object_schemas": [{
                        "object_type": "Question",
                        "required_fields": [
                            "question_id",
                            "unknown",
                            "scope",
                            "provenance",
                            "significance",
                            "answer_classes",
                            "discriminating_power",
                            "cost",
                            "risk",
                            "research_route",
                            "lifecycle_state",
                        ],
                        "field_types": {
                            "question_id": ["#/$defs/Identifier"],
                            "unknown": ["string"],
                            "scope": ["string"],
                            "provenance": ["string"],
                            "significance": ["string"],
                            "answer_classes": ["#/$defs/StringOrList"],
                            "discriminating_power": ["string"],
                            "cost": ["#/$defs/CostEstimate"],
                            "risk": ["string"],
                            "research_route": ["string"],
                        },
                        "allowed_states": [
                            "DRAFT",
                            "VALIDATED",
                            "ACTIVE",
                            "HOLD",
                            "CLOSED",
                            "SUPERSEDED",
                        ],
                    }],
                    "gate_contract": {
                        "canonical_object_projection": {
                            "assessment_objects": ["Unknown", "Question"],
                            "output_objects": ["Question"],
                            "primary_object": "Question",
                        },
                        "input_schema_ref": (
                            "schema/GATE_CONTEXT_SCHEMAS.json"
                            "#/$defs/GateContextC04"
                        ),
                    },
                },
            },
        },
    )
    view = SemanticViewBuilder().build(
        surface,
        SemanticInput(
            phenomenon="Qualify the material question.",
            phase="C04",
        ),
    )

    contract = PhaseOutputContract.from_view(view)

    assert contract.primary_object == "Question"
    assert contract.gate_context_schema_ref.endswith("GateContextC04")
    assert contract.to_dict()["gate_context"] == {
        "schema_ref": (
            "schema/GATE_CONTEXT_SCHEMAS.json#/$defs/GateContextC04"
        ),
        "runtime_owned": True,
        "included_in_semantic_submission": False,
    }
    contract.validate({
        "question_id": "Q-001",
        "unknown": "Whether the evidence supports the claimed link.",
        "scope": "Current infrastructure incidents.",
        "provenance": "User-supplied case facts.",
        "significance": "Material to the emergency-law recommendation.",
        "answer_classes": ["SUPPORTED", "NOT_SUPPORTED", "UNKNOWN"],
        "discriminating_power": "Separates response from centralization.",
        "cost": "One independent review.",
        "risk": "Delay in urgent mitigation.",
        "research_route": "Review incident evidence and authority.",
        "lifecycle_state": "DRAFT",
    })

    with pytest.raises(PhaseOutputValidationError) as exc_info:
        contract.validate({
            "central_judgment": "Adopt a narrow law.",
            "recommendation": "Add judicial review.",
        })

    assert {
        issue.code
        for issue in exc_info.value.issues
    } == {
        "PHASE_OUTPUT_REQUIRED_FIELDS_MISSING",
        "PHASE_OUTPUT_UNDECLARED_FIELDS",
    }


def test_phase_contract_fails_closed_for_unsupported_core_definition():
    surface = replace(
        build_surface(),
        phase_contexts={
            "C04": {
                "phase_capsule": {
                    "phase_id": "C04",
                    "required_object_schemas": [{
                        "object_type": "Question",
                        "required_fields": ["question_id"],
                        "field_types": {
                            "question_id": ["#/$defs/FutureIdentifier"],
                        },
                    }],
                    "gate_contract": {
                        "canonical_object_projection": {
                            "output_objects": ["Question"],
                            "primary_object": "Question",
                        },
                        "input_schema_ref": (
                            "schema/GATE_CONTEXT_SCHEMAS.json"
                            "#/$defs/GateContextC04"
                        ),
                    },
                },
            },
        },
    )
    view = SemanticViewBuilder().build(
        surface,
        SemanticInput(
            phenomenon="Qualify the material question.",
            phase="C04",
        ),
    )

    with pytest.raises(
        PhaseOutputContractError,
        match="unsupported definition 'FutureIdentifier'",
    ):
        PhaseOutputContract.from_view(view)
