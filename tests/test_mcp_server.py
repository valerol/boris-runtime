from pathlib import Path

from mcp_server.server import run_boris_ask
from mcp_server.runtime_client import RuntimeAPIError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntimeClient:
    def __init__(self, response=None, error=None):
        self.response = response or {
            "session_id": "test",
            "type": "ANSWER",
            "content": "ok",
            "metadata": {},
        }
        self.error = error
        self.calls = []

    def ask(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_boris_ask_calls_runtime_api_client():
    client = FakeRuntimeClient()

    response = run_boris_ask(
        input="Explain BOIS Runtime",
        session_id="test",
        mode="default",
        context={"source": "mcp-test"},
        client=client,
    )

    assert response == {
        "session_id": "test",
        "type": "ANSWER",
        "content": "ok",
        "metadata": {},
    }
    assert client.calls == [
        {
            "input": "Explain BOIS Runtime",
            "session_id": "test",
            "mode": "default",
            "context": {"source": "mcp-test"},
        }
    ]


def test_boris_ask_surfaces_runtime_error_payload():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }
    client = FakeRuntimeClient(error=RuntimeAPIError("HTTP 500", status_code=500, payload=error_payload))

    response = run_boris_ask(input="hello", session_id="test", client=client)

    assert response == error_payload


def test_boris_ask_returns_structured_adapter_error_without_payload():
    client = FakeRuntimeClient(error=RuntimeAPIError("connection failed"))

    response = run_boris_ask(input="hello", session_id="test", client=client)

    assert response == {
        "error": "runtime_api_error",
        "detail": "connection failed",
        "session_id": "test",
    }


def test_mcp_adapter_does_not_import_runtime_internals():
    forbidden = (
        "runtime.runtime",
        "BOISRuntime",
        "protocol.engine",
        "ProtocolEngine",
        "core.loader",
    )

    for path in (PROJECT_ROOT / "mcp_server").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in source, f"{path} must not reference {item}"
