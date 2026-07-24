from fastapi.testclient import TestClient

import api.app as app_module
from application.context_provider import CoreSurfaceUnavailable


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
    assert provider.calls == [("Explain BOIS Runtime", "frame-test")]


def test_runtime_frame_generates_session_id(monkeypatch):
    provider = FakeContextProvider()
    monkeypatch.setattr(app_module, "context_provider", provider)

    response = client.post("/runtime/frame", json={"input": "hello"})

    assert response.status_code == 200
    assert response.json()["session_id"]
    assert provider.calls[0][1]


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


def test_legacy_runtime_routes_are_removed():
    routes = {
        (method, route.path)
        for route in app_module.app.routes
        for method in getattr(route, "methods", ())
    }

    assert ("POST", "/runtime/ask") not in routes
    assert ("POST", "/runtime/reset") not in routes
    assert ("POST", "/run") not in routes
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
