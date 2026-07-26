import os
import json
import sys
from pathlib import Path

import pytest
import jsonschema

from application.host_executor import (
    HostWorkOrderCodec,
    InMemoryHostWorkOrderRegistry,
    build_host_work_order,
)
from core_surface import load_core_surface
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityVerifier,
    RuntimeProfile,
)
from semantic_executor import (
    PredicateEvaluator,
    SemanticExecutor,
    SemanticInput,
    SemanticViewBuilder,
)
from application.execution import ExecutionService, OperatorAcceptanceProvider
from tests.test_execution import (
    CompilerAdapter,
    RecordingCalculator,
    StaticAcceptanceProvider,
    StaticSurfaceProvider,
    compiler_payload,
)
from tests.test_semantic_executor import AutoCalculator, uncertainty


CURRENT_CORE_PATH = os.getenv("BORIS_CURRENT_CORE_PATH")
pytestmark = pytest.mark.skipif(
    not CURRENT_CORE_PATH or not Path(CURRENT_CORE_PATH).exists(),
    reason=(
        "Set BORIS_CURRENT_CORE_PATH to the highest available Core release "
        "source."
    ),
)


def _runtime_profile(surface):
    return RuntimeProfile(
        semantic_context_window_tokens=int(
            surface.compatibility_contract.get(
                "minimum_context_window_tokens",
                0,
            )
        ),
    )


class RecordingCompatibilityVerifier:
    def __init__(self, events):
        self.events = events

    def verify(self, surface, operator_acceptance=None):
        self.events.append("runtime_compatibility")
        return RuntimeCompatibilityVerifier(
            profile=_runtime_profile(surface),
        ).verify(
            surface,
            operator_acceptance=operator_acceptance,
        )


@pytest.fixture(scope="module")
def current_core_surface():
    return load_core_surface(CURRENT_CORE_PATH, purpose="evaluation")


@pytest.fixture(scope="module")
def current_core_compatibility(current_core_surface):
    acceptance = OperatorAcceptance(
        package_id=current_core_surface.package_id,
        artifact_version=current_core_surface.artifact_version,
        archive_sha256=current_core_surface.archive_sha256 or "",
        manifest_sha256=current_core_surface.manifest_sha256,
        operator_role="CURRENT_CORE_TEST_OPERATOR",
        decision="ACCEPT",
        accepted_scope=("semantic_evaluation",),
        decision_time="2026-07-25T00:00:00+00:00",
        revocation_route="Replace the evaluation-only acceptance record.",
    )
    return RuntimeCompatibilityVerifier(
        profile=_runtime_profile(current_core_surface),
    ).verify(
        current_core_surface,
        operator_acceptance=acceptance,
    )


def test_current_core_builds_host_work_order_for_every_phase(
    current_core_surface,
    current_core_compatibility,
):
    current_core_compatibility.require_semantic_evaluation(
        current_core_surface
    )
    for phase in (f"C{index:02d}" for index in range(12)):
        semantic_input = SemanticInput(
            phenomenon={"input": "Host work-order compatibility check."},
            phase=phase,
        )
        view = SemanticViewBuilder().build(
            current_core_surface,
            semantic_input,
        )
        work_order = build_host_work_order(
            codec=HostWorkOrderCodec("h" * 32),
            registry=InMemoryHostWorkOrderRegistry(),
            semantic_input=semantic_input,
            view=view,
            session_id=f"host-{phase}",
            source_text="Host work-order compatibility check.",
            resume_count=0,
            resumed=False,
            attestation_sha256=(
                current_core_compatibility.attestation_sha256
            ),
        )
        semantic_result = AutoCalculator().calculate(
            view,
            semantic_input,
        )

        jsonschema.validate(
            semantic_result,
            work_order["response_schema"],
        )
        assert work_order["phase"] == phase
        assert work_order["semantic_prompt"]
        assert work_order["submission_contract"]["operation"] == "submit"


def test_current_core_runtime_compatibility_attestation(
    current_core_surface,
    current_core_compatibility,
):
    check_statuses = {
        check.check_id: check.status
        for check in current_core_compatibility.checks
    }
    required_checks = {
        "CORE_SOURCE_INTEGRITY_BINDING",
        "PUBLIC_CORE_CONTRACT_PROJECTION",
        "PREDICATE_DSL_COMPATIBILITY",
        "OPERATOR_LAYER_BOUNDARY",
        "PHASE_COMPLETE_SELECTION",
        "SEMANTIC_CONTEXT_CAPACITY",
    }

    assert current_core_compatibility.eligible_for_semantic_execution is True
    assert current_core_surface.compatibility_contract["source_contract"] == (
        "public-core-v2"
    )
    assert current_core_compatibility.attestation.archive_sha256 == (
        current_core_surface.archive_sha256 or ""
    )
    assert current_core_compatibility.attestation.spec_check_status == "PASS"
    assert current_core_compatibility.attestation.activation_status == (
        "ACCEPTED_IN_SCOPE"
    )
    assert len(current_core_compatibility.attestation_sha256) == 64
    assert required_checks <= set(check_statuses)
    assert {
        check_id: check_statuses[check_id]
        for check_id in required_checks
    } == {
        check_id: "PASS"
        for check_id in required_checks
    }


def test_current_core_canonical_predicate_vectors(current_core_surface):
    evaluator = PredicateEvaluator(current_core_surface)
    vectors = current_core_surface.machine_canon["predicate_dsl"]["test_vectors"]

    actual = {
        vector["id"]: evaluator.evaluate(
            vector["expression"],
            vector["context"],
        )
        for vector in vectors
    }

    assert actual == {
        vector["id"]: vector["expected"]
        for vector in vectors
    }


def test_current_core_typed_norm_predicate_contracts(current_core_surface):
    evaluator = PredicateEvaluator(current_core_surface)
    contract_path = current_core_surface.machine_canon[
        "critical_predicates_ref"
    ]
    contracts = current_core_surface.read_json(contract_path)["contracts"]

    actual = {
        norm_ref: {
            "positive_applicability": evaluator.evaluate(
                contract["applicability"],
                contract["positive"],
            ),
            "positive_violation": evaluator.evaluate(
                contract["violation"],
                contract["positive"],
            ),
            "negative_applicability": evaluator.evaluate(
                contract["applicability"],
                contract["negative"],
            ),
            "negative_violation": evaluator.evaluate(
                contract["violation"],
                contract["negative"],
            ),
        }
        for norm_ref, contract in contracts.items()
    }

    assert actual
    assert actual == {
        norm_ref: {
            "positive_applicability": "TRUE",
            "positive_violation": "FALSE",
            "negative_applicability": "TRUE",
            "negative_violation": "TRUE",
        }
        for norm_ref in contracts
    }


def test_current_core_assurance_gate_vectors(current_core_surface):
    evaluator = PredicateEvaluator(current_core_surface)
    contract_path = current_core_surface.machine_canon["gate_contracts_ref"]
    contracts = current_core_surface.read_json(contract_path)["contracts"]
    fixtures = current_core_surface.read_json(
        "fixtures/GATE_FIXTURES.json"
    )["fixtures"]

    actual = {
        contract["gate_id"]: {
            "negative": evaluator.evaluate(
                contract["predicate"],
                fixtures[contract["gate_id"]]["negative"]["input"]["context"],
            ),
            "positive": evaluator.evaluate(
                contract["predicate"],
                fixtures[contract["gate_id"]]["positive"]["input"]["context"],
            ),
        }
        for contract in contracts
    }

    assert actual == {
        contract["gate_id"]: {
            "negative": "FALSE",
            "positive": "TRUE",
        }
        for contract in contracts
    }


def test_current_core_permission_keeps_machine_type_modality_and_operation_separate(
    current_core_surface,
    current_core_compatibility,
):
    calculator = AutoCalculator(suggested_gate="HOLD")
    executor = SemanticExecutor(
        current_core_surface,
        calculator,
        current_core_compatibility,
    )

    result = executor.execute(SemanticInput(
        phenomenon="Evaluate the machine representation of a permission.",
        phase="C03",
        requested_norm_refs=("N-GEN-027",),
    ))

    candidate = calculator.last_view.get_candidate("N-GEN-027")
    assert candidate.norm_type == "MANDATORY_RULE"
    assert candidate.modality == "MAY"
    assert candidate.operation == "PERMIT"
    assert candidate.interpretation_status == "SUPPORTED"
    assert result.gate == "HOLD"
    assert result.core_ref.archive_sha256 == (
        current_core_surface.archive_sha256 or ""
    )


def test_current_core_material_claim_without_evidence_yields_hold_candidate(
    current_core_surface,
    current_core_compatibility,
):
    calculator = AutoCalculator(
        suggested_gate="PASS",
        unknowns=("Evidence for the material claim is missing.",),
        uncertainties=[uncertainty(
            "Evidence for the material claim is missing.",
            resolution_class="OPERATOR_INPUT",
            target_path="evidence",
            norm_refs=("N-GEN-052",),
            operator_question="Provide evidence for the material claim.",
        )],
    )
    executor = SemanticExecutor(
        current_core_surface,
        calculator,
        current_core_compatibility,
    )

    result = executor.execute(SemanticInput(
        phenomenon={"claim": "material", "evidence": []},
        phase="C03",
        facts={"evidence": []},
        triggers=("claim:factual",),
    ))

    selected = set(result.trace.candidate_norm_refs)
    assert "N-GEN-052" in selected
    assert all(
        calculator.last_view.get_candidate(norm_ref).layer == "BASE"
        for norm_ref in selected
    )
    assert result.gate == "HOLD"
    assert any(
        issue.code == "OPERATOR_INPUT_REQUIRED"
        and issue.norm_refs == ("N-GEN-052",)
        for issue in result.validation_issues
    )
    assert result.uncertainties[0].resolution_class == "OPERATOR_INPUT"
    assert result.uncertainties[0].target_path == "evidence"


def test_current_core_external_action_without_authority_yields_hold_candidate(
    current_core_surface,
    current_core_compatibility,
):
    calculator = AutoCalculator(
        suggested_gate="PASS",
        unknowns=("External action authority is missing.",),
        uncertainties=[uncertainty(
            "External action authority is missing.",
            resolution_class="OPERATOR_INPUT",
            target_path="authority_ref",
            norm_refs=("N-O015-01",),
            operator_question="Provide authority for the external action.",
        )],
    )
    executor = SemanticExecutor(
        current_core_surface,
        calculator,
        current_core_compatibility,
    )

    result = executor.execute(SemanticInput(
        phenomenon={"external_action": True, "authority_ref": None},
        phase="C10",
        facts={"external_action": True, "authority_ref": None},
        triggers=("action", "organ:O015"),
    ))

    selected = set(result.trace.candidate_norm_refs)
    assert "N-O015-01" in selected
    assert result.gate == "HOLD"
    assert any(
        issue.code == "OPERATOR_INPUT_REQUIRED"
        and issue.norm_refs == ("N-O015-01",)
        for issue in result.validation_issues
    )
    assert result.uncertainties[0].resolution_class == "OPERATOR_INPUT"
    assert result.uncertainties[0].target_path == "authority_ref"


def test_current_core_acceptance_excludes_unaccepted_layers(
    current_core_surface,
):
    semantic_input = SemanticInput(
        phenomenon="Evaluate the accepted Core layers.",
        phase="C03",
    )
    view = SemanticViewBuilder().build(current_core_surface, semantic_input)
    published_refs = set(
        current_core_surface.phase_contexts["C03"][
            "phase_capsule"
        ]["candidate_norm_ids"]
    )
    expected_refs = {
        norm_ref
        for norm_ref in published_refs
        if current_core_surface.get_norm(norm_ref).layer
        in current_core_surface.accepted_layers
    }
    selected_refs = {
        candidate.norm_ref
        for candidate in view.candidates
    }

    assert selected_refs == expected_refs
    assert selected_refs
    assert all(
        candidate.layer in current_core_surface.accepted_layers
        for candidate in view.candidates
    )
    assert published_refs - selected_refs


def test_current_core_cli_smoke_with_source_operator_acceptance(
    current_core_surface,
    current_core_compatibility,
    tmp_path,
    monkeypatch,
    capsys,
):
    from semantic_executor.__main__ import main

    semantic_input = SemanticInput(
        phenomenon="Evaluate the machine representation of a permission.",
        phase="C03",
        requested_norm_refs=("N-GEN-027",),
    )
    view = SemanticViewBuilder().build(current_core_surface, semantic_input)
    calculation = AutoCalculator(suggested_gate="HOLD").calculate(
        view,
        semantic_input,
    )
    input_path = tmp_path / "semantic-input.json"
    calculation_path = tmp_path / "calculation.json"
    acceptance_path = tmp_path / "operator-acceptance.json"
    input_path.write_text(
        json.dumps(semantic_input.to_prompt_dict()),
        encoding="utf-8",
    )
    calculation_path.write_text(json.dumps(calculation), encoding="utf-8")
    acceptance_path.write_text(
        json.dumps(current_core_compatibility.operator_acceptance.to_dict()),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS",
        str(
            _runtime_profile(
                current_core_surface
            ).semantic_context_window_tokens
        ),
    )
    monkeypatch.setattr(sys, "argv", [
        "semantic_executor",
        str(CURRENT_CORE_PATH),
        str(input_path),
        "--calculation",
        str(calculation_path),
        "--operator-acceptance",
        str(acceptance_path),
    ])

    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "CANDIDATE"
    assert output["execution_candidate"]["gate"] == "HOLD"


def test_current_core_application_execution_route_returns_semantic_candidate(
    current_core_surface,
    current_core_compatibility,
):
    text = "Evaluate the available Core norms for this request."
    events = []
    adapter = CompilerAdapter(compiler_payload(text), events)
    calculator = RecordingCalculator(events, suggested_gate="HOLD")
    service = ExecutionService(
        surface_provider=StaticSurfaceProvider(current_core_surface, events),
        acceptance_provider=StaticAcceptanceProvider(
            current_core_compatibility.operator_acceptance,
            events,
        ),
        compatibility_verifier=RecordingCompatibilityVerifier(events),
        llm_adapter_factory=lambda: adapter,
        calculator_factory=lambda _adapter: calculator,
    )

    result = service.execute(
        text,
        session_id="current-core-application-route",
    )

    assert result["execution_version"] == "boris-execution/1.0"
    assert result["status"] == "semantic_candidate"
    assert result["phase"] == "C03"
    assert result["gate"] == "HOLD"
    assert result["norm_results"]
    assert result["limitations"] == [
        "not_independently_reviewed",
        "not_policy_admitted",
        "no_state_mutation",
        "no_external_action",
    ]
    assert events[:5] == [
        "core_surface",
        "operator_acceptance",
        "runtime_compatibility",
        "semantic_input_compiler",
        "semantic_executor",
    ]


def test_current_core_repository_route_needs_no_acceptance_sidecar(
    current_core_surface,
    monkeypatch,
):
    if current_core_surface.source_kind != "directory":
        pytest.skip("This check applies to a configured Core repository.")
    monkeypatch.delenv("BORIS_OPERATOR_ACCEPTANCE_FILE", raising=False)
    text = "Evaluate the configured Core repository."
    events = []
    adapter = CompilerAdapter(compiler_payload(text), events)
    calculator = RecordingCalculator(events, suggested_gate="HOLD")
    service = ExecutionService(
        surface_provider=StaticSurfaceProvider(current_core_surface, events),
        acceptance_provider=OperatorAcceptanceProvider(),
        compatibility_verifier=RecordingCompatibilityVerifier(events),
        llm_adapter_factory=lambda: adapter,
        calculator_factory=lambda _adapter: calculator,
    )

    result = service.execute(
        text,
        session_id="current-core-repository-route",
    )

    assert result["status"] == "semantic_candidate"
    assert result["gate"] == "HOLD"
    assert events[:4] == [
        "core_surface",
        "runtime_compatibility",
        "semantic_input_compiler",
        "semantic_executor",
    ]
