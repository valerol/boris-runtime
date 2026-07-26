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
    SemanticCalculationError,
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
from tests.test_semantic_executor import (
    AutoCalculator,
    build_accepted_compatibility,
    build_surface,
)


def test_host_prepare_and_submit_use_one_signed_validated_work_order(
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

    work_order = service.prepare_host(
        "Explain the runtime.",
        session_id="host-session",
    )

    assert work_order["work_order_version"] == (
        "boris-semantic-work-order/0.1"
    )
    assert work_order["status"] == "semantic_work_order"
    assert work_order["semantic_provider"] == "CHATGPT_HOST"
    assert work_order["phase"] == "C03"
    assert work_order["minimum_context_window_tokens"] >= 0
    assert "host_model_identity_not_attested" in (
        work_order["limitations"]
    )
    assert "SEMANTIC_CALCULATION_DATA" in work_order["semantic_prompt"]
    assert work_order["submission_contract"]["operation"] == "submit"
    assert work_order["submission_contract"][
        "work_order_token"
    ].startswith("hw1.")
    assert set(work_order["bindings"]) == {
        "attestation_sha256",
        "semantic_input_sha256",
        "semantic_view_sha256",
        "semantic_prompt_sha256",
        "response_schema_sha256",
    }
    assert all(
        len(value) == 64
        for value in work_order["bindings"].values()
    )
    assert api_calculator.calls == 0
    assert len(adapter.calls) == 1
    assert events == [
        "core_surface",
        "operator_acceptance",
        "runtime_compatibility",
        "semantic_input_compiler",
    ]

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
    assert result["semantic_provider"] == "CHATGPT_HOST"
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
    work_order = service.prepare_host(
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
    work_order = service.prepare_host(
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
    wrong_session_order = service.prepare_host(
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

    scope_order = service.prepare_host(
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


def test_malformed_host_result_is_rejected_and_consumes_attempt(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_MODE", "prod")
    surface = build_surface()
    source = compiler_payload("Explain the runtime.")
    service, _adapter, _api_calculator, _events = build_service(
        source,
        surface=surface,
    )
    configure_host_executor(service)
    work_order = service.prepare_host(
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

    with pytest.raises(
        SemanticCalculationError,
        match="fields mismatch",
    ):
        service.submit_host(
            semantic_result={"candidate_result": {}},
            **arguments,
        )

    with pytest.raises(HostWorkOrderAlreadyConsumed):
        service.submit_host(
            semantic_result=valid_semantic_result(surface, source),
            **arguments,
        )


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
            semantic_result=valid_semantic_result(surface, source),
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
    _codec, registry = configure_host_executor(service)
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
                "statement": "Authorization is confirmed.",
                "values": {"authorization.granted": True},
                "resolved_unknowns": [],
            },
        },
    )

    state = registry._entries[work_order["work_order_id"]]
    view = SemanticViewBuilder().build(
        surface,
        state.semantic_input,
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
    assert result["semantic_provider"] == "CHATGPT_HOST"
    assert len(adapter.calls) == 1
    assert api_calculator.calls == 1
    assert events.count("semantic_input_compiler") == 1


def configure_host_executor(service):
    codec = HostWorkOrderCodec("h" * 32)
    registry = InMemoryHostWorkOrderRegistry()
    service.host_work_order_codec_factory = lambda: codec
    service.host_work_order_registry = registry
    return codec, registry


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
