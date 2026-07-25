from fastapi.testclient import TestClient

import api.app as app_module
from application.context_provider import CoreSurfaceUnavailable
from application.execution import (
    OperatorAcceptanceUnavailable,
    SemanticInputCompilationError,
)


client = TestClient(app_module.app)


class FakeContextProvider:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def frame(self, user_input, session_id=None, mode="default"):
        self.calls.append((user_input, session_id, mode))
        if self.error:
            raise self.error
        return frame_packet(user_input, session_id)


class FakeExecutionService:
    def __init__(self, error=None, gate="HOLD"):
        self.error = error
        self.gate = gate
        self.calls = []

    def execute(
        self,
        user_input,
        session_id=None,
        mode="default",
        context=None,
    ):
        self.calls.append((user_input, session_id, mode, context))
        if self.error:
            raise self.error
        return execution_packet(session_id, gate=self.gate)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "boris-runtime",
        "api": "fastapi",
    }


def test_runtime_frame_delegates_to_context_provider(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post(
        "/runtime/frame",
        json={
            "session_id": "frame-test",
            "input": "Explain BOIS Runtime",
            "mode": "default",
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
    assert provider.calls == [("Explain BOIS Runtime", "frame-test", "default")]


def test_runtime_frame_generates_session_id(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post("/runtime/frame", json={"input": "hello"})

    assert response.status_code == 200
    assert response.json()["session_id"]
    assert provider.calls[0][1]
    assert provider.calls[0][2] == "default"


def test_runtime_frame_empty_input_returns_validation_error():
    response = client.post("/runtime/frame", json={"input": "   "})

    assert response.status_code == 422


def test_runtime_frame_passes_developer_mode(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post(
        "/runtime/frame",
        json={"input": "Explain BOIS", "mode": "developer"},
    )

    assert response.status_code == 200
    assert provider.calls[0][2] == "developer"


def test_runtime_frame_rejects_unknown_mode():
    response = client.post(
        "/runtime/frame",
        json={"input": "Explain BOIS", "mode": "debug"},
    )

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
            "mode": "developer",
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
            "developer",
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
    return {
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
