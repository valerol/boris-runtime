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
