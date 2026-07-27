from dataclasses import replace

import jsonschema
import pytest

from application.host_executor import (
    HostExecutorUnavailable,
    HostWorkOrderAlreadyConsumed,
    HostWorkOrderCodec,
    HostWorkOrderStateMismatch,
    InMemoryHostWorkOrderRegistry,
    InvalidHostWorkOrder,
)
from semantic_executor import (
    SemanticInput,
    SemanticViewBuilder,
)
from tests.test_execution import (
    StaticAcceptanceProvider,
    StaticCompatibilityVerifier,
    StaticSurfaceProvider,
    build_service,
    compiler_payload,
)
from application.execution import SemanticInputCompilationError
from tests.test_semantic_executor import (
    AutoCalculator,
    build_accepted_compatibility,
    build_surface,
)


def test_host_prepare_and_submit_use_two_signed_validated_work_orders(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, adapter, api_calculator, events = build_service(
        source,
        surface=surface,
    )
    codec, _registry = configure_host_executor(service)

    compilation_order = service.prepare_host(
        "Explain the runtime.",
        session_id="host-session",
    )

    assert compilation_order["work_order_version"] == (
        "boris-semantic-work-order/0.5"
    )
    assert compilation_order["work_order_type"] == "COMPILATION"
    assert compilation_order["status"] == "semantic_work_order"
    assert compilation_order["semantic_provider"] == "CHATGPT_HOST_ONLY"
    assert compilation_order["resume_count"] == 0
    assert "phase" not in compilation_order
    assert compilation_order["minimum_context_window_tokens"] == 0
    assert "host_model_identity_not_attested" in (
        compilation_order["limitations"]
    )
    assert "SEMANTIC_INPUT_COMPILER_DATA" in (
        compilation_order["semantic_prompt"]
    )
    assert "operation" not in compilation_order["submission_contract"]
    assert "operation" not in compilation_order[
        "submission_contract"
    ]["required_arguments"]
    assert compilation_order["submission_contract"][
        "work_order_token"
    ].startswith("hw1.")
    assert set(compilation_order["bindings"]) == {
        "attestation_sha256",
        "semantic_source_sha256",
        "compiler_catalog_sha256",
        "semantic_prompt_sha256",
        "response_schema_sha256",
    }
    assert all(
        len(value) == 64
        for value in compilation_order["bindings"].values()
    )
    assert api_calculator.calls == 0
    assert len(adapter.calls) == 0
    assert events == [
        "core_surface",
        "operator_acceptance",
        "runtime_compatibility",
    ]

    jsonschema.validate(
        source,
        compilation_order["response_schema"],
    )
    work_order = service.submit_host(
        work_order_id=compilation_order["work_order_id"],
        work_order_token=compilation_order["submission_contract"][
            "work_order_token"
        ],
        semantic_input=source,
        session_id="host-session",
    )
    assert work_order["work_order_type"] == "CALCULATION"
    assert work_order["resume_count"] == 0
    assert work_order["phase"] == "C03"
    assert work_order["phase_output_contract"][
        "semantic_output"
    ]["primary_object"] == "CandidateResult"
    assert work_order["response_schema"]["properties"][
        "candidate_result"
    ]["required"] == ["status"]
    assert "SEMANTIC_CALCULATION_DATA" in work_order["semantic_prompt"]
    assert "semantic_result" in work_order["submission_contract"][
        "required_arguments"
    ]
    assert len(adapter.calls) == 0

    semantic_result = valid_semantic_result(surface, source)
    jsonschema.validate(
        semantic_result,
        work_order["response_schema"],
    )
    result = service.submit_host(
        work_order_id=work_order["work_order_id"],
        work_order_token=work_order["submission_contract"][
            "work_order_token"
        ],
        semantic_result=semantic_result,
        session_id="host-session",
    )

    assert result["status"] == "semantic_candidate"
    assert result["semantic_provider"] == "CHATGPT_HOST_ONLY"
    assert result["host_work_order_id"] == work_order["work_order_id"]
    assert result["gate"] == "PASS"
    assert result["candidate_result"] == {
        "status": "CANDIDATE_ONLY"
    }
    assert "host_context_capacity_not_attested" in (
        result["limitations"]
    )
    assert api_calculator.calls == 0
    assert codec.verify(
        work_order["submission_contract"]["work_order_token"]
    )["semantic_view_sha256"] == work_order["bindings"][
        "semantic_view_sha256"
    ]


def test_host_work_order_is_single_use(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    work_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="single-use",
    )
    arguments = {
        "work_order_id": work_order["work_order_id"],
        "work_order_token": work_order["submission_contract"][
            "work_order_token"
        ],
        "semantic_result": valid_semantic_result(surface, source),
        "session_id": "single-use",
    }

    service.submit_host(**arguments)

    with pytest.raises(
        HostWorkOrderAlreadyConsumed,
        match="already been submitted",
    ):
        service.submit_host(**arguments)


def test_invalid_host_token_does_not_consume_valid_work_order(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    work_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="tamper-test",
    )
    token = work_order["submission_contract"]["work_order_token"]
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(InvalidHostWorkOrder):
        service.submit_host(
            work_order_id=work_order["work_order_id"],
            work_order_token=token[:-1] + replacement,
            semantic_result=valid_semantic_result(surface, source),
            session_id="tamper-test",
        )

    result = service.submit_host(
        work_order_id=work_order["work_order_id"],
        work_order_token=token,
        semantic_result=valid_semantic_result(surface, source),
        session_id="tamper-test",
    )
    assert result["gate"] == "PASS"


def test_host_submission_rejects_wrong_session_and_current_scope(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    wrong_session_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="bound-session",
    )

    with pytest.raises(
        HostWorkOrderStateMismatch,
        match="session_id",
    ):
        service.submit_host(
            work_order_id=wrong_session_order["work_order_id"],
            work_order_token=wrong_session_order["submission_contract"][
                "work_order_token"
            ],
            semantic_result=valid_semantic_result(surface, source),
            session_id="other-session",
        )

    scope_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="scope-session",
    )
    changed_surface = replace(
        surface,
        manifest_sha256="f" * 64,
    )
    changed_compatibility = build_accepted_compatibility(
        changed_surface
    )
    service.surface_provider = StaticSurfaceProvider(changed_surface)
    service.acceptance_provider = StaticAcceptanceProvider(
        changed_compatibility.operator_acceptance
    )
    service.compatibility_verifier = StaticCompatibilityVerifier(
        changed_compatibility
    )

    with pytest.raises(
        HostWorkOrderStateMismatch,
        match="no longer matches",
    ):
        service.submit_host(
            work_order_id=scope_order["work_order_id"],
            work_order_token=scope_order["submission_contract"][
                "work_order_token"
            ],
            semantic_result=valid_semantic_result(surface, source),
            session_id="scope-session",
        )


def test_invalid_phase_output_receives_one_hold_correction_and_can_be_accepted(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    work_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="invalid-result",
    )
    arguments = {
        "work_order_id": work_order["work_order_id"],
        "work_order_token": work_order["submission_contract"][
            "work_order_token"
        ],
        "session_id": "invalid-result",
    }

    correction = service.submit_host(
        semantic_result={"candidate_result": {}},
        **arguments,
    )

    assert correction["gate"] == "HOLD"
    assert correction["work_order_type"] == "CALCULATION"
    assert correction["correction"]["correction_count"] == 1
    assert correction["correction"]["previous_work_order_id"] == (
        work_order["work_order_id"]
    )
    assert correction["correction"]["return_state"] == "C03"
    assert correction["correction"]["issues"] == [{
        "code": "PHASE_OUTPUT_REQUIRED_FIELDS_MISSING",
        "path": "$.candidate_result",
        "received": [],
        "expected": "required fields ['status']",
        "instruction": (
            "Add the missing canonical CandidateResult fields: ['status']."
        ),
    }]
    assert "HOLD_CORRECTION" in correction["semantic_prompt"]
    assert "not canonical REPAIR" in correction["semantic_prompt"]

    result = service.submit_host(
        work_order_id=correction["work_order_id"],
        work_order_token=correction["submission_contract"][
            "work_order_token"
        ],
        semantic_result=valid_semantic_result(surface, source),
        session_id="invalid-result",
    )
    assert result["gate"] == "PASS"

    with pytest.raises(HostWorkOrderAlreadyConsumed):
        service.submit_host(
            semantic_result=valid_semantic_result(surface, source),
            **arguments,
        )


def test_invalid_hold_correction_preserves_hold_without_third_attempt(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "c" * 32)
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    work_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="invalid-correction",
    )
    correction = service.submit_host(
        work_order_id=work_order["work_order_id"],
        work_order_token=work_order["submission_contract"][
            "work_order_token"
        ],
        semantic_result={"candidate_result": {}},
        session_id="invalid-correction",
    )

    hold = service.submit_host(
        work_order_id=correction["work_order_id"],
        work_order_token=correction["submission_contract"][
            "work_order_token"
        ],
        semantic_result={"candidate_result": {}},
        session_id="invalid-correction",
    )

    assert hold["gate"] == "HOLD"
    assert hold["candidate_result"] is None
    assert hold["hold"]["status"] == "operator_input_required"
    assert hold["hold"]["resolution_owner"] == "OPERATOR"
    assert hold["hold"]["required_operator_input"] is not None
    assert hold["hold"]["handoff_version"] == (
        "boris-hold-handoff/1.4"
    )
    assert hold["hold"]["hold_record"]["return_state"] == "C03"
    assert hold["hold"]["blocking_precondition"][
        "resolution_options"
    ] == ["CHANGE_SCOPE", "TERMINATE_CYCLE"]
    assert hold["hold"]["required_operator_input"][
        "system_targets"
    ][0]["kind"] == "SYSTEM_COMPLIANCE_HOLD"
    assert hold["hold"]["continuation_token"].startswith("v1.")
    assert "work_order_id" not in hold
    assert "submission_contract" not in hold

    terminated = service.prepare_host(
        session_id="invalid-correction",
        resume={
            "continuation_token": hold["hold"][
                "continuation_token"
            ],
            "operator_input": {
                "resolution_mode": "TERMINATE_CYCLE",
                "statement": (
                    "Terminate the invalid submission cycle."
                ),
                "values": {},
                "resolved_unknowns": [],
            },
        },
    )

    assert terminated["gate"] == "HOLD"
    assert terminated["hold"]["status"] == "operator_terminated"
    assert terminated["candidate_result"]["operator_decision"][
        "resolution_mode"
    ] == "TERMINATE_CYCLE"


def test_malformed_host_compilation_is_rejected_and_consumes_attempt(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(source)
    configure_host_executor(service)
    work_order = service.prepare_host(
        "Explain the runtime.",
        session_id="invalid-compilation",
    )
    arguments = {
        "work_order_id": work_order["work_order_id"],
        "work_order_token": work_order["submission_contract"][
            "work_order_token"
        ],
        "session_id": "invalid-compilation",
    }
    malformed = dict(source)
    malformed["phase"] = "C99"

    with pytest.raises(
        SemanticInputCompilationError,
        match="not allowed by the verified Core Surface",
    ):
        service.submit_host(
            semantic_input=malformed,
            **arguments,
        )

    with pytest.raises(HostWorkOrderAlreadyConsumed):
        service.submit_host(
            semantic_input=source,
            **arguments,
        )


def test_host_only_route_never_constructs_api_adapter(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)

    def reject_api_adapter():
        raise AssertionError("Host-only route constructed the API adapter.")

    service.llm_adapter_factory = reject_api_adapter
    calculation_order = prepare_calculation_work_order(
        service,
        source,
        "Explain the runtime.",
        session_id="zero-api",
    )
    result = service.submit_host(
        work_order_id=calculation_order["work_order_id"],
        work_order_token=calculation_order["submission_contract"][
            "work_order_token"
        ],
        semantic_result=valid_semantic_result(surface, source),
        session_id="zero-api",
    )

    assert result["gate"] == "PASS"
    assert result["semantic_provider"] == "CHATGPT_HOST_ONLY"


def test_host_work_order_expires_and_requires_a_dedicated_secret(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    now = [1000]
    codec = HostWorkOrderCodec(
        "e" * 32,
        ttl_seconds=60,
        clock=lambda: now[0],
    )
    service.host_work_order_codec_factory = lambda: codec
    service.host_work_order_registry = InMemoryHostWorkOrderRegistry(
        clock=lambda: now[0],
    )
    work_order = service.prepare_host(
        "Explain the runtime.",
        session_id="expiry-test",
    )
    now[0] = 1060

    with pytest.raises(InvalidHostWorkOrder, match="expired"):
        service.submit_host(
            work_order_id=work_order["work_order_id"],
            work_order_token=work_order["submission_contract"][
                "work_order_token"
            ],
            semantic_input=source,
            session_id="expiry-test",
        )

    monkeypatch.delenv("BORIS_HOST_EXECUTOR_SECRET", raising=False)
    with pytest.raises(HostExecutorUnavailable, match="at least 32 bytes"):
        HostWorkOrderCodec.from_environment()


def test_host_prepare_accepts_signed_hold_resume_without_recompiling(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "r" * 32)
    surface = build_surface()
    text = "Evaluate an action."
    context = {
        "unknowns": ["authorization.granted remains unknown."],
    }
    source = compiler_payload(
        text,
        context,
        triggers=["action"],
    )
    service, adapter, api_calculator, events = build_service(
        source,
        surface=surface,
    )
    codec, registry = configure_host_executor(service)
    first = service.execute(
        text,
        session_id="host-resume",
        context=context,
    )

    work_order = service.prepare_host(
        session_id="host-resume",
        resume={
            "continuation_token": first["hold"][
                "continuation_token"
            ],
            "operator_input": {
                "resolution_mode": "PROVIDE_INFORMATION",
                "statement": "Authorization is confirmed.",
                "values": {"authorization.granted": True},
                "resolved_unknowns": [],
            },
        },
    )

    assert work_order["resume_count"] == 1
    assert codec.verify(
        work_order["submission_contract"]["work_order_token"]
    )["resume_count"] == 1
    state = registry._entries[work_order["work_order_id"]]
    view = SemanticViewBuilder().build(
        surface,
        state.semantic_input,
        operator_decision=state.operator_decision,
    )
    semantic_result = AutoCalculator().calculate(
        view,
        state.semantic_input,
    )
    result = service.submit_host(
        work_order_id=work_order["work_order_id"],
        work_order_token=work_order["submission_contract"][
            "work_order_token"
        ],
        semantic_result=semantic_result,
        session_id="host-resume",
    )

    assert first["gate"] == "HOLD"
    assert result["gate"] == "PASS"
    assert result["semantic_provider"] == "CHATGPT_HOST_ONLY"
    assert len(adapter.calls) == 1
    assert api_calculator.calls == 1
    assert events.count("semantic_input_compiler") == 1


def test_host_conditional_resume_preserves_hold_state_and_rechecks_gate(
    monkeypatch,
):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    monkeypatch.setenv("BORIS_CONTINUATION_SECRET", "q" * 32)
    surface = build_surface()
    text = "Evaluate a bounded policy question."
    description = "A material historical fact is not available."
    context = {"unknowns": [description]}
    source = compiler_payload(text, context)
    service, _adapter, calculator, events = build_service(
        source,
        surface=surface,
    )
    calculator.uncertainties = [
        {
            "uncertainty_id": "historical-fact",
            "description": description,
            "resolution_class": "OPERATOR_INPUT",
            "target_path": None,
            "norm_refs": [],
            "core_refs": [],
            "operator_question": (
                "Provide the historical fact if it is available."
            ),
        }
    ]
    _codec, registry = configure_host_executor(service)
    first = service.execute(
        text,
        session_id="host-conditional-resume",
        context=context,
    )

    work_order = service.prepare_host(
        session_id="host-conditional-resume",
        resume={
            "continuation_token": first["hold"][
                "continuation_token"
            ],
            "operator_input": {
                "resolution_mode": "ALLOW_CONDITIONAL_PROCEEDING",
                "statement": (
                    "Recalculate conditionally and preserve the missing "
                    "fact as a limitation."
                ),
                "values": {},
                "resolved_unknowns": [],
            },
        },
    )

    state = registry._entries[work_order["work_order_id"]]
    assert state.semantic_input.unknowns == (description,)
    assert state.continuation_cycle_id == first["hold"][
        "hold_record"
    ]["cycle_id"]
    assert state.continuation_resolution["gate_forced"] is False
    assert state.continuation_resolution[
        "preserved_hold_record"
    ] == first["hold"]["hold_record"]
    assert state.semantic_input.evidence == ()
    decision = state.operator_decision
    assert decision["resolution_mode"] == (
        "ALLOW_CONDITIONAL_PROCEEDING"
    )
    assert decision["unknowns_preserved"] == ["historical-fact"]
    assert decision["state_hash"] == first["hold"][
        "hold_record"
    ]["state_hash"]

    view = SemanticViewBuilder().build(
        surface,
        state.semantic_input,
        operator_decision=state.operator_decision,
    )
    semantic_result = AutoCalculator().calculate(
        view,
        state.semantic_input,
    )
    result = service.submit_host(
        work_order_id=work_order["work_order_id"],
        work_order_token=work_order["submission_contract"][
            "work_order_token"
        ],
        semantic_result=semantic_result,
        session_id="host-conditional-resume",
    )

    assert result["gate"] == "PASS"
    assert result["phase"] == first["hold"]["hold_record"][
        "return_state"
    ]
    assert result["unknowns"] == [description]
    assert "developer_trace" not in result
    assert events.count("semantic_input_compiler") == 1


def configure_host_executor(service):
    codec = HostWorkOrderCodec("h" * 32)
    registry = InMemoryHostWorkOrderRegistry()
    service.host_work_order_codec_factory = lambda: codec
    service.host_work_order_registry = registry
    return codec, registry


def prepare_calculation_work_order(
    service,
    semantic_input,
    user_input,
    *,
    session_id,
):
    compilation_order = service.prepare_host(
        user_input,
        session_id=session_id,
    )
    return service.submit_host(
        work_order_id=compilation_order["work_order_id"],
        work_order_token=compilation_order["submission_contract"][
            "work_order_token"
        ],
        semantic_input=semantic_input,
        session_id=session_id,
    )


def valid_semantic_result(surface, payload):
    semantic_input = SemanticInput(
        phenomenon=payload["phenomenon"],
        phase=payload["phase"],
        facts=payload["facts"],
        unknowns=tuple(payload["unknowns"]),
        evidence=tuple(payload["evidence"]),
        authority=payload["authority"],
        active_layers=tuple(payload["active_layers"]),
        triggers=tuple(payload["triggers"]),
        applicability_scopes=tuple(
            payload["applicability_scopes"]
        ),
        requested_norm_refs=tuple(payload["requested_norm_refs"]),
        evaluate_inactive=payload["evaluate_inactive"],
    )
    view = SemanticViewBuilder().build(surface, semantic_input)
    return AutoCalculator().calculate(view, semantic_input)
