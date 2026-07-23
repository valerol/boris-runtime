import os
import json
import sys
from pathlib import Path

import pytest

from core_surface import load_core_surface
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityVerifier,
)
from semantic_executor import (
    PredicateEvaluator,
    SemanticExecutor,
    SemanticInput,
    SemanticViewBuilder,
)
from tests.test_semantic_executor import AutoCalculator


V218_PATH = os.getenv("BORIS_CORE_V218_PATH")
pytestmark = pytest.mark.skipif(
    not V218_PATH or not Path(V218_PATH).exists(),
    reason="Set BORIS_CORE_V218_PATH to run v2.18 semantic integration tests.",
)


@pytest.fixture(scope="module")
def v218_surface():
    return load_core_surface(V218_PATH, purpose="evaluation")


@pytest.fixture(scope="module")
def v218_compatibility(v218_surface):
    if v218_surface.source_kind != "archive":
        pytest.skip("v2.18 RuntimeAttestation tests require the original ZIP.")
    acceptance = OperatorAcceptance(
        package_id=v218_surface.package_id,
        artifact_version=v218_surface.artifact_version,
        archive_sha256=v218_surface.archive_sha256,
        manifest_sha256=v218_surface.manifest_sha256,
        operator_role="PHASE_4F_TEST_OPERATOR",
        decision="ACCEPT",
        accepted_scope=("semantic_evaluation",),
        decision_time="2026-07-23T00:00:00+00:00",
        revocation_route="Replace the evaluation-only acceptance record.",
    )
    return RuntimeCompatibilityVerifier().verify(
        v218_surface,
        operator_acceptance=acceptance,
    )


def test_v218_runtime_compatibility_attestation(
    v218_surface,
    v218_compatibility,
):
    declared_checks = set(
        v218_surface.read_json(
            "assurance/VALIDATION_SPEC.json"
        )["required_checks"]
    )
    check_statuses = {
        check.check_id: check.status
        for check in v218_compatibility.checks
    }

    assert v218_compatibility.eligible_for_semantic_execution is True
    assert v218_compatibility.attestation.archive_sha256 == (
        v218_surface.archive_sha256
    )
    assert v218_compatibility.attestation.spec_check_status == "PASS"
    assert v218_compatibility.attestation.activation_status == (
        "ACCEPTED_IN_SCOPE"
    )
    assert len(v218_compatibility.attestation_sha256) == 64
    assert declared_checks
    assert {
        check_id: check_statuses[check_id]
        for check_id in declared_checks
    } == {
        check_id: "PASS"
        for check_id in declared_checks
    }


def test_v218_canonical_predicate_vectors(v218_surface):
    evaluator = PredicateEvaluator()
    vectors = v218_surface.machine_canon["predicate_dsl"]["test_vectors"]

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


def test_v218_assurance_gate_vectors(v218_surface):
    evaluator = PredicateEvaluator()
    vectors = v218_surface.read_json("assurance/TEST_VECTORS.json")["tests"]

    actual = {
        vector["test_id"]: {
            "negative": evaluator.evaluate(
                vector["predicate"],
                vector["negative_fixture"],
            ),
            "positive": evaluator.evaluate(
                vector["predicate"],
                vector["positive_fixture"],
            ),
        }
        for vector in vectors
    }

    assert actual == {
        vector["test_id"]: {
            "negative": "FALSE",
            "positive": "TRUE",
        }
        for vector in vectors
    }


def test_v218_permission_keeps_machine_type_modality_and_operation_separate(
    v218_surface,
    v218_compatibility,
):
    calculator = AutoCalculator(suggested_gate="HOLD")
    executor = SemanticExecutor(
        v218_surface,
        calculator,
        v218_compatibility,
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
    assert result.core_ref.archive_sha256 == v218_surface.archive_sha256


def test_v218_material_claim_without_evidence_yields_hold_candidate(
    v218_surface,
    v218_compatibility,
):
    calculator = AutoCalculator(
        suggested_gate="PASS",
        unknowns=("Evidence for the material claim is missing.",),
    )
    executor = SemanticExecutor(
        v218_surface,
        calculator,
        v218_compatibility,
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
        issue.code == "CALCULATION_MATERIAL_UNKNOWNS"
        for issue in result.validation_issues
    )


def test_v218_external_action_without_authority_yields_hold_candidate(
    v218_surface,
    v218_compatibility,
):
    calculator = AutoCalculator(
        suggested_gate="PASS",
        unknowns=("External action authority is missing.",),
    )
    executor = SemanticExecutor(
        v218_surface,
        calculator,
        v218_compatibility,
    )

    result = executor.execute(SemanticInput(
        phenomenon={"external_action": True, "authority_ref": None},
        phase="C10",
        facts={"external_action": True, "authority_ref": None},
        triggers=("action", "organ:O015"),
    ))

    selected = set(result.trace.candidate_norm_refs)
    assert {"N-GEN-017", "N-O015-03"}.issubset(selected)
    assert result.gate == "HOLD"
    assert any(
        issue.code == "CALCULATION_MATERIAL_UNKNOWNS"
        for issue in result.validation_issues
    )


def test_v218_publication_candidate_remains_evaluation_only(
    v218_surface,
    v218_compatibility,
):
    calculator = AutoCalculator(suggested_gate="PASS")
    executor = SemanticExecutor(
        v218_surface,
        calculator,
        v218_compatibility,
    )

    result = executor.execute(SemanticInput(
        phenomenon="Activate T-N-043.",
        phase="PACKAGE_VALIDATION",
        active_layers=("PUBLICATION_CANDIDATE",),
        requested_norm_refs=("T-N-043",),
        evaluate_inactive=True,
    ))

    candidate = calculator.last_view.get_candidate("T-N-043")
    assert candidate.card_status == "CANDIDATE"
    assert candidate.interpretation_status == "EVALUATION_ONLY_INACTIVE"
    assert result.gate == "HOLD"
    assert v218_surface.status == "INTERNAL_CANDIDATE"


def test_v218_cli_smoke_with_exact_operator_acceptance(
    v218_surface,
    v218_compatibility,
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
    view = SemanticViewBuilder().build(v218_surface, semantic_input)
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
        json.dumps(v218_compatibility.operator_acceptance.to_dict()),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "semantic_executor",
        str(V218_PATH),
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
