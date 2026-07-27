def independent_review_packet(
    *,
    decision="PASS",
    gate_assessment="SUPPORTED",
):
    candidate_sha = "c" * 64
    calculation_sha = "d" * 64
    input_sha = "e" * 64
    supported = (
        ["The candidate preserves its declared semantic gate."]
        if decision == "PASS"
        else []
    )
    unresolved = (
        ["The candidate cannot yet be independently resolved."]
        if decision == "HOLD"
        else []
    )
    refuted = (
        ["The candidate gate is not supported by the supplied material."]
        if decision == "REJECTED"
        else []
    )
    lifecycle = {
        "PASS": "ACCEPTED",
        "HOLD": "RELEVANCE_ASSESSED",
        "REJECTED": "REJECTED",
    }[decision]
    return {
        "review_version": "boris-independent-review/1.0",
        "review_id": "IR-test",
        "reviewer_ref": "O027.runtime-independent-reviewer",
        "producer_ref": "semantic_executor",
        "independence_level": "IND2",
        "method": "adversarial_counterexample_and_gate_cross_check",
        "decision": decision,
        "candidate_gate_assessment": gate_assessment,
        "summary": "Independent review completed.",
        "supported_claims": supported,
        "refuted_claims": refuted,
        "unresolved_issues": unresolved,
        "distortions": [],
        "bindings": {
            "semantic_input_sha256": input_sha,
            "semantic_calculation_sha256": calculation_sha,
            "execution_candidate_sha256": candidate_sha,
            "core_ref": {
                "package_id": "test-core",
                "artifact_version": "1.0",
            },
            "runtime_attestation": {
                "attestation_sha256": "a" * 64,
                "substrate_id": "test-substrate",
            },
        },
        "evidence": {
            "evidence_id": "IR-test",
            "source": "O027.runtime-independent-reviewer",
            "observed_object": (
                f"ExecutionCandidate:{candidate_sha}"
            ),
            "method": (
                "adversarial_counterexample_and_gate_cross_check"
            ),
            "time": "2026-07-27T00:00:00Z",
            "scope": "exact_candidate_and_semantic_calculation",
            "resolution": decision,
            "completeness": (
                ["COMPLETE_FOR_DECLARED_SCOPE"]
                if decision != "HOLD"
                else unresolved
            ),
            "distortions": [],
            "independence": "IND2",
            "supported_or_refuted_objects": [
                f"execution_candidate_sha256:{candidate_sha}",
                f"semantic_calculation_sha256:{calculation_sha}",
                *supported,
                *refuted,
            ],
            "lifecycle_state": lifecycle,
        },
        "state_mutation": False,
    }


def review_llm_payload(
    *,
    decision="PASS",
    gate_assessment="SUPPORTED",
):
    return {
        "decision": decision,
        "candidate_gate_assessment": gate_assessment,
        "summary": "Independent review completed.",
        "supported_claims": (
            ["The candidate preserves its declared semantic gate."]
            if decision == "PASS"
            else []
        ),
        "refuted_claims": (
            ["The candidate gate is materially unsupported."]
            if decision == "REJECTED"
            else []
        ),
        "unresolved_issues": (
            ["The candidate cannot yet be independently resolved."]
            if decision == "HOLD"
            else []
        ),
        "distortions": [],
    }
