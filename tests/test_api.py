import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ACTIVE_RUNTIME_PREFIXES = ("api", "core", "llm", "prompt", "protocol", "runtime")


def _matches_active_runtime(module_name):
    return module_name in ACTIVE_RUNTIME_PREFIXES or module_name.startswith(
        tuple(f"{prefix}." for prefix in ACTIVE_RUNTIME_PREFIXES)
    )


@pytest.fixture
def api_context():
    saved_path = list(sys.path)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if _matches_active_runtime(name)
    }

    if str(PROJECT_ROOT) in sys.path:
        sys.path.remove(str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))

    for module_name in list(sys.modules):
        if _matches_active_runtime(module_name):
            sys.modules.pop(module_name, None)

    from api.app import app, runtime_registry

    try:
        yield app, runtime_registry
    finally:
        for module_name in list(sys.modules):
            if _matches_active_runtime(module_name):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def clear_api_state(monkeypatch, runtime_registry):
    runtime_registry.clear()
    monkeypatch.delenv("BOIS_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_health_returns_ok(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "boris-runtime",
        "api": "fastapi",
    }


def test_runtime_ask_valid_input_returns_protocol_shape(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post(
        "/runtime/ask",
        json={
            "session_id": "test",
            "input": "Explain BOIS Runtime v0",
            "mode": "default",
            "context": {"source": "pytest"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "test"
    assert set(body) == {"session_id", "type", "content", "metadata"}
    assert body["type"] in {"ANSWER", "QUESTION", "TOOL_CALL", "GAP"}
    assert isinstance(body["content"], str)
    assert isinstance(body["metadata"], dict)
    assert body["metadata"]["transport"] == {
        "mode": "default",
        "context_received": True,
    }


def test_runtime_ask_generates_session_id(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post("/runtime/ask", json={"input": "hello"})

    assert response.status_code == 200
    assert response.json()["session_id"]


def test_runtime_ask_reuses_runtime_for_same_session_id(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    first = client.post("/runtime/ask", json={"session_id": "same", "input": "hello"})
    runtime = runtime_registry.get("same")
    second = client.post("/runtime/ask", json={"session_id": "same", "input": "next"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert runtime is runtime_registry.get("same")
    assert runtime.session.session_id == "same"


def test_runtime_reset_removes_existing_session(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    ask_response = client.post("/runtime/ask", json={"session_id": "reset-me", "input": "hello"})
    reset_response = client.post("/runtime/reset", json={"session_id": "reset-me"})

    assert ask_response.status_code == 200
    assert reset_response.status_code == 200
    assert reset_response.json() == {"session_id": "reset-me", "reset": True}
    assert runtime_registry.get("reset-me") is None


def test_runtime_session_exists_after_ask(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    ask_response = client.post("/runtime/ask", json={"session_id": "inspect-me", "input": "hello"})
    session_response = client.get("/runtime/session/inspect-me")

    assert ask_response.status_code == 200
    assert session_response.status_code == 200
    assert session_response.json() == {"session_id": "inspect-me", "exists": True}


def test_runtime_session_missing_after_reset(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    client.post("/runtime/ask", json={"session_id": "gone", "input": "hello"})
    reset_response = client.post("/runtime/reset", json={"session_id": "gone"})
    session_response = client.get("/runtime/session/gone")

    assert reset_response.json() == {"session_id": "gone", "reset": True}
    assert session_response.status_code == 200
    assert session_response.json() == {"session_id": "gone", "exists": False}


def test_runtime_reset_missing_session_returns_false(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post("/runtime/reset", json={"session_id": "missing"})

    assert response.status_code == 200
    assert response.json() == {"session_id": "missing", "reset": False}


def test_runtime_ask_empty_input_returns_validation_error(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post("/runtime/ask", json={"input": "   "})

    assert response.status_code == 422


def test_api_defaults_to_mock_adapter_without_openai_key(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post("/runtime/ask", json={"session_id": "mock", "input": "hello"})

    assert response.status_code == 200
    assert response.json()["metadata"]["llm_adapter"] == "mock"


def test_misconfigured_openai_returns_controlled_error(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    monkeypatch.setenv("BOIS_LLM", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)

    response = client.post("/runtime/ask", json={"session_id": "bad-openai", "input": "hello"})

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "llm_unavailable"
    assert body["detail"] == "BOIS_LLM=openai requires OPENAI_API_KEY"
    assert body["session_id"] == "bad-openai"
    assert "Traceback" not in response.text


def test_runtime_frame_valid_input_returns_context_packet(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
    client = TestClient(app)

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
    assert body["packet_version"] == "boris-context/1.0"
    assert body["session_id"] == "frame-test"
    assert body["input"] == "Explain BOIS Runtime"
    assert body["runtime_mode"] == "context_provider"
    assert body["llm_called"] is False
    assert "type" not in body
    assert "content" not in body
    assert body["retrieval_metadata"] == {
        "returned_chunks": 0,
        "total_characters": 0,
        "truncated": False,
        "max_chunks": 6,
        "max_chunk_characters": 3000,
        "max_total_characters": 12000,
    }


def test_runtime_frame_generates_and_reuses_session(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
    client = TestClient(app)

    generated = client.post("/runtime/frame", json={"input": "hello"}).json()["session_id"]
    first = client.post("/runtime/frame", json={"session_id": "same-frame", "input": "hello"})
    runtime = runtime_registry.get("same-frame")
    second = client.post("/runtime/frame", json={"session_id": "same-frame", "input": "next"})

    assert generated
    assert first.status_code == 200
    assert second.status_code == 200
    assert runtime is runtime_registry.get("same-frame")


def test_runtime_frame_empty_input_returns_validation_error(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    client = TestClient(app)

    response = client.post("/runtime/frame", json={"input": "   "})

    assert response.status_code == 422


def test_runtime_frame_is_independent_of_openai_configuration(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)
    monkeypatch.setenv("BOIS_LLM", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
    client = TestClient(app)

    frame_response = client.post(
        "/runtime/frame",
        json={"session_id": "openai-frame", "input": "hello"},
    )
    ask_response = client.post(
        "/runtime/ask",
        json={"session_id": "openai-frame", "input": "hello"},
    )

    assert frame_response.status_code == 200
    assert frame_response.json()["llm_called"] is False
    assert ask_response.status_code == 503
    assert ask_response.json()["error"] == "llm_unavailable"


def test_runtime_frame_execution_error_is_controlled_and_redacted(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)

    import api.app as app_module

    class BrokenRegistry:
        def frame(self, session_id, user_input):
            raise ValueError("runtime exploded with secret-value")

    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setattr(app_module, "runtime_registry", BrokenRegistry())
    client = TestClient(app)

    response = client.post("/runtime/frame", json={"session_id": "broken", "input": "hello"})

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": "runtime_error",
        "detail": "runtime exploded with [redacted]",
        "session_id": "broken",
    }
    assert "Traceback" not in response.text
    assert "secret-value" not in response.text


def test_runtime_execution_error_returns_controlled_500(monkeypatch, api_context):
    app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)

    import api.app as app_module

    class BrokenRegistry:
        def run(self, session_id, user_input):
            raise ValueError("runtime exploded")

    monkeypatch.setattr(app_module, "runtime_registry", BrokenRegistry())
    client = TestClient(app)

    response = client.post("/runtime/ask", json={"session_id": "broken", "input": "hello"})

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": "runtime_error",
        "detail": "runtime exploded",
        "session_id": "broken",
    }
    assert "Traceback" not in response.text


def test_error_detail_redacts_openai_key(monkeypatch, api_context):
    _app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)

    import api.app as app_module

    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")

    response = app_module._error_response(
        500,
        "runtime_error",
        "failed with secret-value",
        session_id="redact",
    )

    assert response.status_code == 500
    assert b"secret-value" not in response.body
    assert b"[redacted]" in response.body


def test_runtime_registry_run_uses_handle_lock(monkeypatch, api_context):
    _app, runtime_registry = api_context
    clear_api_state(monkeypatch, runtime_registry)

    import api.runtime_registry as registry_module

    calls = []

    class FakeRuntime:
        def __init__(self, session_id=None, llm_adapter=None, core_ref=None):
            self.session_id = session_id
            self.llm_adapter = llm_adapter

        def run(self, user_input):
            calls.append((self.session_id, user_input))
            return {"type": "ANSWER", "content": "ok", "metadata": {}}

    monkeypatch.setattr(registry_module, "BOISRuntime", FakeRuntime)
    monkeypatch.setattr(registry_module, "build_lazy_llm_adapter", lambda: object())

    registry = registry_module.RuntimeRegistry()
    first = registry.run("locked", "one")
    handle = registry.get_handle("locked")
    runtime = registry.get("locked")
    second = registry.run("locked", "two")

    assert first["content"] == "ok"
    assert second["content"] == "ok"
    assert handle is not None
    assert handle.lock is not None
    assert runtime is registry.get("locked")
    assert calls == [("locked", "one"), ("locked", "two")]
