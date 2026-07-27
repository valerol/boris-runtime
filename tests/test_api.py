from fastapi.testclient import TestClient

import api.app as app_module
from api.models import RuntimeExecutionRequest, RuntimeFrameRequest
from application.context_provider import CoreSurfaceUnavailable
from application.continuation import IncompleteOperatorResolution
from application.execution import (
    OperatorAcceptanceUnavailable,
    SemanticInputCompilationError,
)
from application.host_executor import HostWorkOrderAlreadyConsumed


client = TestClient(app_module.app)


class FakeContextProvider:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def frame(self, user_input, session_id=None):
        self.calls.append((user_input, session_id))
        if self.error:
            raise self.error
        return frame_packet(user_input, session_id)


class FakeExecutionService:
    def __init__(self, error=None, gate="HOLD", empty_candidate=False):
        self.error = error
        self.gate = gate
        self.empty_candidate = empty_candidate
        self.calls = []
        self.host_calls = []

    def execute(
        self,
        user_input,
        session_id=None,
        context=None,
        resume=None,
    ):
        if resume is None:
            self.calls.append((user_input, session_id, context))
        else:
            self.calls.append(
                (user_input, session_id, context, resume)
            )
        if self.error:
            raise self.error
        packet = execution_packet(session_id, gate=self.gate)
        if self.empty_candidate:
            packet["candidate_result"] = None
            packet["candidate_unavailable_reason"] = (
                "No conditional candidate is available."
            )
        return packet

    def prepare_host(
        self,
        user_input,
        session_id=None,
        context=None,
        resume=None,
    ):
        self.host_calls.append(
            ("prepare", user_input, session_id, context, resume)
        )
        if self.error:
            raise self.error
        return host_work_order_packet(session_id)

    def submit_host(
        self,
        *,
        work_order_id,
        work_order_token,
        semantic_input=None,
        semantic_result=None,
        session_id=None,
    ):
        self.host_calls.append((
            "submit",
            work_order_id,
            work_order_token,
            semantic_input,
            semantic_result,
            session_id,
        ))
        if self.error:
            raise self.error
        if semantic_input is not None:
            return host_work_order_packet(
                session_id,
                work_order_type="CALCULATION",
            )
        packet = execution_packet(session_id, gate="PASS")
        packet["semantic_provider"] = "CHATGPT_HOST_ONLY"
        packet["host_work_order_id"] = work_order_id
        return packet


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "boris-runtime",
        "api": "fastapi",
    }


def test_runtime_request_schemas_do_not_expose_mode():
    assert "mode" not in RuntimeFrameRequest.model_json_schema()["properties"]
    assert "mode" not in RuntimeExecutionRequest.model_json_schema()["properties"]
    assert "operation" in (
        RuntimeExecutionRequest.model_json_schema()["properties"]
    )


def test_runtime_execute_prepare_and_submit_route_one_host_work_order(
    monkeypatch,
):
    service = FakeExecutionService()
    monkeypatch.setattr(app_module, "execution_service", service)

    prepared = client.post(
        "/runtime/execute",
        json={
            "operation": "prepare",
            "input": "Explain BOIS Runtime",
            "session_id": "host-api",
        },
    )

    assert prepared.status_code == 200
    work_order = prepared.json()
    assert work_order["status"] == "semantic_work_order"
    assert work_order["work_order_type"] == "COMPILATION"
    assert work_order["semantic_provider"] == "CHATGPT_HOST_ONLY"
    assert service.host_calls == [(
        "prepare",
        "Explain BOIS Runtime",
        "host-api",
        {},
        None,
    )]

    compiled = {
        "phenomenon": {"input": "Explain BOIS Runtime", "context": {}},
        "phase": "C03",
        "facts": {},
        "unknowns": [],
        "evidence": [],
        "authority": {},
        "active_layers": [],
        "triggers": [],
        "applicability_scopes": [],
        "requested_norm_refs": [],
        "evaluate_inactive": False,
    }
    calculated = client.post(
        "/runtime/execute",
        json={
            "operation": "submit",
            "session_id": "host-api",
            "work_order_id": work_order["work_order_id"],
            "work_order_token": work_order[
                "submission_contract"
            ]["work_order_token"],
            "semantic_input": compiled,
        },
    )
    assert calculated.status_code == 200
    calculation_order = calculated.json()
    assert calculation_order["work_order_type"] == "CALCULATION"

    submitted = client.post(
        "/runtime/execute",
        json={
            "operation": "submit",
            "session_id": "host-api",
            "work_order_id": calculation_order["work_order_id"],
            "work_order_token": calculation_order[
                "submission_contract"
            ]["work_order_token"],
            "semantic_result": {"candidate_result": {"summary": "Host"}},
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "semantic_candidate"
    assert submitted.json()["semantic_provider"] == "CHATGPT_HOST_ONLY"
    assert service.host_calls[-1] == (
        "submit",
        "work-order-1",
        "hw1.payload.signature",
        None,
        {"candidate_result": {"summary": "Host"}},
        "host-api",
    )


def test_runtime_execute_host_route_validates_contract_and_replay_error(
    monkeypatch,
):
    invalid_prepare = client.post(
        "/runtime/execute",
        json={"operation": "prepare"},
    )
    invalid_submit = client.post(
        "/runtime/execute",
        json={
            "operation": "submit",
            "input": "must remain token-bound",
            "work_order_id": "work-order-1",
            "work_order_token": "hw1.payload.signature",
            "semantic_result": {},
        },
    )
    assert invalid_prepare.status_code == 422
    assert invalid_submit.status_code == 422

    service = FakeExecutionService(
        error=HostWorkOrderAlreadyConsumed(
            "Host work order has already been submitted."
        )
    )
    monkeypatch.setattr(app_module, "execution_service", service)
    replay = client.post(
        "/runtime/execute",
        json={
            "operation": "submit",
            "work_order_id": "work-order-1",
            "work_order_token": "hw1.payload.signature",
            "semantic_result": {},
        },
    )
    assert replay.status_code == 409
    assert replay.json()["error"] == "host_work_order_consumed"


def test_runtime_frame_delegates_to_context_provider(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post(
        "/runtime/frame",
        json={
            "session_id": "frame-test",
            "input": "Explain BOIS Runtime",
            "context": {"source": "pytest"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["packet_version"] == "boris-context/2.0"
    assert body["session_id"] == "frame-test"
    assert body["input"] == "Explain BOIS Runtime"
    assert body["runtime_mode"] == "context_provider"
    assert body["llm_called"] is False
    assert provider.calls == [("Explain BOIS Runtime", "frame-test")]


def test_runtime_frame_generates_session_id(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post("/runtime/frame", json={"input": "hello"})

    assert response.status_code == 200
    assert response.json()["session_id"]
    assert provider.calls[0][1]
    assert len(provider.calls[0]) == 2


def test_runtime_frame_empty_input_returns_validation_error():
    response = client.post("/runtime/frame", json={"input": "   "})

    assert response.status_code == 422


def test_runtime_frame_reports_core_surface_unavailable(monkeypatch):
    provider = FakeContextProvider(
        CoreSurfaceUnavailable("configured package is unavailable")
    )
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post(
        "/runtime/frame",
        json={"session_id": "missing-core", "input": "hello"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "core_surface_unavailable",
        "detail": "configured package is unavailable",
        "session_id": "missing-core",
    }


def test_runtime_frame_execution_error_is_controlled_and_redacted(monkeypatch):
    provider = FakeContextProvider(
        ValueError("runtime exploded with secret-value")
    )
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post(
        "/runtime/frame",
        json={"session_id": "broken", "input": "hello"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "runtime_error",
        "detail": "runtime exploded with [redacted]",
        "session_id": "broken",
    }


def test_runtime_execute_delegates_to_execution_service(monkeypatch):
    service = FakeExecutionService(gate="PASS")
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={
            "session_id": "execution-test",
            "input": "Explain BOIS Runtime",
            "context": {"facts": {"source_supplied": True}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["execution_version"] == "boris-execution/1.0"
    assert body["status"] == "semantic_candidate"
    assert body["gate"] == "PASS"
    assert service.calls == [
        (
            "Explain BOIS Runtime",
            "execution-test",
            {"facts": {"source_supplied": True}},
        )
    ]


def test_runtime_execute_hold_is_a_normal_runtime_result(monkeypatch):
    service = FakeExecutionService(gate="HOLD")
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={"input": "Explain BOIS Runtime"},
    )

    assert response.status_code == 200
    assert response.json()["gate"] == "HOLD"
    assert response.json()["status"] == "semantic_candidate"
    assert response.json()["hold"]["status"] == (
        "operator_input_required"
    )


def test_runtime_execute_accepts_non_operator_hold_without_token(
    monkeypatch,
):
    class NonOperatorHoldService(FakeExecutionService):
        def execute(self, *args, **kwargs):
            packet = super().execute(*args, **kwargs)
            packet["uncertainties"] = [{
                "uncertainty_id": "future-event",
                "description": "A future event remains contingent.",
                "resolution_class": "FUTURE_CONTINGENT",
            }]
            packet["hold"] = {
                "handoff_version": "boris-hold-handoff/1.2",
                "status": "resolution_not_operator_owned",
                "reason": "No unresolved target is operator-owned.",
                "required_operator_input": None,
                "resolution_summary": {
                    "FUTURE_CONTINGENT": [{
                        "uncertainty_id": "future-event",
                    }],
                },
                "resume_count": 0,
            }
            return packet

    monkeypatch.setattr(
        app_module,
        "execution_service",
        NonOperatorHoldService(),
    )

    response = client.post(
        "/runtime/execute",
        json={"input": "Evaluate a conditional route."},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["hold"]["status"] == "resolution_not_operator_owned"
    assert body["hold"]["required_operator_input"] is None
    assert "continuation_token" not in body["hold"]
    assert "expires_at" not in body["hold"]


def test_runtime_execute_preserves_explicit_null_hold_candidate(
    monkeypatch,
):
    service = FakeExecutionService(
        gate="HOLD",
        empty_candidate=True,
    )
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={"input": "Explain BOIS Runtime"},
    )

    assert response.status_code == 200
    assert "candidate_result" in response.json()
    assert response.json()["candidate_result"] is None
    assert response.json()["candidate_unavailable_reason"] == (
        "No conditional candidate is available."
    )


def test_runtime_execute_resume_delegates_signed_handoff(monkeypatch):
    service = FakeExecutionService(gate="PASS")
    monkeypatch.setattr(app_module, "execution_service", service)
    resume = {
        "continuation_token": "v1.payload.signature",
        "operator_input": {
            "statement": "Conditional analysis is allowed.",
            "values": {},
            "resolved_unknowns": ["Permission is unknown."],
        },
    }

    response = client.post(
        "/runtime/execute",
        json={
            "session_id": "execution-test",
            "resume": resume,
        },
    )

    assert response.status_code == 200
    assert service.calls == [
        (None, "execution-test", {}, resume)
    ]


def test_runtime_execute_reports_incomplete_operator_resolution(monkeypatch):
    service = FakeExecutionService(
        error=IncompleteOperatorResolution(
            "Operator input does not close every signed HOLD target."
        )
    )
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={
            "session_id": "execution-test",
            "resume": {
                "continuation_token": "v1.payload.signature",
                "operator_input": "Continue.",
            },
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "incomplete_operator_resolution",
        "detail": (
            "Operator input does not close every signed HOLD target."
        ),
        "session_id": "execution-test",
    }


def test_runtime_execute_requires_input_xor_resume():
    neither = client.post("/runtime/execute", json={})
    both = client.post(
        "/runtime/execute",
        json={
            "input": "Initial input",
            "resume": {
                "continuation_token": "v1.payload.signature",
                "operator_input": "Continue.",
            },
        },
    )

    assert neither.status_code == 422
    assert both.status_code == 422


def test_runtime_execute_missing_acceptance_fails_closed(monkeypatch):
    service = FakeExecutionService(
        error=OperatorAcceptanceUnavailable(
            "Server OperatorAcceptance is not configured."
        )
    )
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={"session_id": "closed", "input": "Explain BOIS Runtime"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "operator_acceptance_unavailable",
        "detail": "Server OperatorAcceptance is not configured.",
        "session_id": "closed",
    }


def test_runtime_execute_invalid_semantic_input_is_controlled(monkeypatch):
    service = FakeExecutionService(
        error=SemanticInputCompilationError(
            "SemanticInput phase is not allowed."
        )
    )
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={"session_id": "invalid", "input": "Explain BOIS Runtime"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "semantic_input_error",
        "detail": "SemanticInput phase is not allowed.",
        "session_id": "invalid",
    }


def test_runtime_execute_unexpected_error_does_not_leak_detail(monkeypatch):
    service = FakeExecutionService(
        error=RuntimeError(
            "failure at /opt/private/core.zip with secret-value"
        )
    )
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setattr(app_module, "execution_service", service)

    response = client.post(
        "/runtime/execute",
        json={"session_id": "broken", "input": "Explain BOIS Runtime"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "runtime_error",
        "detail": "Unexpected Runtime execution failure.",
        "session_id": "broken",
    }


def test_legacy_runtime_routes_are_removed():
    routes = {
        (method, route.path)
        for route in app_module.app.routes
        for method in getattr(route, "methods", ())
    }

    assert ("POST", "/runtime/ask") not in routes
    assert ("POST", "/runtime/reset") not in routes
    assert ("POST", "/run") not in routes
    assert ("POST", "/runtime/execute") in routes
    assert ("POST", "/runtime/frame") in routes
    assert not any(path.startswith("/runtime/session/") for _method, path in routes)


def frame_packet(user_input, session_id):
    return {
        "packet_version": "boris-context/2.0",
        "frame_id": "00000000-0000-4000-8000-000000000001",
        "session_id": session_id,
        "input": user_input,
        "runtime_mode": "context_provider",
        "llm_called": False,
        "bois_frame": {
            "framework": "BOIS",
            "core": {"projection": "core_surface"},
            "input": user_input,
            "constraints": [],
        },
        "sima": {
            "risk": 0.2,
            "uncertainty": 0.2,
            "missing_fields": [],
            "ambiguity_score": 0.1,
        },
        "boris_context": {
            "name": "BORIS",
            "role": "operator/domain specialization",
            "context": {"core_projection": "core_surface"},
            "session": {
                "session_id": session_id,
                "clarification_cycles": 0,
                "max_clarification_cycles": 3,
            },
        },
        "projected_core": [],
        "projection_metadata": {
            "returned_chunks": 0,
            "total_characters": 0,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": [],
        "runtime_generated_prompt": f"## User input\n{user_input}",
    }


def execution_packet(session_id, gate="HOLD"):
    packet = {
        "execution_version": "boris-execution/1.0",
        "session_id": session_id,
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": gate,
        "candidate_result": {"summary": "Candidate only."},
        "norm_results": [],
        "unknowns": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": [
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
    }
    if gate == "HOLD":
        packet["hold"] = {
            "handoff_version": "boris-hold-handoff/1.1",
            "status": "operator_input_required",
            "reason": "Material information remains unresolved.",
            "required_operator_input": {
                "question": "Provide the missing information.",
                "semantic_unknowns": [{
                    "unknown_id": "unknown-001",
                    "description": "Permission is unknown.",
                    "target_path": None,
                    "resolution_kind": "operator_statement",
                    "expected_type": "text",
                    "norm_refs": [],
                    "question": "Resolve: Permission is unknown.",
                }],
                "predicate_inputs": [],
                "response_contract": {
                    "statement": "Plain text.",
                    "values": "Optional object.",
                    "resolved_unknowns": "Optional array.",
                },
            },
            "continuation_token": "v1.payload.signature",
            "expires_at": "2026-07-25T12:00:00+00:00",
            "resume_count": 0,
        }
    return packet


def host_work_order_packet(session_id, work_order_type="COMPILATION"):
    is_compilation = work_order_type == "COMPILATION"
    packet = {
        "work_order_version": "boris-semantic-work-order/0.4",
        "work_order_id": "work-order-1",
        "work_order_type": work_order_type,
        "session_id": session_id,
        "status": "semantic_work_order",
        "semantic_provider": "CHATGPT_HOST_ONLY",
        "minimum_context_window_tokens": (
            0 if is_compilation else 524288
        ),
        "core_ref": {
            "package_id": "BOIS_TEST_CORE",
            "artifact_version": "2.31",
            "source_kind": "directory",
            "archive_sha256": "",
            "content_set_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        },
        "issued_at": "2026-07-26T12:00:00+00:00",
        "expires_at": "2026-07-26T12:15:00+00:00",
        "semantic_prompt": "Calculate the signed semantic work order.",
        "response_schema": {"type": "object"},
        "bindings": {
            "attestation_sha256": "1" * 64,
            **(
                {
                    "semantic_source_sha256": "2" * 64,
                    "compiler_catalog_sha256": "3" * 64,
                }
                if is_compilation
                else {
                    "semantic_input_sha256": "2" * 64,
                    "semantic_view_sha256": "3" * 64,
                }
            ),
            "semantic_prompt_sha256": "4" * 64,
            "response_schema_sha256": "5" * 64,
        },
        "submission_contract": {
            "tool": "boris.execute",
            "required_arguments": [
                "work_order_id",
                "work_order_token",
                (
                    "semantic_input"
                    if is_compilation
                    else "semantic_result"
                ),
            ],
            "work_order_token": "hw1.payload.signature",
        },
        "limitations": [
            "contract_isolation_only",
            "single_process_registry",
        ],
    }
    if not is_compilation:
        packet["phase"] = "C03"
        packet["phase_output_contract"] = {
            "contract_version": "boris-phase-output-contract/1.0",
            "phase": "C03",
            "semantic_output": {
                "primary_object": "CandidateResult",
                "output_objects": ["CandidateResult"],
                "schema_source": (
                    "phase_capsule.required_object_schemas"
                ),
                "schema": {"type": "object"},
            },
            "gate_context": {
                "schema_ref": "schema/test.json#/$defs/C03",
                "runtime_owned": True,
                "included_in_semantic_submission": False,
            },
        }
    return packet
